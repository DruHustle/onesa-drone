"""Pinned owner-installed Drone component runner. Not an HTTP deployment service."""

import base64
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from uuid import UUID

PLAN = Path("/etc/onesa/oracle-drone-release.json")
ORIGINS = {
    "staging": ("https://drone-staging.onesa.eu", "https://drone-api-staging.onesa.eu", 18541),
    "production": ("https://drone.onesa.eu", "https://drone-api.onesa.eu", 18540),
}
CHECKS = {
    "staging": {
        "source_build_image_identity",
        "configuration_and_isolation",
        "authentication_and_authorization",
        "persistence",
        "affected_workflows",
        "schema_and_migrations",
        "rollback_readiness",
        "security_and_contracts",
    },
    "operations": {
        "backup_restore",
        "monitoring_and_capacity",
        "privacy_publication_controls",
        "preservation_baseline",
        "rollback_readiness",
    },
    "deploy": {
        "exact_authorized_artifact",
        "configuration_preserved",
        "independent_components_preserved",
        "provider_receipt",
    },
    "production": {
        "source_build_image_identity",
        "health_readiness",
        "authentication_and_authorization",
        "affected_workflows",
        "persistence_preserved",
        "independent_components_preserved",
        "configuration_preserved",
        "no_unapproved_processing_or_actuation",
    },
}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def private(path, directory=False):
    path = Path(path)
    s = path.lstat()
    public_certificate = path.suffix == ".crt"
    database_key = path.name == "server.key"
    require(
        not any(p.is_symlink() for p in [path, *path.parents])
        and s.st_uid in ({0, 70} if database_key else {0})
        and (s.st_mode & 0o022 == 0 if public_certificate else s.st_mode & 0o077 == 0),
        "Root-private custody required",
    )
    require(stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode), "Custody type differs")
    require(
        all(p.stat().st_uid == 0 and p.stat().st_mode & 0o022 == 0 for p in path.parents),
        "Custody ancestor changed",
    )
    return path


def write(path, value):
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb"
    ) as stream:
        stream.write(value if isinstance(value, bytes) else canonical(value))
        stream.flush()
        os.fsync(stream.fileno())


def validate_plan(plan, binding):
    require(
        binding.get("repository") == "DruHustle/onesa-drone"
        and binding.get("component") in {"backend", "frontend"},
        "Foreign component",
    )
    require(plan["bindings"].get(binding["component"]) == binding, "Changed source/artifact binding")
    require(
        binding["target_environment"] == "production"
        and re.fullmatch(r"[a-f0-9]{40}", binding["candidate_commit"]),
        "Qualified production source required",
    )
    backend_manifest = private(plan["build_manifests"]["backend"])
    identities = json.loads(backend_manifest.read_text())["runtime_image_ids"]
    images = {plan[k] for k in ["api_image", "database_image", "probe_image"]}
    require(
        set(plan["runtime_images"]) == set(identities) == images,
        "Complete portable/runtime image mapping required",
    )
    require(
        all(
            re.fullmatch(r"sha256:[a-f0-9]{64}", identities[image])
            and plan["runtime_images"][image] in {image, identities[image]}
            for image in images
        ),
        "Runtime image is not the scanned native artifact",
    )
    for slot, (origin, api, port) in ORIGINS.items():
        config = plan["slots"][slot]
        require(
            (config["origin"], config["api_origin"], config["port"]) == (origin, api, port),
            "Slot routing mismatch",
        )
        require(config["project"] == "onesa-drone-oracle-" + slot, "Foreign Compose project")
        hashes = {name: digest(private(name)) for name in config["configuration_sha256"]}
        if config.get("protection_bypass_file"):
            require(
                config["protection_bypass_file"] in hashes, "Automation access is not configuration-bound"
            )
        require(str(backend_manifest) in hashes, "Native image identities are not configuration-bound")
        control = json.loads(private(config["initialization_file"]).read_text())
        require(
            config["initialization_file"] in hashes
            and control
            == {
                "provision_database": config["provision_database"],
                "previous_image": config["previous_image"],
            }
            and type(control["provision_database"]) is bool
            and (
                control["previous_image"] is None
                if control["provision_database"]
                else bool(re.fullmatch(r"sha256:[a-f0-9]{64}", control["previous_image"] or ""))
            ),
            "Initialization or preservation policy is not bound",
        )
        require(hashes == config["configuration_sha256"], "Private configuration changed")
        require(
            hashlib.sha256(canonical(hashes)).hexdigest() == binding["configuration_sha256"][slot],
            "Configuration is not evidence-bound",
        )
    require(
        plan["slots"]["staging"]["configuration_sha256"]
        != plan["slots"]["production"]["configuration_sha256"],
        "Slot isolation required",
    )
    require(digest(private(plan["source_archive"])) == binding["source_sha256"], "Source archive changed")
    require(
        digest(private(plan["build_manifests"][binding["component"]])) == binding["build_sha256"],
        "Native build identity changed",
    )
    native = json.loads(Path(plan["build_manifests"][binding["component"]]).read_text())
    require(
        native["source_commit"] == binding["candidate_commit"]
        and native["source_tree"] == binding["source_tree"],
        "Build belongs to another source",
    )
    if binding["component"] == "backend":
        require(
            native["image_id"] == plan["api_image"] and native["architecture"] == "arm64",
            "Wrong native runtime",
        )
    expected = (
        plan["api_image"]
        if binding["component"] == "backend"
        else "sha256:" + digest(Path(plan["slots"]["production"]["frontend_artifact"]) / "release.json")
    )
    require(binding["artifact_digest"] == expected, "Artifact differs from owner binding")
    for image in [plan["api_image"], plan["database_image"], plan["probe_image"]]:
        evidence = plan["security_reports"][image]
        require(digest(private(evidence["path"])) == evidence["sha256"], "Security evidence changed")
        report = json.loads(Path(evidence["path"]).read_text())
        require(report.get("Metadata", {}).get("ImageID") == image, "Scan belongs to a different image")
        require(
            report.get("Results")
            and all(
                v.get("Severity") not in {"HIGH", "CRITICAL"}
                for r in report["Results"]
                for v in r.get("Vulnerabilities") or []
            ),
            "Runtime security gate failed",
        )
        created = datetime.fromisoformat(report["CreatedAt"].replace("Z", "+00:00"))
        require(0 <= time.time() - created.timestamp() < 24 * 3600, "Runtime security evidence expired")
    for path, expected in plan["tool_sha256"].items():
        require(digest(private(path)) == expected, "Installed tool changed")
    require(
        plan["physical_authority"] is False and plan["synthetic_data_only"] is True,
        "Simulation-only release scope required",
    )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class Client:
    def __init__(self, api, origin):
        require(
            (origin, api) in {(value[0], value[1]) for value in ORIGINS.values()}, "Foreign HTTP destination"
        )
        self.api, self.origin, self.csrf = api, origin, ""
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, path, method="GET", data=None, expected=200):
        require(path.startswith("/api/v1/") and ".." not in path, "HTTP path refused")
        headers = {
            "Origin": self.origin,
            "Content-Type": "application/json",
            "X-CSRF-Token": self.csrf,
            "User-Agent": "OnesaDroneOwnerQualification/1",
        }
        if method != "GET":
            headers["Idempotency-Key"] = __import__("uuid").uuid4().hex
        request = urllib.request.Request(
            self.api + path,
            data=canonical(data) if data is not None else None,
            method=method,
            headers=headers,
        )
        try:
            response = self.opener.open(request, timeout=25)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            require(
                response.status == expected,
                "Unexpected HTTP status: " + str(response.status) + " on " + path.split("/")[3],
            )
            raw = response.read(2 * 1024 * 1024 + 1)
            require(len(raw) <= 2 * 1024 * 1024, "HTTP response bound")
            return json.loads(raw)

    def login(self, account):
        user = self.call("/api/v1/auth/login", "POST", {k: account[k] for k in ["email", "password"]})
        self.csrf = user["csrf"]
        require(
            len(list(self.jar)) == 1
            and all(
                cookie.secure and cookie.domain_specified is False and cookie.has_nonstandard_attr("HttpOnly")
                for cookie in self.jar
            ),
            "Secure private session cookie required",
        )
        return user


class Runner:
    def __init__(self, binding, context, phase):
        require(os.geteuid() == 0 and not os.getenv("GITHUB_ACTIONS"), "External root-owner runner required")
        self.plan = json.loads(private(PLAN).read_text())
        validate_plan(self.plan, binding)
        self.binding, self.context, self.phase = binding, context, phase
        self.folder = private(self.plan["evidence_root"], directory=True)
        self.count = 0
        self.component = binding["component"]
        self.check_context()

    def check_context(self):
        keys = [
            ("context_id", "context"),
            ("qualification_id", "qualification"),
            ("authorization_id", "authorization"),
            ("operation_id", "deployment-intent"),
        ]
        key, kind = next((key, kind) for key, kind in keys if self.context.get(key))
        identifier = str(UUID(self.context[key]))
        store = private(self.plan["issuer_store"], directory=True)
        trust = json.loads(private(store / "trust.json").read_text())
        anchor = json.loads(private("/etc/onesa/oracle-release-trust.json").read_text())["installations"].get(
            str(store)
        )
        require(
            anchor and anchor["active"] and anchor["key_id"] == trust["key_id"],
            "Uncommissioned runner custody",
        )
        with sqlite3.connect("file:" + str(private(store / "records.sqlite")) + "?mode=ro", uri=True) as db:
            row = db.execute("SELECT envelope,revoked FROM records WHERE id=?", (identifier,)).fetchone()
            require(row and (not row[1] or self.phase == "production"), "Signed context missing/revoked")
            envelope = json.loads(row[0])
            record, signature = envelope["record"], envelope["signature"]
            require(
                record["kind"] == kind and record["binding"] == self.binding,
                "Context belongs to another source or phase",
            )
            require(
                signature["algorithm"] == "Ed25519"
                and signature["key_id"] == digest(private(store / "public.pem")) == trust["key_id"],
                "Foreign context signer",
            )
            if self.phase != "production":
                require(
                    datetime.fromisoformat(record["issued_at"])
                    <= datetime.now(timezone.utc)
                    < datetime.fromisoformat(record["expires_at"]),
                    "Context expired",
                )
            if self.phase == "staging":
                require(
                    db.execute("SELECT state FROM contexts WHERE id=?", (identifier,)).fetchone()
                    == ("reserved",),
                    "Staging context has not been durably reserved",
                )
        with tempfile.TemporaryDirectory(dir=self.folder) as directory:
            payload, sig = Path(directory) / "payload", Path(directory) / "signature"
            payload.write_bytes(canonical(record))
            sig.write_bytes(base64.b64decode(signature["value"], validate=True))
            payload.chmod(0o600)
            sig.chmod(0o600)
            self.run(
                [
                    "/usr/bin/openssl",
                    "pkeyutl",
                    "-verify",
                    "-rawin",
                    "-pubin",
                    "-inkey",
                    str(store / "public.pem"),
                    "-sigfile",
                    str(sig),
                    "-in",
                    str(payload),
                ]
            )

    def run(self, args, data=None, timeout=180, persist_stdout=True):
        self.count += 1
        try:
            result = subprocess.run(
                [str(x) for x in args], input=data, capture_output=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired as error:
            prefix = self.folder / (str(time.time_ns()) + "-interrupted")
            write(
                prefix.with_suffix(".json"), {"state": "INTERRUPTED_INSPECT_ONLY", "automatic_retry": False}
            )
            write(prefix.with_suffix(".stderr"), error.stderr or b"")
            if persist_stdout:
                write(prefix.with_suffix(".stdout"), error.stdout or b"")
            raise ValueError("Command interrupted; inspect retained operation") from None
        # Logs may contain private diagnostics; they never go to caller stdout.
        prefix = self.folder / (str(time.time_ns()) + "-" + str(self.count))
        write(
            prefix.with_suffix(".stdout"),
            result.stdout
            if persist_stdout
            else canonical(
                {
                    "bytes": len(result.stdout),
                    "sha256": hashlib.sha256(result.stdout).hexdigest(),
                    "plaintext_not_persisted": True,
                }
            ),
        )
        write(prefix.with_suffix(".stderr"), result.stderr)
        require(result.returncode == 0, "Command failed; inspect private diagnostic " + prefix.name)
        return result.stdout

    def compose(self, slot, *args, data=None, timeout=180, persist_stdout=True):
        config = self.plan["slots"][slot]
        return self.run(
            [
                "/usr/bin/docker",
                "compose",
                "--project-name",
                config["project"],
                "--env-file",
                config["images_env"],
                "-f",
                self.plan["compose_file"],
                *args,
            ],
            data,
            timeout,
            persist_stdout,
        )

    def identity(self, slot):
        config = self.plan["slots"][slot]
        name = config["project"] + "-api-1"
        raw = self.run(
            [
                "/usr/bin/docker",
                "inspect",
                "--format",
                "{{json .Image}} {{json .Config.Labels}} {{json .HostConfig.PortBindings}} {{json .State.Health.Status}}",
                name,
            ]
        )
        decoder = json.JSONDecoder()
        values = []
        text = raw.decode().strip()
        while text:
            value, end = decoder.raw_decode(text)
            values.append(value)
            text = text[end:].lstrip()
        image, labels, ports, health = values
        require(
            image == self.plan["runtime_images"][self.plan["api_image"]]
            and labels["org.onesa.source-commit"] == self.binding["candidate_commit"]
            and labels["org.onesa.mode"] == "simulation",
            "Serving runtime/source differs",
        )
        require(
            health == "healthy"
            and ports == {"8400/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(config["port"])}]},
            "Health/loopback binding differs",
        )
        return image

    def preserved(self):
        for name, image in self.plan["preserved_containers"].items():
            actual = self.run(["/usr/bin/docker", "inspect", "--format", "{{.Image}}", name]).decode().strip()
            require(actual == image, "Independent workload changed: " + name)
        require(shutil.disk_usage("/").free >= 4 * 1024**3, "Oracle disk reserve below 4 GiB")
        available = next(
            int(line.split()[1]) * 1024
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemAvailable:")
        )
        require(available >= 1024**3, "Oracle memory reserve below 1 GiB")

    def initialize_backend(self, slot):
        config = self.plan["slots"][slot]
        if not config["provision_database"]:
            existing = (
                self.run(
                    ["/usr/bin/docker", "inspect", "--format", "{{.Image}}", config["project"] + "-api-1"]
                )
                .decode()
                .strip()
            )
            require(
                existing == config["previous_image"],
                "Existing Drone image changed before preservation update",
            )
            before = self.verify_storage(slot)
            self.compose(slot, "up", "-d", "--wait", "--wait-timeout", "90", "db")
            self.compose(slot, "run", "--rm", "-T", "migrate")
            self.compose(slot, "up", "-d", "--wait", "--wait-timeout", "90", "api")
            self.identity(slot)
            require(before == self.verify_storage(slot), "Existing Drone records changed during image update")
            return
        self.compose(slot, "up", "-d", "--wait", "--wait-timeout", "90", "db")
        self.compose(slot, "run", "--rm", "-T", "migrate")
        # This file contains only the new slot's schema grants and generated login.
        self.compose(
            slot,
            "exec",
            "-T",
            "db",
            "psql",
            "-X",
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "drone_owner",
            "-d",
            "drone",
            data=private(config["grants_file"]).read_bytes(),
        )
        fixture = json.loads(private(config["fixture_file"]).read_text())
        for account in [fixture["operator"], fixture["foreign"]]:
            secret = (account["password"] + "\n") * 2
            self.compose(
                slot,
                "run",
                "--rm",
                "-T",
                "migrate",
                "python",
                "-m",
                "backend.app.cli",
                "bootstrap",
                "--email",
                account["email"],
                "--tenant",
                "Synthetic Drone " + slot,
                data=secret.encode(),
            )
        self.compose(
            slot,
            "run",
            "--rm",
            "-T",
            "migrate",
            "python",
            "-m",
            "backend.app.cli",
            "seed",
            "--email",
            fixture["operator"]["email"],
        )
        self.compose(slot, "up", "-d", "--wait", "--wait-timeout", "90", "api")
        self.identity(slot)

    def api_check(self, slot, workflow=False):
        config = self.plan["slots"][slot]
        fixture = json.loads(private(config["fixture_file"]).read_text())
        require(
            all(
                re.fullmatch(r"[a-z0-9._+-]+@example\.test", account["email"])
                and len(account["password"]) >= 14
                for account in fixture.values()
            ),
            "Only owned synthetic fixture identities are permitted",
        )
        api, origin = config["api_origin"], config["origin"]
        guest = Client(api, origin)
        require(
            guest.call("/api/v1/health")["mode"] == "simulation"
            and guest.call("/api/v1/ready")["status"] == "ready",
            "Live/readiness unavailable",
        )
        guest.call("/api/v1/operations", expected=401)
        client = Client(api, origin)
        user = client.login(fixture["operator"])
        require(user["role"] == "admin", "Fixture role differs")
        operations = client.call("/api/v1/operations")
        require(operations["mode"] == "simulation" and operations["aircraft"], "Illustrative fleet missing")
        monitor = client.call("/api/v1/infrastructure")
        services = {row["name"]: row["status"] for row in monitor["services"]}
        require(
            all(services.get(k) == "healthy" for k in ["Backend", "Database", "Telemetry"])
            and services.get("Simulation") in {"healthy", "idle"}
            and monitor["metrics"]["worker_failures"] == 0,
            "Operational monitoring degraded",
        )
        controls = client.call("/api/v1/security")["controls"]
        require(
            controls["simulation_only"] is True and controls["physical_adapter"] == "disabled",
            "Physical authority detected",
        )
        if workflow:
            mission = client.call(
                "/api/v1/missions",
                "POST",
                {
                    "label": "Owner qualification " + self.context["context_id"][:8],
                    "package_weight": 1.2,
                    "package_kind": "standard",
                    "origin": {"lat": 52.52, "lon": 13.405},
                    "destination": {"lat": 52.523, "lon": 13.411},
                    "scenario": "nominal",
                },
                201,
            )
            token, mission = mission["tracking_token"], mission["mission"]
            foreign = Client(api, origin)
            foreign.login(fixture["foreign"])
            foreign.call("/api/v1/missions/" + mission["id"] + "/history", expected=404)
            viewer = fixture["viewer"]
            self.ensure_viewer(client, viewer)
            reader = Client(api, origin)
            reader.login(viewer)
            reader.call(
                "/api/v1/missions/" + mission["id"] + "/commands",
                "POST",
                {"action": "plan", "revision": mission["revision"]},
                403,
            )
            for action in ["plan", "validate", "authorize", "launch"]:
                mission = client.call(
                    "/api/v1/missions/" + mission["id"] + "/commands",
                    "POST",
                    {"action": action, "revision": mission["revision"]},
                )
            until = time.monotonic() + 120
            while time.monotonic() < until:
                current = client.call("/api/v1/operations")
                mission = next(row for row in current["missions"] if row["id"] == mission["id"])
                if mission["state"] == "completed":
                    break
                require(
                    mission["state"] not in {"aborted", "cancelled", "paused"}, "Qualification mission failed"
                )
                time.sleep(1)
            require(
                mission["state"] == "completed" and mission["delivered"], "Virtual delivery not completed"
            )
            history = client.call("/api/v1/missions/" + mission["id"] + "/history")
            require(
                history["telemetry"] and history["events"][-1]["state"] == "completed",
                "Persistence/history unavailable",
            )
            tracking = guest.call("/api/v1/tracking/" + token)
            require(
                tracking["delivered"]
                and not {"aircraft_id", "position", "destination", "origin", "label"} & tracking.keys(),
                "Tracking privacy differs",
            )
        return {"authentication": True, "tenant_scope": workflow, "persistent_fleet": True}

    def ensure_viewer(self, client, account):
        existing = next((u for u in client.call("/api/v1/users") if u["email"] == account["email"]), None)
        if existing:
            require(
                existing["role"] == "viewer" and existing["active"] is True,
                "Existing fixture authority changed",
            )
        else:
            client.call("/api/v1/users", "POST", {**account, "role": "viewer"}, 201)

    def verify_storage(self, slot, database=None):
        script = r"""
import hashlib,json
from sqlalchemy import select,func,text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from backend.app.config import Settings
from backend.app.db import Store
from backend.app.models import Tenant,Aircraft,Mission,MissionEvent,Audit,Telemetry
from backend.app.service import j
from autonomy.safety_supervisor.supervisor import physical_command
cfg=Settings();cfg.validate();url=make_url(cfg.database_url)
assert cfg.secure and cfg.worker and not cfg.ai_url and not cfg.ai_session
try:physical_command('arm')
except PermissionError:pass
else:raise AssertionError('Physical command accepted')
if DATABASE is not None:url=url.set(database=DATABASE)
s=Store(url.render_as_string(hide_password=False));s.verify()
with s.session() as db:
    assert db.execute(text('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()')).scalar() is True
    assert db.execute(text("SELECT current_user")).scalar()=='drone_login'
    for table,privilege in [('audits','DELETE'),('audits','UPDATE'),('mission_events','DELETE')]:
        assert db.execute(text('SELECT has_table_privilege(current_user,:table,:privilege)'),{'table':table,'privilege':privilege}).scalar() is False
    assert db.execute(text("SELECT has_schema_privilege(current_user,'public','CREATE')")).scalar() is False
    counts={m.__tablename__:db.scalar(select(func.count()).select_from(m)) for m in [Tenant,Aircraft,Mission,MissionEvent,Audit,Telemetry]}
    for tenant in db.scalars(select(Tenant)):
        rows=list(db.scalars(select(Audit).where(Audit.tenant_id==tenant.id)))
        remaining={a.previous:a for a in rows};previous='';seen=0
        assert len(remaining)==len(rows)
        while previous in remaining:
            a=remaining.pop(previous)
            assert hashlib.sha256(j([a.id,a.tenant_id,a.at,a.actor,a.action,a.detail,a.correlation_id,a.previous]).encode()).hexdigest()==a.digest
            previous=a.digest;seen+=1
        assert not remaining and seen==len(rows) and previous==tenant.audit_head
bad=Store(url.set(query={**url.query,'sslrootcert':'/etc/ssl/cert.pem'}).render_as_string(hide_password=False))
try:
    with bad.session() as db:db.execute(text('SELECT 1'))
except SQLAlchemyError:pass
else:raise AssertionError('Untrusted database CA accepted')
print(json.dumps({'counts':counts,'schema_verified':True,'tls_and_wrong_ca':True,'runtime_grants':True,'tenant_audit_chains':True}))
""".replace("DATABASE", repr(database))
        return json.loads(self.compose(slot, "exec", "-T", "api", "python", "-", data=script.encode()))

    def rollback_readiness(self):
        recovery = json.loads(private(self.plan["rollback_file"]).read_text())
        require(
            recovery["source_commit"] == self.binding["candidate_commit"]
            and recovery["strategy"] == "first-release-disable-only"
            and recovery["preserve_database"] is True
            and recovery["physical_interfaces_disabled"] is True,
            "First-release rollback plan differs",
        )
        for image in [self.plan["api_image"], self.plan["database_image"], self.plan["probe_image"]]:
            self.run(
                [
                    "/usr/bin/docker",
                    "image",
                    "inspect",
                    "--format",
                    "{{.Id}}",
                    self.plan["runtime_images"][image],
                ]
            )
        for name, expected in self.plan["retained_artifacts"].items():
            require(digest(private(name)) == expected, "Rollback artifact is missing or changed")

    def frontend_files(self, slot):
        artifact = private(self.plan["slots"][slot]["frontend_artifact"], directory=True)
        manifest = json.loads((artifact / "release.json").read_text())
        require(
            manifest["source_commit"] == self.binding["candidate_commit"]
            and manifest["environment"] == slot
            and manifest["project_id"] == self.plan["vercel_project_id"],
            "Frontend artifact identity differs",
        )
        require(manifest["backend_origin"] == ORIGINS[slot][1], "Frontend/API environment crossed")
        for name, expected in manifest["files"].items():
            require(not name.startswith("/") and ".." not in Path(name).parts, "Artifact path refused")
            require(digest(artifact / ".vercel/output/static" / name) == expected, "Frontend bytes changed")
        require(
            digest(artifact / ".vercel/output/config.json") == manifest["routing_sha256"], "Routing changed"
        )
        expected_files = json.loads(private(self.plan["build_manifests"]["frontend"]).read_text())["files"]
        require(manifest["files"] == expected_files, "Frontend differs from the native build")
        actual_files = {
            str(p.relative_to(artifact / ".vercel/output/static"))
            for p in (artifact / ".vercel/output/static").rglob("*")
            if p.is_file()
        }
        require(actual_files == set(manifest["files"]), "Unreviewed frontend file present")
        return artifact

    def vercel(self, args, operation=None, artifact=None, data=None):
        custody = private(self.plan["vercel_custody"], directory=True)
        auth = json.loads(private(custody / "auth.json").read_text())
        require(
            auth.get("expiresAt", 0) > time.time() + 3600,
            "Provider custody needs normal owner renewal before a request",
        )
        command = [
            "/usr/bin/docker",
            "run",
            "--rm",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            "384m",
            "--cpus",
            "0.25",
            "--tmpfs",
            "/root:rw,nosuid,nodev,size=32m",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=32m",
            "-e",
            "VERCEL_TELEMETRY_DISABLED=1",
            "-e",
            "CI=1",
            "-v",
            str(custody) + ":/private/vercel:rw",
        ]
        if artifact:
            command += [
                "-v",
                str(artifact) + ":/artifact:ro",
                "--tmpfs",
                "/work:rw,nosuid,nodev,size=64m",
                "--entrypoint",
                "/bin/sh",
            ]
        if operation:
            transport = self.folder / (operation + "-transport")
            transport.mkdir(mode=0o700)
            write(
                transport / "scope.json",
                {
                    "operation_id": operation,
                    "request_budget": 1,
                    "repository": "DruHustle/onesa-drone",
                    "component": "frontend",
                    "environment": "production" if self.phase == "deploy" else "staging",
                },
            )
            shutil.copyfile(private(self.plan["transport_guard"]), transport / "guard.cjs")
            (transport / "guard.cjs").chmod(0o600)
            command += [
                "-v",
                str(transport) + ":/private/transport:rw",
                "-e",
                "ONESA_ORACLE_VERIFIER_PRELOAD=1",
                "-e",
                "NODE_OPTIONS=--require=/private/transport/guard.cjs",
            ]
        command += [self.plan["vercel_cli_image"]]
        if artifact:
            command += [
                "-c",
                'cp -R /artifact/. /work/ && exec node /opt/onesa-vercel-tool/node_modules/vercel/dist/index.js "$@"',
                "vercel",
            ]
        command += [
            *args,
            "--scope",
            "druhustles-projects",
            "--global-config",
            "/private/vercel",
        ]
        return self.run(command, data, timeout=300)

    def deploy_frontend(self, slot, identifier):
        artifact = self.frontend_files(slot)
        args = [
            "deploy",
            "--prebuilt",
            "--archive=tgz",
            "--cwd",
            "/work",
            "--meta",
            "onesaOperationID=" + identifier,
            "--meta",
            "onesaSourceCommit=" + self.binding["candidate_commit"],
            "--meta",
            "gitCommitRef=" + ("main" if slot == "production" else "staging"),
        ]
        if slot == "production":
            args += ["--prod", "--skip-domain"]
        else:
            args.append("--target=preview")
        raw = self.vercel(args, operation=identifier, artifact=artifact).decode()
        urls = set(re.findall(r"https://onesa-drone-[a-z0-9-]+\.vercel\.app", raw))
        require(len(urls) == 1, "Provider create acknowledgement uncertain; inspect retained request")
        url = urls.pop()
        details = json.loads(self.vercel(["api", "/v13/deployments/" + url.removeprefix("https://")]))
        self.frontend_receipt_identity(details, slot, identifier)
        self.vercel(["alias", "set", url, ORIGINS[slot][0].removeprefix("https://")])
        self.alias_identity(slot, details["id"])
        receipt = {
            "deployment_id": details["id"],
            "url": url,
            "source": self.binding["candidate_commit"],
            "project_id": details["projectId"],
        }
        write(self.folder / (slot + "-frontend-receipt.json"), receipt)
        return receipt["deployment_id"]

    def frontend_receipt_identity(self, details, slot, identifier):
        require(
            details["projectId"] == self.plan["vercel_project_id"]
            and details.get("meta", {}).get("onesaSourceCommit") == self.binding["candidate_commit"]
            and details.get("meta", {}).get("onesaOperationID") == identifier
            and details.get("readyState") == "READY"
            and (
                details.get("target") == "production"
                if slot == "production"
                else details.get("target") in {None, "preview"}
            ),
            "Provider source/project/operation/target receipt differs; do not assign an alias",
        )

    def alias_identity(self, slot, deployment):
        host = ORIGINS[slot][0].removeprefix("https://")
        observed = json.loads(self.vercel(["api", "/v4/aliases/" + host]))
        require(
            observed.get("alias") == host
            and observed.get("projectId") == self.plan["vercel_project_id"]
            and observed.get("deploymentId") == deployment,
            "Canonical frontend alias differs from the provider receipt",
        )

    def browser(self, slot, workflow=False):
        config = self.plan["slots"][slot]
        fixture = json.loads(private(config["fixture_file"]).read_text())["operator"]
        body = {**fixture, "origin": config["origin"], "workflow": workflow}
        bypass = config.get("protection_bypass_file")
        if bypass:
            body["protection_bypass"] = private(bypass).read_text().strip()
        raw = self.run(
            [
                "/usr/bin/docker",
                "run",
                "--rm",
                "-i",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--memory",
                "1024m",
                "--cpus",
                "0.5",
                "--pids-limit",
                "256",
                "-e",
                "LP_NUM_THREADS=2",
                "-e",
                "XDG_CONFIG_HOME=/tmp/onesa-chromium-config",
                "-e",
                "XDG_CACHE_HOME=/tmp/onesa-chromium-cache",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=192m",
                self.plan["runtime_images"][self.plan["probe_image"]],
            ],
            canonical(body),
            timeout=300,
        )
        observed = json.loads(raw)
        require(
            observed["state"] == "OBSERVED"
            and observed["mode"] == "simulation"
            and observed["physical_interfaces_used"] is False,
            "Browser observation incomplete",
        )
        require(
            all(
                observed["checks"].get(key) is True
                for key in ["authentication", "live_telemetry", "webgl", "responsive_accessibility"]
            ),
            "Browser check missing",
        )
        if workflow:
            require(observed["checks"].get("complete_delivery") is True, "Hosted delivery not demonstrated")

    def backup_restore(self):
        slot = "staging"
        before = self.verify_storage(slot)
        archive = self.compose(
            slot,
            "exec",
            "-T",
            "db",
            "pg_dump",
            "-U",
            "drone_owner",
            "-d",
            "drone",
            "-Fc",
            "--no-owner",
            persist_stdout=False,
        )
        require(len(archive) <= 64 * 1024 * 1024, "Simulation backup exceeds approved initial bound")
        target = "drone_restore_" + __import__("uuid").uuid4().hex[:16]
        self.compose(slot, "exec", "-T", "db", "createdb", "-U", "drone_owner", target)
        self.compose(
            slot,
            "exec",
            "-T",
            "db",
            "pg_restore",
            "-U",
            "drone_owner",
            "-d",
            target,
            "--no-owner",
            "--exit-on-error",
            data=archive,
        )
        sql = "SELECT (SELECT count(*) FROM missions),(SELECT count(*) FROM mission_events),(SELECT count(*) FROM audits),(SELECT count(*) FROM telemetry)"
        original = self.compose(
            slot, "exec", "-T", "db", "psql", "-X", "-tA", "-U", "drone_owner", "-d", "drone", "-c", sql
        )
        restored = self.compose(
            slot, "exec", "-T", "db", "psql", "-X", "-tA", "-U", "drone_owner", "-d", target, "-c", sql
        )
        require(original == restored, "Restored operational counts differ")
        require(
            before == self.verify_storage(slot, database=target),
            "Restored schema, grants, counts or audit chain differs",
        )
        recipient = private(self.plan["backup_recipient"])
        encrypted = self.run(
            [
                "/usr/bin/openssl",
                "cms",
                "-encrypt",
                "-binary",
                "-aes-256-gcm",
                "-outform",
                "DER",
                "-recip",
                str(recipient),
            ],
            archive,
        )
        name = "staging-backup-" + str(time.time_ns()) + ".cms"
        write(self.folder / name, encrypted)
        write(
            self.folder / (name + ".json"),
            {
                "source": self.binding["candidate_commit"],
                "ciphertext_sha256": hashlib.sha256(encrypted).hexdigest(),
                "restored_counts_sha256": hashlib.sha256(restored).hexdigest(),
                "restore_database": target,
                "plaintext_dump_persisted": False,
            },
        )

    def execute(self):
        self.preserved()
        self.frontend_files("staging")
        self.frontend_files("production")
        self.rollback_readiness()
        slot = "staging" if self.phase == "staging" else "production"
        deployment = None
        if self.phase == "staging":
            marker = self.folder / (self.context["context_id"] + "-" + self.component + "-intent.json")
            write(
                marker,
                {"context_id": self.context["context_id"], "binding": self.binding, "automatic_retry": False},
            )
            if self.component == "backend":
                self.initialize_backend(slot)
                self.api_check(slot, workflow=True)
                self.verify_storage(slot)
                # First-release rollback preserves the database while withdrawing
                # the single simulation process; restart proves retained persistence.
                before = self.verify_storage(slot)
                self.compose(slot, "stop", "api")
                self.compose(slot, "up", "-d", "--wait", "--wait-timeout", "90", "api")
                self.identity(slot)
                require(before == self.verify_storage(slot), "Restart lost persisted records")
            else:
                self.identity(slot)
                self.deploy_frontend(slot, self.context["context_id"])
                self.browser(slot, workflow=True)
            self.backup_restore()
        elif self.phase == "operations":
            self.identity("staging")
            self.api_check("staging")
            self.backup_restore()
        elif self.phase == "deploy":
            marker = self.folder / (self.context["operation_id"] + "-" + self.component + "-intent.json")
            write(
                marker,
                {
                    "operation_id": self.context["operation_id"],
                    "binding": self.binding,
                    "automatic_retry": False,
                },
            )
            if self.component == "backend":
                self.initialize_backend(slot)
                self.api_check(slot)
                self.verify_storage(slot)
                deployment = self.identity(slot)
            else:
                self.identity(slot)
                deployment = self.deploy_frontend(slot, self.context["operation_id"])
        elif self.phase == "production":
            self.identity(slot)
            self.api_check(slot)
            self.verify_storage(slot)
            if self.component == "frontend":
                self.browser(slot)
                receipt = json.loads(private(self.folder / "production-frontend-receipt.json").read_text())
                details = json.loads(self.vercel(["api", "/v13/deployments/" + receipt["deployment_id"]]))
                self.alias_identity(slot, receipt["deployment_id"])
                require(
                    details["projectId"] == self.plan["vercel_project_id"]
                    and details.get("readyState") == "READY"
                    and details["meta"].get("onesaSourceCommit") == self.binding["candidate_commit"],
                    "Serving frontend receipt differs",
                )
                deployment = details["id"]
            else:
                deployment = self.identity(slot)
        else:
            raise ValueError("Unknown phase")
        self.preserved()
        # Each phase reaches this only after its real commands and observations pass.
        return {
            "binding": self.binding,
            "environment": slot,
            "workflow_run_id": 0,
            "operation_id": self.context.get("operation_id"),
            "deployment_id": deployment,
            "checks": {name: "PASS" for name in CHECKS[self.phase]},
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "physical_authority": False,
        }


def main():
    raw = sys.stdin.buffer.read(128 * 1024 + 1)
    require(len(raw) <= 128 * 1024, "Runner input bound")
    value = json.loads(raw)
    result = Runner(value["binding"], value["context"], sys.argv[1]).execute()
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Drone owner runner failed; inspect private evidence; no automatic retry.", file=sys.stderr)
        raise SystemExit(1) from None

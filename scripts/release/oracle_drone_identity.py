"""Explicit owner-bound shared account qualification for existing Drone slots.

No identity is created, granted, linked by email or changed here. Actual Portal
sign-in yields a product session whose host-only cookie never crosses to the API
hostname. Existing mission, isolation, storage, restore and browser checks remain.
"""

import base64
import fcntl
import hashlib
import http.cookiejar
import json
import os
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

PROFILE = "shared-identity-v1"
KEYS = {
    "ONESA_IDENTITY_ENABLED",
    "ONESA_IDENTITY_ISSUER",
    "ONESA_IDENTITY_CLIENT_ID",
    "ONESA_IDENTITY_CLIENT_SECRET",
    "ONESA_IDENTITY_CALLBACK",
    "ONESA_IDENTITY_ENCRYPTION_KEY",
}
ACTORS = {"operator", "foreign", "viewer"}
BROWSER = "/probe/scripts/release/oracle_drone_identity_browser.mjs"
CREDENTIAL_FIELDS = {
    "schema_version",
    "candidate_commit",
    "scope",
    "created_at",
    "expires_at",
    "accounts",
    "portal_bypass",
}


def require(value, code):
    if not value:
        raise ValueError(code)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DRONE_IDENTITY_DUPLICATE_FIELD")
        result[key] = value
    return result


def read(path):
    import oracle_drone as d

    path = d.private(path)
    require(
        path.stat().st_nlink == 1 and 0 < path.stat().st_size <= 128 * 1024,
        "DRONE_IDENTITY_PRIVATE_INPUT_BOUND",
    )
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def values(path):
    import oracle_drone as d

    path = d.private(path)
    require(
        path.stat().st_nlink == 1 and 0 < path.stat().st_size <= 128 * 1024, "DRONE_IDENTITY_RUNTIME_BOUND"
    )
    rows = [line for line in path.read_text().splitlines() if line and not line.startswith("#")]
    require(all("=" in line for line in rows), "DRONE_IDENTITY_RUNTIME_FORMAT")
    result = dict(line.split("=", 1) for line in rows)
    require(
        len(result) == len(rows) and all(re.fullmatch(r"[A-Z][A-Z0-9_]*", key) for key in result),
        "DRONE_IDENTITY_RUNTIME_DUPLICATE_OR_INVALID",
    )
    return result


def credential_payload_digest(value):
    """Bind all credential and scope values while allowing a fresh short lease."""
    import oracle_drone as d

    require(set(value) == CREDENTIAL_FIELDS, "DRONE_IDENTITY_CREDENTIAL_CUSTODY")
    return hashlib.sha256(
        d.canonical({key: item for key, item in value.items() if key not in {"created_at", "expires_at"}})
    ).hexdigest()


def credential_pin(path):
    return credential_payload_digest(read(path))


def source_profile(plan, binding):
    import oracle_drone as d

    selected = plan.get("qualification_profile")
    if selected is None:
        require("identity" not in plan, "DRONE_EXPLICIT_IDENTITY_PROFILE_REQUIRED")
        return None
    require(selected == PROFILE, "DRONE_UNKNOWN_QUALIFICATION_PROFILE")
    value = plan["identity"]
    require(
        set(value) == {"candidate_commit", "source_tree", "source_sha256", "environments"}
        and all(value[key] == binding[key] for key in ["candidate_commit", "source_tree", "source_sha256"])
        and set(value["environments"]) == {"staging", "production"},
        "DRONE_IDENTITY_SOURCE_BINDING",
    )
    for name in [
        "oracle_drone_identity.py",
        "oracle_drone_identity_browser.mjs",
        "probe_policy.mjs",
        "oracle_drone_rollback.py",
        "oracle_drone_rollback_containers.py",
    ]:
        path = Path(__file__).with_name(name)
        require(
            plan["tool_sha256"].get(str(path)) == d.digest(d.private(path)),
            "DRONE_MATCHED_IDENTITY_HELPER_REQUIRED",
        )
    subjects = set()
    for environment, entry in value["environments"].items():
        require(
            set(entry)
            == {
                "issuer",
                "client_id",
                "client_secret_sha256",
                "encryption_key_sha256",
                "accounts",
                "portal_bypass_sha256",
                "baseline_runtime_file",
                "baseline_migrator_file",
            },
            "DRONE_IDENTITY_ENVIRONMENT_SCHEMA",
        )
        issuer = urlsplit(entry["issuer"])
        require(
            issuer.scheme == "https"
            and not issuer.username
            and not issuer.password
            and not issuer.port
            and issuer.path == "/api/v1/identity"
            and not issuer.query
            and not issuer.fragment
            and (
                issuer.hostname == "portal.onesa.eu"
                if environment == "production"
                else re.fullmatch(r"onesa-company-portal-[a-z0-9-]+\.vercel\.app", issuer.hostname or "")
            ),
            "DRONE_IDENTITY_ISSUER_SCOPE",
        )
        require(
            re.fullmatch(r"[A-Za-z0-9_-]{16,128}", entry["client_id"])
            and all(
                re.fullmatch(r"[a-f0-9]{64}", entry[key])
                for key in ["client_secret_sha256", "encryption_key_sha256"]
            )
            and (
                entry["portal_bypass_sha256"] is None
                or environment == "staging"
                and re.fullmatch(r"[a-f0-9]{64}", entry["portal_bypass_sha256"])
            )
            and set(entry["accounts"]) == ACTORS,
            "DRONE_CONFIDENTIAL_CLIENT_PROFILE",
        )
        for actor, account in entry["accounts"].items():
            require(
                set(account) == {"subject", "email", "tenant_id", "role"}
                and all(str(UUID(account[key])) == account[key] for key in ["subject", "tenant_id"])
                and re.fullmatch(r"[^\s@]{1,64}@[^\s@]{1,189}", account["email"])
                and account["email"] == account["email"].casefold()
                and account["role"] == ("viewer" if actor == "viewer" else "admin"),
                "DRONE_EXISTING_SYNTHETIC_IDENTITY_REQUIRED",
            )
            require(account["subject"] not in subjects, "DRONE_SEPARATE_ENVIRONMENT_PRINCIPALS_REQUIRED")
            subjects.add(account["subject"])
        accounts = entry["accounts"]
        require(
            accounts["operator"]["tenant_id"] == accounts["viewer"]["tenant_id"]
            and accounts["foreign"]["tenant_id"] != accounts["operator"]["tenant_id"],
            "DRONE_ISOLATED_WORKSPACE_FIXTURES_REQUIRED",
        )
        slot = plan["slots"][environment]
        require(slot["provision_database"] is False, "DRONE_IDENTITY_PRESERVES_EXISTING_DATABASES")
        hashes = slot["configuration_sha256"]
        require(
            all(slot[key] in hashes for key in ["images_env", "fixture_file"])
            and all(entry[key] in hashes for key in ["baseline_runtime_file", "baseline_migrator_file"]),
            "DRONE_IDENTITY_PRIVATE_CONFIGURATION_NOT_BOUND",
        )
        images = values(slot["images_env"])
        for key, baseline in [
            ("DRONE_RUNTIME_ENV_FILE", "baseline_runtime_file"),
            ("DRONE_MIGRATOR_ENV_FILE", "baseline_migrator_file"),
        ]:
            require(images[key] in hashes, "DRONE_IDENTITY_RUNTIME_NOT_BOUND")
            prepared, previous = values(images[key]), values(entry[baseline])
            require(
                {k: v for k, v in previous.items() if k not in KEYS}
                == {k: v for k, v in prepared.items() if k not in KEYS},
                "DRONE_UNRELATED_CONFIGURATION_CHANGED",
            )
            configuration(entry, slot["origin"], prepared)
        # A genuine reserved owner phase renews only this time envelope later.
        # Static preflight still verifies the complete immutable credential pin.
        credentials(plan, binding, environment, require_current=False)
    stage, production = (value["environments"][key] for key in ["staging", "production"])
    require(
        all(
            stage[key] != production[key]
            for key in ["issuer", "client_id", "client_secret_sha256", "encryption_key_sha256"]
        ),
        "DRONE_IDENTITY_ENVIRONMENT_SECRETS_MUST_BE_SEPARATE",
    )
    import oracle_drone_rollback

    oracle_drone_rollback.profile(plan, binding)
    return value


def configuration(entry, origin, prepared):
    secret, encryption = (
        prepared.get("ONESA_IDENTITY_CLIENT_SECRET", ""),
        prepared.get("ONESA_IDENTITY_ENCRYPTION_KEY", ""),
    )
    require(
        prepared.get("ONESA_IDENTITY_ENABLED") == "true"
        and prepared.get("ONESA_IDENTITY_ISSUER") == entry["issuer"]
        and prepared.get("ONESA_IDENTITY_CLIENT_ID") == entry["client_id"]
        and prepared.get("ONESA_IDENTITY_CALLBACK") == origin + "/api/v1/auth/identity/callback"
        and 32 <= len(secret) <= 1024
        and all(33 <= ord(char) <= 126 for char in secret)
        and hashlib.sha256(secret.encode()).hexdigest() == entry["client_secret_sha256"]
        and re.fullmatch(r"[A-Za-z0-9_-]{43}=", encryption)
        and len(base64.urlsafe_b64decode(encryption)) == 32
        and hashlib.sha256(encryption.encode()).hexdigest() == entry["encryption_key_sha256"],
        "DRONE_IDENTITY_CONFIGURATION_CHANGED",
    )


def credentials(plan, binding, environment, *, require_current=True):
    value = read(plan["slots"][environment]["fixture_file"])
    return validate_credentials(value, plan, binding, environment, require_current=require_current)


def validate_credentials(value, plan, binding, environment, *, require_current=True):
    slot = plan["slots"][environment]
    path = slot["fixture_file"]
    require(
        set(value) == CREDENTIAL_FIELDS
        and credential_payload_digest(value) == slot["configuration_sha256"][path]
        and type(value["schema_version"]) is int
        and value["schema_version"] == 1
        and value["candidate_commit"] == binding["candidate_commit"]
        and value["scope"] == "existing-owned-synthetic-identities"
        and set(value["accounts"]) == ACTORS,
        "DRONE_IDENTITY_CREDENTIAL_CUSTODY",
    )
    stamps = [datetime.fromisoformat(value[key]) for key in ["created_at", "expires_at"]]
    require(all(stamp.tzinfo is not None for stamp in stamps), "DRONE_IDENTITY_CREDENTIAL_TIMEZONE")
    created, expires = (stamp.timestamp() for stamp in stamps)
    require(
        0 < expires - created <= 3600
        and created <= time.time()
        and (not require_current or time.time() < expires),
        "DRONE_IDENTITY_CREDENTIAL_EXPIRED",
    )
    planned = plan["identity"]["environments"][environment]
    for actor, account in value["accounts"].items():
        require(
            set(account) == {"subject", "email", "tenant_id", "role", "password", "totp_secret"}
            and all(
                account[key] == planned["accounts"][actor][key]
                for key in ["subject", "email", "tenant_id", "role"]
            )
            and isinstance(account["password"], str)
            and 1 <= len(account["password"]) <= 256
            and re.fullmatch(r"[A-Z2-7]{16,128}", account["totp_secret"]),
            "DRONE_IDENTITY_CREDENTIAL_BINDING",
        )
    bypass = value["portal_bypass"]
    require(
        bypass is None
        and planned["portal_bypass_sha256"] is None
        or isinstance(bypass, str)
        and 1 <= len(bypass) <= 8192
        and all(33 <= ord(char) <= 126 for char in bypass)
        and hashlib.sha256(bypass.encode()).hexdigest() == planned["portal_bypass_sha256"],
        "DRONE_PORTAL_PROTECTION_CUSTODY",
    )
    return value


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def renew_credentials(runner, record):
    """Refresh one unchanged private fixture inside its verified owner operation.

    Runtime/provider configuration and signed release records are not modified.
    An uncertain replacement retains its intent and cannot be retried implicitly.
    """
    import oracle_drone as d

    require(
        os.geteuid() == 0 and not os.getenv("GITHUB_ACTIONS") and runner.phase in {"staging", "deploy"},
        "DRONE_OWNER_CREDENTIAL_RENEWAL_ONLY",
    )
    key, kind = (
        ("context_id", "context") if runner.phase == "staging" else ("operation_id", "deployment-intent")
    )
    require(
        record["binding"] == runner.binding
        and record["id"] == runner.context.get(key)
        and record["kind"] == kind
        and record in runner.context_records,
        "DRONE_CREDENTIAL_SIGNED_OPERATION_REQUIRED",
    )
    authority = d.canonical(runner.context_records)
    authority_digest = hashlib.sha256(authority).hexdigest()
    deadline = min(datetime.fromisoformat(item["expires_at"]) for item in runner.context_records)
    environment = "staging" if runner.phase == "staging" else "production"
    slot = runner.plan["slots"][environment]
    source = Path(slot["fixture_file"])
    folder = d.private(runner.folder, directory=True)
    lock = folder / "identity-credential-renewal.lock"
    if lock.exists():
        d.private(lock)
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        require(
            info.st_uid == 0 and info.st_nlink == 1 and info.st_mode & 0o077 == 0,
            "DRONE_CREDENTIAL_RENEWAL_LOCK_CUSTODY",
        )
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held_source = d.private(source)
        require(held_source.stat().st_nlink == 1, "DRONE_IDENTITY_PRIVATE_INPUT_BOUND")
        raw = held_source.read_bytes()
        require(0 < len(raw) <= 128 * 1024, "DRONE_IDENTITY_PRIVATE_INPUT_BOUND")
        value = validate_credentials(
            json.loads(raw, object_pairs_hook=unique),
            runner.plan,
            runner.binding,
            environment,
            require_current=False,
        )
        previous = hashlib.sha256(raw).hexdigest()
        identifier = str(UUID(record["id"]))
        prefix = folder / ("identity-credentials-" + identifier + "-" + runner.phase)
        receipt_path, intent_path = prefix.with_suffix(".json"), prefix.with_suffix(".intent.json")
        if receipt_path.exists():
            receipt = read(receipt_path)
            require(
                receipt["binding"] == runner.binding
                and receipt["operation_id"] == identifier
                and receipt["environment"] == environment
                and receipt["phase"] == runner.phase
                and receipt["authority_sha256"] == authority_digest
                and receipt["payload_sha256"] == slot["configuration_sha256"][str(source)]
                and receipt["envelope_sha256"] == previous,
                "DRONE_CREDENTIAL_RENEWAL_ALREADY_USED",
            )
            credentials(runner.plan, runner.binding, environment)
            return
        require(not intent_path.exists(), "DRONE_CREDENTIAL_RENEWAL_UNCERTAIN_INSPECT_ONLY")
        current = datetime.now(timezone.utc)
        expires = min(current + timedelta(hours=1), deadline)
        require(current < expires, "DRONE_CREDENTIAL_RENEWAL_CONTEXT_EXPIRED")
        value.update(created_at=current.isoformat(), expires_at=expires.isoformat())
        encoded = d.canonical(value)
        intended = hashlib.sha256(encoded).hexdigest()
        fixed = {
            "binding": runner.binding,
            "operation_id": identifier,
            "phase": runner.phase,
            "authority_sha256": authority_digest,
            "environment": environment,
            "payload_sha256": slot["configuration_sha256"][str(source)],
            "previous_envelope_sha256": previous,
            "envelope_sha256": intended,
            "created_at": value["created_at"],
            "expires_at": value["expires_at"],
            "provider_requests": 0,
            "runtime_configuration_changed": False,
            "records_issued": 0,
        }
        d.write(intent_path, {**fixed, "automatic_retry": False})
        sync_directory(folder)
        file, temporary = tempfile.mkstemp(prefix=".drone-identity-lease-", dir=source.parent)
        try:
            with os.fdopen(file, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            require(
                runner.check_context() == record and d.canonical(runner.context_records) == authority,
                "DRONE_CREDENTIAL_RENEWAL_AUTHORITY_CHANGED",
            )
            require(
                d.private(source).stat().st_nlink == 1 and d.digest(source) == previous,
                "DRONE_CREDENTIAL_CUSTODY_CHANGED_DURING_RENEWAL",
            )
            os.replace(temporary, source)
            sync_directory(source.parent)
        finally:
            Path(temporary).unlink(missing_ok=True)
        credentials(runner.plan, runner.binding, environment)
        d.write(receipt_path, fixed)
        sync_directory(folder)
    finally:
        os.close(descriptor)


def request(runner, environment):
    held = credentials(runner.plan, runner.binding, environment)
    entry = runner.plan["identity"]["environments"][environment]
    return {
        "profile": PROFILE,
        "environment": environment,
        "origin": runner.plan["slots"][environment]["origin"],
        "issuer": entry["issuer"],
        "client_id": entry["client_id"],
        "accounts": held["accounts"],
        "expires_at": held["expires_at"],
        "portal_bypass": held["portal_bypass"],
    }


def validate_session(value, identity, actor):
    account = identity["accounts"][actor]
    require(
        set(value) == {"schema_version", "origin", "issuer", "subject", "role", "tenant_id", "csrf", "cookie"}
        and value["schema_version"] == 1
        and value["origin"] == identity["origin"]
        and value["issuer"] == identity["issuer"]
        and all(value[key] == account[key] for key in ["subject", "role", "tenant_id"])
        and re.fullmatch(r"[A-Za-z0-9_-]{20,128}", value["csrf"]),
        "DRONE_IDENTITY_SESSION_BINDING",
    )
    cookie = value["cookie"]
    require(
        set(cookie) == {"name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite"}
        and cookie["name"] == "drone_session"
        and re.fullmatch(r"[A-Za-z0-9_-]{20,128}", cookie["value"])
        and cookie["domain"] == urlsplit(identity["origin"]).hostname
        and cookie["path"] == "/"
        and cookie["httpOnly"] is True
        and cookie["secure"] is True
        and cookie["sameSite"] == "Strict"
        and type(cookie["expires"]) in {int, float}
        and time.time() < cookie["expires"] <= time.time() + 86400,
        "DRONE_HOST_ONLY_IDENTITY_COOKIE_REQUIRED",
    )


def login(runner, client, environment, actor):
    import oracle_drone as d

    identity = request(runner, environment)
    require(
        actor in ACTORS and client.api == client.origin == identity["origin"],
        "DRONE_IDENTITY_COOKIE_ORIGIN_MUST_NOT_BE_REWRITTEN",
    )
    payload = {"identity": identity, "actor": actor, "drone_bypass": None}
    bypass = runner.plan["slots"][environment].get("protection_bypass_file")
    if bypass:
        payload["drone_bypass"] = d.private(bypass).read_text().strip()
    arguments = runner.probe_arguments(entrypoint="node") + [BROWSER]
    raw = runner.run(arguments, d.canonical(payload), timeout=180, persist_stdout=False)
    require(0 < len(raw) <= 65536, "DRONE_IDENTITY_SESSION_RESPONSE_BOUND")
    value = json.loads(raw, object_pairs_hook=unique)
    require(
        time.time() < datetime.fromisoformat(identity["expires_at"]).timestamp(),
        "DRONE_IDENTITY_CREDENTIAL_EXPIRED",
    )
    validate_session(value, identity, actor)
    cookie = value["cookie"]
    client.jar.clear()
    client.jar.set_cookie(
        http.cookiejar.Cookie(
            version=0,
            name=cookie["name"],
            value=cookie["value"],
            port=None,
            port_specified=False,
            domain=cookie["domain"],
            domain_specified=False,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=True,
            expires=int(cookie["expires"]),
            discard=False,
            comment=None,
            comment_url=None,
            rest={"HttpOnly": None, "SameSite": "Strict"},
            rfc2109=False,
        )
    )
    client.csrf = value["csrf"]
    # The application cookie stays on its actual browser host. The exact-host
    # protection credential is sent only on direct no-redirect requests to it.
    client.protection_bypass = payload["drone_bypass"]
    observed = client.call("/api/v1/auth/me")
    require(
        observed["identity_managed"] is True
        and observed["global_admin"] is False
        and observed["identity_subject"] == value["subject"]
        and observed["tenant_id"] == value["tenant_id"]
        and observed["role"] == value["role"]
        and observed["csrf"] == value["csrf"]
        and observed["email"] == identity["accounts"][actor]["email"],
        "DRONE_LIVE_IDENTITY_SESSION_CHANGED",
    )
    return observed

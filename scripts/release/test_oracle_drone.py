"""Release refusal and private-evidence tests; these do not claim hosted acceptance."""

from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import http.cookiejar
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import oracle_drone as d


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.custody = patch.object(d, "private", side_effect=lambda p, **_: Path(p))
        self.custody.start()
        self.addCleanup(self.custody.stop)

        def file(name, value):
            path = self.root / name
            path.write_bytes(value if isinstance(value, bytes) else d.canonical(value))
            return str(path)

        api = "sha256:" + "a" * 64
        self.binding = {
            "repository": "DruHustle/onesa-drone",
            "component": "backend",
            "candidate_commit": "b" * 40,
            "source_tree": "c" * 40,
            "target_environment": "production",
            "artifact_digest": api,
            "configuration_sha256": {},
        }
        self.plan = {
            "bindings": {"backend": self.binding},
            "slots": {},
            "api_image": api,
            "database_image": "sha256:" + "d" * 64,
            "probe_image": "sha256:" + "e" * 64,
            "build_manifests": {},
            "security_reports": {},
            "tool_sha256": {},
            "physical_authority": False,
            "synthetic_data_only": True,
        }
        for slot, (origin, api_origin, port) in d.ORIGINS.items():
            path = file(slot + ".env", slot.encode())
            hashes = {path: d.digest(path)}
            self.plan["slots"][slot] = {
                "origin": origin,
                "api_origin": api_origin,
                "port": port,
                "project": "onesa-drone-oracle-" + slot,
                "configuration_sha256": hashes,
            }
            self.binding["configuration_sha256"][slot] = hashlib.sha256(d.canonical(hashes)).hexdigest()
        self.plan["source_archive"] = file("source.tar", b"source fixture")
        self.binding["source_sha256"] = d.digest(self.plan["source_archive"])
        native = file(
            "backend.json",
            {
                "source_commit": "b" * 40,
                "source_tree": "c" * 40,
                "image_id": api,
                "architecture": "arm64",
                "runtime_image_ids": {
                    self.plan[k]: self.plan[k] for k in ["api_image", "database_image", "probe_image"]
                },
            },
        )
        self.plan["build_manifests"]["backend"] = native
        self.binding["build_sha256"] = d.digest(native)
        self.plan["runtime_images"] = json.loads(Path(native).read_text())["runtime_image_ids"].copy()
        self.rebind_native()
        for index, image in enumerate([self.plan[k] for k in ["api_image", "database_image", "probe_image"]]):
            path = file(
                str(index) + ".json",
                {
                    "Metadata": {"ImageID": image},
                    "Results": [{"Target": "OS"}],
                    "CreatedAt": datetime.now(timezone.utc).isoformat(),
                },
            )
            self.plan["security_reports"][image] = {"path": path, "sha256": d.digest(path)}

    def rebind_native(self):
        native = self.plan["build_manifests"]["backend"]
        self.binding["build_sha256"] = d.digest(native)
        for slot, config in self.plan["slots"].items():
            config["configuration_sha256"][native] = d.digest(native)
            self.binding["configuration_sha256"][slot] = hashlib.sha256(
                d.canonical(config["configuration_sha256"])
            ).hexdigest()

    def test_classic_and_manifest_runtime_ids_remain_bound_to_scanned_config(self):
        path = Path(self.plan["build_manifests"]["backend"])
        native = json.loads(path.read_text())
        api = self.plan["api_image"]
        native["runtime_image_ids"][api] = "sha256:" + "f" * 64
        path.write_bytes(d.canonical(native))
        self.rebind_native()
        d.validate_plan(self.plan, self.binding)  # classic store uses configuration ID
        self.plan["runtime_images"][api] = native["runtime_image_ids"][api]
        d.validate_plan(self.plan, self.binding)  # containerd store uses manifest ID
        self.plan["runtime_images"][api] = "sha256:" + "1" * 64
        with self.assertRaisesRegex(ValueError, "not the scanned native artifact"):
            d.validate_plan(self.plan, self.binding)

    def change_report(self, **changes):
        entry = self.plan["security_reports"][self.plan["api_image"]]
        path = Path(entry["path"])
        value = json.loads(path.read_text()) | changes
        path.write_bytes(d.canonical(value))
        entry["sha256"] = d.digest(path)

    def test_exact_plan_is_accepted(self):
        d.validate_plan(self.plan, self.binding)

    def test_cross_environment_or_changed_private_config_refused(self):
        self.plan["slots"]["staging"]["api_origin"] = d.ORIGINS["production"][1]
        with self.assertRaisesRegex(ValueError, "routing"):
            d.validate_plan(self.plan, self.binding)
        self.plan["slots"]["staging"]["api_origin"] = d.ORIGINS["staging"][1]
        Path(next(iter(self.plan["slots"]["staging"]["configuration_sha256"]))).write_text("changed")
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            d.validate_plan(self.plan, self.binding)

    def test_foreign_component_or_changed_artifact_refused(self):
        binding = deepcopy(self.binding)
        binding["repository"] = "DruHustle/onesa-robot"
        with self.assertRaisesRegex(ValueError, "Foreign"):
            d.validate_plan(self.plan, binding)
        self.plan["api_image"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(ValueError, "mapping|native runtime"):
            d.validate_plan(self.plan, self.binding)

    def test_empty_failed_foreign_or_expired_scan_refused(self):
        for change, message in [
            ({"Results": []}, "security gate"),
            ({"Results": [{"Vulnerabilities": [{"Severity": "HIGH"}]}]}, "security gate"),
            ({"Results": [{}], "Metadata": {"ImageID": "wrong"}}, "different image"),
            (
                {
                    "Metadata": {"ImageID": self.plan["api_image"]},
                    "CreatedAt": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                },
                "expired",
            ),
        ]:
            self.change_report(**change)
            with self.assertRaisesRegex(ValueError, message):
                d.validate_plan(self.plan, self.binding)

    def test_physical_or_real_data_scope_refused(self):
        for key, value in [("physical_authority", True), ("synthetic_data_only", False)]:
            original = self.plan[key]
            self.plan[key] = value
            with self.assertRaisesRegex(ValueError, "Simulation-only"):
                d.validate_plan(self.plan, self.binding)
            self.plan[key] = original


class PrivacyTests(unittest.TestCase):
    def test_api_requests_identify_the_owner_client(self):
        client = d.Client(*reversed(d.ORIGINS["staging"][:2]))
        response = io.BytesIO(b'{"mode":"simulation"}')
        response.status = 200
        with patch.object(client.opener, "open", return_value=response) as request:
            self.assertEqual(client.call("/api/v1/health"), {"mode": "simulation"})
        self.assertEqual(request.call_args.args[0].get_header("User-agent"), "OnesaDroneOwnerQualification/1")

    def test_stale_or_foreign_provider_alias_cannot_qualify(self):
        runner = object.__new__(d.Runner)
        runner.plan = {"vercel_project_id": "prj_fixture"}
        valid = {"alias": "drone.onesa.eu", "projectId": "prj_fixture", "deploymentId": "dpl_fixture"}
        with patch.object(runner, "vercel", return_value=d.canonical(valid)):
            runner.alias_identity("production", "dpl_fixture")
        for key, value in [
            ("alias", "drone-staging.onesa.eu"),
            ("projectId", "prj_foreign"),
            ("deploymentId", "dpl_stale"),
        ]:
            with patch.object(runner, "vercel", return_value=d.canonical(valid | {key: value})):
                with self.assertRaisesRegex(ValueError, "Canonical frontend alias"):
                    runner.alias_identity("production", "dpl_fixture")

    def runner(self, folder):
        runner = object.__new__(d.Runner)
        runner.folder, runner.count = Path(folder), 0
        return runner

    def test_backup_plaintext_and_stdin_are_not_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = self.runner(folder)
            secret = b"private fixture password"
            dump = b"sensitive PostgreSQL archive"
            with patch.object(
                d.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, dump, b"")
            ) as invoke:
                self.assertEqual(runner.run(["pg_dump"], data=secret, persist_stdout=False), dump)
                self.assertEqual(invoke.call_args.kwargs["input"], secret)
            output = b"".join(p.read_bytes() for p in Path(folder).iterdir())
            self.assertNotIn(secret, output)
            self.assertNotIn(dump, output)
            self.assertIn(b"plaintext_not_persisted", output)

    def test_interruption_has_no_retry_and_no_plaintext_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = self.runner(folder)
            with patch.object(
                d.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("pg_dump", 1, output=b"private dump"),
            ):
                with self.assertRaisesRegex(ValueError, "inspect retained"):
                    runner.run(["pg_dump"], persist_stdout=False)
            output = b"".join(p.read_bytes() for p in Path(folder).iterdir())
            self.assertNotIn(b"private dump", output)
            self.assertIn(b'"automatic_retry":false', output)

    def test_custody_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "alias"
            path.symlink_to("/etc/passwd")
            with self.assertRaises(ValueError):
                d.private(path)

    def test_foreign_http_destination_refused(self):
        with self.assertRaisesRegex(ValueError, "Foreign HTTP"):
            d.Client("https://example.com", d.ORIGINS["production"][0])

    def test_successful_login_without_secure_host_cookie_refused(self):
        client = d.Client(*reversed(d.ORIGINS["staging"][:2]))
        with patch.object(client, "call", return_value={"csrf": "fixture"}):
            with self.assertRaisesRegex(ValueError, "Secure private session"):
                client.login({"email": "fixture@example.test", "password": "fixture"})
        cookie = http.cookiejar.Cookie(
            0,
            "drone_session",
            "fixture",
            None,
            False,
            ".onesa.eu",
            True,
            True,
            "/",
            True,
            True,
            None,
            True,
            None,
            None,
            {"HttpOnly": None},
            False,
        )
        client.jar.set_cookie(cookie)
        with patch.object(client, "call", return_value={"csrf": "fixture"}):
            with self.assertRaisesRegex(ValueError, "Secure private session"):
                client.login({"email": "fixture@example.test", "password": "fixture"})

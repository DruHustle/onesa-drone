"""Real Ed25519 signatures and disposable SQLite reservations, never live authority."""

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import oracle_drone as d
import oracle_owner as o
from test_oracle_owner import SCHEMA


class SignedContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "signing.pem"
            subprocess.run(
                [o.OPENSSL, "genpkey", "-algorithm", "ED25519", "-out", str(path)],
                check=True,
                capture_output=True,
            )
            cls.secret = path.read_bytes()
            cls.public = subprocess.check_output([o.OPENSSL, "pkey", "-in", str(path), "-pubout"])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path.home() if os.getuid() == 0 else None)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.root.chmod(0o700)
        self.installed = self.root / "installed"
        self.installed.mkdir(mode=0o700)
        self.executable = self.installed / "oracle_drone.py"
        self.executable.write_bytes(Path(d.__file__).read_bytes())
        self.verifier = self.installed / "oracle_owner.py"
        self.verifier.write_bytes(Path(o.__file__).read_bytes())
        self.executable.chmod(0o600)
        self.verifier.chmod(0o600)
        self.store_root = self.root / "issuer"
        self.store_root.mkdir(mode=0o700)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir(mode=0o700)
        self.anchor = self.root / "anchor.json"
        self.binding = {
            "repository": "DruHustle/onesa-drone",
            "component": "backend",
            "candidate_commit": "a" * 40,
            "source_tree": "b" * 40,
            "source_sha256": "c" * 64,
            "build_sha256": "d" * 64,
            "artifact_digest": "sha256:" + "e" * 64,
            "configuration_sha256": {"staging": "f" * 64, "production": "1" * 64},
            "target_environment": "production",
        }
        profile = {
            "qualification_attempt_limit": 1,
            "runners": {
                phase: {
                    "path": str(self.executable),
                    "sha256": d.digest(self.executable),
                    "timeout_seconds": 1800,
                }
                for phase in d.CHECKS
            },
            "required_checks": {phase: sorted(checks) for phase, checks in d.CHECKS.items()},
        }
        policy = {"schema_version": 1, "components": {"DruHustle/onesa-drone:backend": profile}}
        self.put_file("policy.json", d.canonical(policy))
        self.put_file("signing.pem", self.secret)
        self.put_file("public.pem", self.public)
        self.trust = {
            "installation_id": str(uuid4()),
            "key_id": d.digest(self.store_root / "public.pem"),
            "policy_sha256": d.digest(self.store_root / "policy.json"),
            "verifier_sha256": d.digest(self.verifier),
            "openssl_sha256": d.digest(o.OPENSSL),
            "runner_root": str(self.installed),
        }
        self.put_file("trust.json", d.canonical(self.trust))
        self.registry = {
            "schema_version": 1,
            "installations": {
                str(self.store_root): {
                    **{
                        key: self.trust[key]
                        for key in ["installation_id", "key_id", "policy_sha256", "verifier_sha256"]
                    },
                    "active": True,
                }
            },
        }
        self.anchor.write_bytes(d.canonical(self.registry))
        self.anchor.chmod(0o600)
        self.db = sqlite3.connect(self.store_root / "records.sqlite", isolation_level=None)
        self.db.executescript(SCHEMA)
        self.addCleanup(self.db.close)
        (self.store_root / "records.sqlite").chmod(0o600)
        # Use the real installed issuer's record constructor and OpenSSL signing.
        # No GitHub or host commissioning lookup is made by this disposable issuer.
        self.issuer = object.__new__(o.Store)
        self.issuer.root, self.issuer.trust, self.issuer.db = self.store_root, self.trust, self.db
        self.issuer.clock = lambda: datetime.now(timezone.utc) - timedelta(seconds=5)
        self.context = self.issuer.put(
            "context",
            self.binding,
            {
                "qualification_environment": "staging",
                "state": "ISSUED_UNUSED",
                "ci": [],
            },
        )["record"]
        self.qualification = self.issuer.put(
            "qualification", self.binding, {"ci": []}, parent=self.context["id"]
        )["record"]
        self.attempt = self.issuer.put(
            "authorization-attempt", self.binding, {"decision": "PENDING"}, parent=self.qualification["id"]
        )["record"]
        self.authorization = self.issuer.put(
            "authorization",
            self.binding,
            {
                "decision": "approve",
                "physical_hardware_authorized": False,
                "attempt_id": self.attempt["id"],
            },
            parent=self.qualification["id"],
        )["record"]
        self.operation = self.issuer.put(
            "deployment-intent",
            self.binding,
            {
                "authorization": self.authorization["id"],
                "provider_request_budget": 1,
                "automatic_retry": False,
            },
            parent=self.authorization["id"],
        )["record"]
        self.db.execute("INSERT INTO contexts VALUES(?, 'consumed')", (self.context["id"],))
        self.db.execute(
            "INSERT INTO deployments VALUES(?,?,?,'request-recorded')",
            (
                self.operation["id"],
                self.authorization["id"],
                self.qualification["id"],
            ),
        )
        self.runner = object.__new__(d.Runner)
        self.runner.plan = {"issuer_store": str(self.store_root)}
        self.runner.binding, self.runner.folder, self.runner.count = self.binding, self.evidence, 0
        self.runner.phase = "deploy"
        self.runner.context = {
            "operation_id": self.operation["id"],
            "authorization_id": self.authorization["id"],
        }
        self.enterContext(patch.object(d, "__file__", str(self.executable)))
        self.enterContext(patch.object(d, "private", side_effect=self.fixture_private))

    def put_file(self, name, data):
        path = self.store_root / name
        path.write_bytes(data)
        path.chmod(0o600)

    def fixture_private(self, path, directory=False):
        # Keep fixture mode/link checks real while replacing only the production
        # root UID/ancestor assumption and the fixed external registry path.
        path = self.anchor if str(path) == "/etc/onesa/oracle-release-trust.json" else Path(path)
        self.assertTrue(path.is_relative_to(self.root), "No real host custody may be accessed")
        info = path.lstat()
        self.assertFalse(path.is_symlink())
        self.assertEqual(info.st_uid, os.getuid())
        self.assertEqual(info.st_mode & 0o077, 0)
        self.assertTrue(
            stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
        )
        return path

    def envelope(self, identifier):
        return json.loads(
            self.db.execute("SELECT envelope FROM records WHERE id=?", (identifier,)).fetchone()[0]
        )

    def alter(self, identifier, mutation, *, resign=True):
        envelope = self.envelope(identifier)
        record = envelope["record"]
        mutation(record)
        if resign:
            signature = o.signed_bytes(
                self.store_root / "signing.pem", self.store_root / "public.pem", d.canonical(record)
            )
            envelope["signature"]["value"] = base64.b64encode(signature).decode()
        self.db.execute(
            "UPDATE records SET envelope=?,parent=?,kind=?,created=? WHERE id=?",
            (
                d.canonical(envelope).decode(),
                record["parent"],
                record["kind"],
                record["issued_at"],
                identifier,
            ),
        )

    def test_deploy_verifies_operation_first_and_all_real_signed_ancestors(self):
        observed = self.runner.check_context()
        self.assertEqual(observed, self.operation)
        self.assertEqual(self.runner.context_records[0]["id"], self.operation["id"])
        self.assertEqual(
            {item["kind"] for item in self.runner.context_records},
            {
                "deployment-intent",
                "authorization",
                "qualification",
                "context",
                "authorization-attempt",
            },
        )
        self.assertEqual(self.runner.count, 5, "Every signature must be checked with real OpenSSL")

    def test_staging_requires_reserved_context_and_operations_use_exact_variants(self):
        self.runner.phase = "staging"
        self.runner.context = {"context_id": self.context["id"]}
        with self.assertRaisesRegex(ValueError, "reserved/consumed"):
            self.runner.check_context()
        self.db.execute("UPDATE contexts SET state='reserved'")
        self.assertEqual(self.runner.check_context(), self.context)
        self.assertEqual(self.runner.context_records, [self.context])
        self.runner.phase = "operations"
        self.assertEqual(self.runner.check_context(), self.context)
        self.db.execute("UPDATE contexts SET state='consumed'")
        for context, expected in [
            ({"qualification_id": self.qualification["id"], "owner_decision": "approve"}, self.qualification),
            ({"authorization_id": self.authorization["id"], "before_deployment": True}, self.authorization),
        ]:
            self.runner.context = context
            self.assertEqual(self.runner.check_context(), expected)

    def test_extra_or_ambiguous_phase_keys_cannot_select_another_signed_record(self):
        for phase, context in [
            ("staging", {"context_id": self.context["id"], "operation_id": self.operation["id"]}),
            ("deploy", {"authorization_id": self.authorization["id"]}),
            ("deploy", {**self.runner.context, "context_id": self.context["id"]}),
            ("production", {"operation_id": self.operation["id"], "read_only": False}),
            ("production", {"operation_id": self.operation["id"], "read_only": 1}),
            ("operations", {"qualification_id": self.qualification["id"], "owner_decision": "deny"}),
            ("operations", {"authorization_id": self.authorization["id"], "before_deployment": 1}),
            ("unrecognized", {"context_id": self.context["id"]}),
        ]:
            self.runner.phase, self.runner.context = phase, context
            with self.subTest(phase=phase, context=context), self.assertRaises(ValueError):
                self.runner.check_context()

    def test_revoked_ancestors_never_renew_through_a_valid_top_signature(self):
        for item in [self.context, self.qualification, self.attempt, self.authorization, self.operation]:
            self.db.execute("UPDATE records SET revoked=1 WHERE id=?", (item["id"],))
            with self.subTest(kind=item["kind"]), self.assertRaisesRegex(ValueError, "missing/revoked"):
                self.runner.check_context()
            self.assertEqual(self.runner.context_records, [])
            self.db.execute("UPDATE records SET revoked=0 WHERE id=?", (item["id"],))

    def test_expired_and_tampered_ancestor_signatures_are_rejected(self):
        identifier = self.qualification["id"]
        original = self.envelope(identifier)
        expired = datetime.now(timezone.utc) - timedelta(hours=2)
        self.alter(
            identifier,
            lambda row: row.update(
                issued_at=expired.isoformat(), expires_at=(expired + timedelta(hours=1)).isoformat()
            ),
        )
        with self.assertRaisesRegex(ValueError, "ancestor expired"):
            self.runner.check_context()
        self.db.execute(
            "UPDATE records SET envelope=?,created=? WHERE id=?",
            (
                d.canonical(original).decode(),
                original["record"]["issued_at"],
                identifier,
            ),
        )
        self.alter(identifier, lambda row: row["details"].update(caller_pass=True), resign=False)
        with self.assertRaisesRegex(ValueError, "Command failed"):
            self.runner.check_context()

    def test_wrong_reservation_state_parent_or_caller_authorization_is_refused(self):
        for state in ["deployed-unverified", "accepted"]:
            self.db.execute("UPDATE deployments SET state=?", (state,))
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "reservation"):
                self.runner.check_context()
        self.db.execute("UPDATE deployments SET state='request-recorded',qualification=?", (str(uuid4()),))
        with self.assertRaisesRegex(ValueError, "reservation"):
            self.runner.check_context()
        self.db.execute("UPDATE deployments SET qualification=?", (self.qualification["id"],))
        self.runner.context["authorization_id"] = str(uuid4())
        with self.assertRaisesRegex(ValueError, "Caller authorization"):
            self.runner.check_context()
        self.runner.context["authorization_id"] = self.authorization["id"]
        self.db.execute("DELETE FROM deployments")
        with self.assertRaisesRegex(ValueError, "reservation"):
            self.runner.check_context()

    def test_signed_foreign_source_or_owner_provenance_is_not_trusted(self):
        original = self.envelope(self.operation["id"])
        for mutate in [
            lambda row: row["binding"].update(candidate_commit="0" * 40),
            lambda row: row["owner_provenance"].update(owner="someone-else"),
            lambda row: row["owner_provenance"].update(installation_id=str(uuid4())),
            lambda row: row.update(workflow_run_id=123),
            lambda row: row.update(execution_context="github-actions"),
            lambda row: row["details"].update(provider_request_budget=2),
            lambda row: row["details"].update(automatic_retry=True),
        ]:
            self.db.execute(
                "UPDATE records SET envelope=? WHERE id=?",
                (d.canonical(original).decode(), self.operation["id"]),
            )
            self.alter(self.operation["id"], mutate)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.runner.check_context()

    def test_newer_decision_invalidates_deployment_without_modifying_old_signatures(self):
        self.issuer.put(
            "authorization-attempt", self.binding, {"decision": "PENDING"}, parent=self.qualification["id"]
        )
        with self.assertRaisesRegex(ValueError, "superseded"):
            self.runner.check_context()

    def test_historical_production_inspection_preserves_expired_revoked_chain(self):
        for item in [self.context, self.qualification, self.attempt, self.authorization, self.operation]:
            past = datetime.now(timezone.utc) - timedelta(hours=2)
            self.alter(
                item["id"],
                lambda row: row.update(
                    issued_at=past.isoformat(), expires_at=(past + timedelta(hours=1)).isoformat()
                ),
            )
        self.db.execute("UPDATE records SET revoked=1")
        self.db.execute("UPDATE deployments SET state='accepted'")
        self.runner.phase = "production"
        self.runner.context = {"operation_id": self.operation["id"], "read_only": True}
        self.assertEqual(self.runner.check_context()["id"], self.operation["id"])
        self.assertEqual(len(self.runner.context_records), 5)
        self.assertEqual(self.db.execute("SELECT state FROM deployments").fetchone(), ("accepted",))

    def test_commissioning_and_installed_source_pins_are_checked(self):
        for field in ["installation_id", "key_id", "verifier_sha256", "policy_sha256"]:
            changed = deepcopy(self.registry)
            changed["installations"][str(self.store_root)][field] = "changed"
            self.anchor.write_bytes(d.canonical(changed))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Uncommissioned"):
                self.runner.check_context()
        self.anchor.write_bytes(d.canonical(self.registry))
        self.executable.write_bytes(
            self.executable.read_bytes() + b"\n# changed synthetic installed source\n"
        )
        with self.assertRaisesRegex(ValueError, "runner source changed"):
            self.runner.check_context()

    def test_revocation_during_crypto_verification_is_rechecked_before_return(self):
        original = self.runner.run
        calls = 0

        def concurrent(*args, **kwargs):
            nonlocal calls
            result = original(*args, **kwargs)
            calls += 1
            if calls == 5:
                self.db.execute("UPDATE records SET revoked=1 WHERE id=?", (self.context["id"],))
            return result

        self.runner.run = concurrent
        with self.assertRaisesRegex(ValueError, "authority changed during verification"):
            self.runner.check_context()
        self.assertEqual(self.runner.context_records, [])


class IsolatedCliTests(unittest.TestCase):
    def test_owner_python_isolated_invocation_loads_pinned_sibling_and_enters_guarded_cli(self):
        path = Path(d.__file__).resolve()
        result = subprocess.run(
            [sys.executable, "-I", str(path), "production"],
            input=json.dumps({"binding": {}, "context": {}}),
            text=True,
            capture_output=True,
            timeout=15,
            env={"PATH": os.defpath, "GITHUB_ACTIONS": "true"},
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr, "Drone owner runner failed; inspect private evidence; no automatic retry.\n"
        )
        self.assertNotIn("ModuleNotFoundError", result.stderr)


if __name__ == "__main__":
    unittest.main()

"""Synthetic rollback gate boundaries; these fixtures confer no hosted authority.

The owner signature verifier and real application workflows have separate tests.
Here, already-verified record-shaped fixtures exercise the gate's exact binding,
private receipt reuse and refusal paths without a daemon or live database.
"""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import oracle_drone as d
import oracle_drone_identity as identity
import oracle_drone_rollback as rollback
import oracle_drone_rollback_containers as custody
import test_oracle_drone_identity as fixtures


class RollbackFixture(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.IdentityPlanTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.plan, self.binding, self.root = (
            self.fixture.plan,
            self.fixture.binding,
            self.fixture.root,
        )
        self.recovery = rollback.read(self.plan["rollback_file"])

    def save_recovery(self, value):
        path = Path(self.plan["rollback_file"])
        path.write_bytes(d.canonical(value))
        for slot in self.plan["slots"].values():
            slot["configuration_sha256"][str(path)] = d.digest(path)

    def baseline(self, environment, kind, changes):
        path = Path(self.plan["identity"]["environments"][environment]["baseline_" + kind + "_file"])
        values = identity.values(path)
        values.update(changes)
        path.write_text("".join(key + "=" + value + "\n" for key, value in values.items()))
        self.plan["slots"][environment]["configuration_sha256"][str(path)] = d.digest(path)
        self.recovery["environments"][environment][kind + "_sha256"] = d.digest(path)
        self.save_recovery(self.recovery)
        return path

    def image_rows(self):
        rows = {}
        for key, user, source in [
            ("api_image", "10001:10001", self.binding["candidate_commit"]),
            ("database_image", "70:70", None),
        ]:
            image = self.plan["runtime_images"][self.plan[key]]
            rows[image] = {
                "Id": image,
                "Architecture": "arm64",
                "Os": "linux",
                "Config": {
                    "User": user,
                    "Volumes": {"/var/lib/postgresql/data": {}} if key == "database_image" else {},
                    "Labels": {} if source is None else {"org.onesa.source-commit": source},
                },
            }
        for entry in self.recovery["environments"].values():
            rows[entry["image_id"]] = {
                "Id": entry["image_id"],
                "Architecture": "arm64",
                "Os": "linux",
                "Config": {
                    "User": "10001:10001",
                    "Volumes": {},
                    "Labels": {"org.onesa.source-commit": entry["source_commit"]},
                },
            }
        return rows

    def inspect_images(self, *args, **_kwargs):
        self.assertEqual(args[:2], ("image", "inspect"))
        self.assertEqual(len(args), 3)
        return d.canonical([self.image_rows()[args[2]]])

    def runner(self, phase="operations"):
        runner = object.__new__(d.Runner)
        runner.plan, runner.binding = self.plan, self.binding
        runner.folder = self.root / "rollback-gate-fixture"
        runner.folder.mkdir(mode=0o700, exist_ok=True)
        runner.component, runner.phase = "backend", phase
        original = {"id": str(uuid4()), "kind": "context", "binding": deepcopy(self.binding)}
        runner.context = {"context_id": original["id"]}
        runner.context_records = [deepcopy(original)]
        runner.check_context = Mock()
        return runner, original

    def receipts(self, runner, original):
        folder = rollback.proof_folder(runner, original)
        folder.mkdir(mode=0o700)
        with patch.object(custody, "docker", side_effect=self.inspect_images):
            image_ids = rollback.images(self.plan, self.binding, self.recovery)
        cleanup = {
            "operation_id": original["id"],
            "isolated_containers_removed": True,
            "private_inputs_retained": False,
            "containers": {},
            "release_authority": False,
        }
        self.write_json(folder / "cleanup.json", cleanup)
        proof = {
            "schema_version": 1,
            "profile": rollback.PROFILE,
            "binding": deepcopy(self.binding),
            "operation_id": original["id"],
            "context_sha256": hashlib.sha256(d.canonical(original)).hexdigest(),
            "images": image_ids,
            "recovery": deepcopy(self.recovery),
            "schema": {"0001": "1" * 64, "0002-identity": "2" * 64},
            "environments": {
                environment: {
                    **entry,
                    "runtime_role": "drone_login",
                    "native_worker": True,
                    "checks": {key: "PASS" for key in rollback.CHECKS},
                }
                for environment, entry in self.recovery["environments"].items()
            },
            "status": "PASS",
            "synthetic_database_restore": "PASS",
            "production_writes": 0,
            "hosted_database_connections": 0,
            "network": "none",
            "isolated_containers_removed": True,
            "cleanup_sha256": d.digest(folder / "cleanup.json"),
        }
        self.write_json(folder / "receipt.json", proof)
        return folder, proof, cleanup

    @staticmethod
    def write_json(path, value):
        path.write_bytes(d.canonical(value))
        path.chmod(0o600)

    @staticmethod
    def summary(folder, original):
        return {
            "profile": rollback.PROFILE,
            "qualification_context_id": original["id"],
            "receipt_sha256": d.digest(folder / "receipt.json"),
        }

    def add_qualification_fixture(self, runner, summary):
        runner.context_records.append(
            {
                "id": str(uuid4()),
                "kind": "qualification",
                "binding": deepcopy(self.binding),
                "details": {"staging": {"observations": {"rollback_proof": deepcopy(summary)}}},
            }
        )


class ProfileTests(RollbackFixture):
    def test_both_slots_require_the_exact_candidate_and_retained_configuration(self):
        self.assertEqual(rollback.profile(self.plan, self.binding), self.recovery)
        for environment in ["staging", "production"]:
            for kind in ["runtime", "migrator"]:
                changed = deepcopy(self.recovery)
                changed["environments"][environment][kind + "_sha256"] = "0" * 64
                self.save_recovery(changed)
                with self.subTest(environment=environment, kind=kind):
                    with self.assertRaisesRegex(ValueError, "RETAINED_CONFIGURATION_CHANGED"):
                        rollback.profile(self.plan, self.binding)
        self.save_recovery(self.recovery)

    def test_shared_profile_and_source_bound_retained_strategy_are_mandatory(self):
        for selected in [None, "first-release-disable-only", "unknown"]:
            plan = deepcopy(self.plan)
            plan["qualification_profile"] = selected
            with self.subTest(profile=selected), self.assertRaisesRegex(ValueError, "SHARED_ROLLBACK"):
                rollback.profile(plan, self.binding)
        for field, value in [
            ("strategy", "first-release-disable-only"),
            ("source_commit", "0" * 40),
            ("preserve_database", False),
            ("physical_interfaces_disabled", False),
            ("environments", {"staging": self.recovery["environments"]["staging"]}),
        ]:
            changed = deepcopy(self.recovery)
            changed[field] = value
            self.save_recovery(changed)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "SOURCE_BOUND_RETAINED"):
                rollback.profile(self.plan, self.binding)

    def test_retained_source_image_and_no_provisioning_are_enforced_per_slot(self):
        for environment in ["staging", "production"]:
            for field, value in [("source_commit", "main"), ("image_id", "sha256:" + "0" * 64)]:
                changed = deepcopy(self.recovery)
                changed["environments"][environment][field] = value
                self.save_recovery(changed)
                with self.subTest(environment=environment, field=field):
                    with self.assertRaisesRegex(ValueError, "RETAINED_SOURCE_IMAGE_SCOPE"):
                        rollback.profile(self.plan, self.binding)
            self.save_recovery(self.recovery)
            for changes in [{"previous_image": "sha256:" + "0" * 64}, {"provision_database": True}]:
                plan = deepcopy(self.plan)
                plan["slots"][environment].update(changes)
                with self.subTest(environment=environment, changes=changes):
                    with self.assertRaisesRegex(ValueError, "RETAINED_SOURCE_IMAGE_SCOPE"):
                        rollback.profile(plan, self.binding)

    def test_rollback_file_must_be_configuration_bound_in_both_slots(self):
        for environment in ["staging", "production"]:
            for missing in [False, True]:
                plan = deepcopy(self.plan)
                hashes = plan["slots"][environment]["configuration_sha256"]
                if missing:
                    del hashes[plan["rollback_file"]]
                else:
                    hashes[plan["rollback_file"]] = "0" * 64
                with self.subTest(environment=environment, missing=missing):
                    with self.assertRaisesRegex(ValueError, "NOT_CONFIGURATION_BOUND"):
                        rollback.profile(plan, self.binding)

    def test_changed_baseline_bytes_are_rejected_even_when_file_still_exists(self):
        path = Path(self.plan["identity"]["environments"]["production"]["baseline_migrator_file"])
        path.write_text(path.read_text() + "UNREVIEWED=value\n")
        with self.assertRaisesRegex(ValueError, "RETAINED_CONFIGURATION_CHANGED"):
            rollback.profile(self.plan, self.binding)

    def test_identity_enabled_baseline_is_rejected_even_if_its_hash_is_rebound(self):
        for environment in ["staging", "production"]:
            for kind in ["runtime", "migrator"]:
                self.baseline(environment, kind, {"ONESA_IDENTITY_ENABLED": "true"})
                with self.subTest(environment=environment, kind=kind):
                    with self.assertRaisesRegex(ValueError, "RETAINED_IDENTITY_MUST_BE_DISABLED"):
                        rollback.profile(self.plan, self.binding)
                self.baseline(environment, kind, {"ONESA_IDENTITY_ENABLED": "false"})
        self.assertEqual(rollback.profile(self.plan, self.binding), self.recovery)

    def test_native_simulation_and_external_provider_boundary_cannot_be_rebound(self):
        for key, value in [
            ("APP_ORIGIN", "https://foreign.example.test"),
            ("COOKIE_SECURE", "false"),
            ("SIMULATION_WORKER", "false"),
            ("ONESA_AI_URL", "https://provider.example.test"),
            ("ONESA_AI_DELEGATED_SESSION", "synthetic-private-session"),
        ]:
            path = Path(self.plan["identity"]["environments"]["staging"]["baseline_runtime_file"])
            before = identity.values(path).get(key, "")
            self.baseline("staging", "runtime", {key: value})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "SIMULATION_CONFIGURATION"):
                rollback.profile(self.plan, self.binding)
            self.baseline("staging", "runtime", {key: before})

    def test_injected_environment_contains_no_live_database_or_provider_credentials(self):
        private_values = {
            "DATABASE_URL": "postgresql+psycopg://owner:synthetic-password@live.example.test/live",
            "ONESA_AI_API_KEY": "synthetic-api-key",
            "ONESA_AI_DELEGATED_SESSION": "synthetic-delegated-session",
            "ONESA_AI_DELEGATED_CSRF": "synthetic-csrf",
            "ONESA_IDENTITY_CLIENT_SECRET": "synthetic-client-secret",
            "ONESA_IDENTITY_ENCRYPTION_KEY": "synthetic-encryption-key",
            "UNRELATED_SECRET": "synthetic-unrelated-secret",
        }
        self.baseline("production", "runtime", {**private_values, "ONESA_AI_PROVIDER": "disabled"})
        for database in rollback.DATABASES:
            values = dict(
                value.split("=", 1)
                for value in rollback.native_environment(self.plan, "production", database)
            )
            self.assertEqual(
                values["DATABASE_URL"],
                "postgresql+psycopg://drone_login@/" + database + "?host=/var/run/postgresql",
            )
            self.assertEqual(values["ONESA_IDENTITY_ENABLED"], "false")
            self.assertEqual(values["ONESA_AI_PROVIDER"], "disabled")
            self.assertEqual(values["APP_ORIGIN"], "http://localhost:3400")
            self.assertEqual(values["SIMULATION_WORKER"], "true")
            for secret in private_values.values():
                self.assertNotIn(secret, json.dumps(values))
        with patch.object(identity, "values") as read:
            with self.assertRaisesRegex(ValueError, "DATABASE_SCOPE"):
                rollback.native_environment(self.plan, "production", "live")
            read.assert_not_called()

    def test_both_host_helpers_must_remain_source_pinned(self):
        for name in ["oracle_drone_rollback.py", "oracle_drone_rollback_containers.py"]:
            plan = deepcopy(self.plan)
            plan["tool_sha256"].pop(str(Path(identity.__file__).with_name(name)))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "MATCHED_IDENTITY_HELPER"):
                identity.source_profile(plan, self.binding)


class ImageTests(RollbackFixture):
    def setUp(self):
        super().setUp()
        self.recovery["environments"]["production"].update(
            image_id="sha256:" + "9" * 64, source_commit="8" * 40
        )
        self.plan["slots"]["production"]["previous_image"] = "sha256:" + "9" * 64
        self.save_recovery(self.recovery)

    def test_actual_readback_matches_each_scoped_image_source_and_runtime_user(self):
        with patch.object(custody, "docker", side_effect=self.inspect_images) as inspect:
            actual = rollback.images(self.plan, self.binding, self.recovery)
        self.assertEqual(set(actual), {"candidate", "database", "staging", "production"})
        for environment in ["staging", "production"]:
            self.assertEqual(
                actual[environment]["image_id"], self.recovery["environments"][environment]["image_id"]
            )
            self.assertEqual(
                actual[environment]["source_commit"],
                self.recovery["environments"][environment]["source_commit"],
            )
            self.assertEqual(actual[environment]["user"], "10001:10001")
        self.assertEqual(actual["database"]["user"], "70:70")
        self.assertEqual(inspect.call_count, 4)

    def test_relabelled_foreign_root_or_writable_image_is_refused(self):
        candidate = self.plan["runtime_images"][self.plan["api_image"]]
        database = self.plan["runtime_images"][self.plan["database_image"]]
        for reference in [candidate, database, self.recovery["environments"]["production"]["image_id"]]:
            for field, value in [
                ("Id", "sha256:" + "0" * 64),
                ("Architecture", "amd64"),
                ("Os", "windows"),
                ("User", "0:0"),
                ("Volumes", {"/foreign": {}}),
                ("source", "0" * 40),
            ]:
                if reference == database and field == "source":
                    continue
                rows = self.image_rows()
                target = rows[reference]
                if field in {"User", "Volumes"}:
                    target["Config"][field] = value
                elif field == "source":
                    target["Config"]["Labels"]["org.onesa.source-commit"] = value
                else:
                    target[field] = value
                with self.subTest(reference=reference, field=field):
                    with patch.object(
                        custody, "docker", side_effect=lambda *args, **_: d.canonical([rows[args[2]]])
                    ):
                        with self.assertRaisesRegex(ValueError, "IMMUTABLE_IMAGE_OR_SOURCE_CHANGED"):
                            rollback.images(self.plan, self.binding, self.recovery)

    def test_missing_or_ambiguous_daemon_image_readback_cannot_qualify(self):
        for rows in [[], [{}, {}]]:
            with self.subTest(rows=rows), patch.object(custody, "docker", return_value=d.canonical(rows)):
                with self.assertRaisesRegex(ValueError, "ROLLBACK_IMAGE_MISSING"):
                    rollback.images(self.plan, self.binding, self.recovery)


class GateTests(RollbackFixture):
    def setUp(self):
        super().setUp()
        self.real_qualify = rollback.qualify
        self.enterContext(patch.object(rollback.os, "geteuid", return_value=0))
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.inspect = self.enterContext(patch.object(custody, "docker", side_effect=self.inspect_images))
        self.rehearse = self.enterContext(patch.object(rollback, "qualify"))

    def test_staging_gate_runs_the_reserved_rehearsal_and_returns_exact_receipt_hash(self):
        runner, original = self.runner("staging")
        folder, _, _ = self.receipts(runner, original)
        actual = rollback.gate(runner)
        self.assertEqual(actual, self.summary(folder, original))
        self.rehearse.assert_called_once()
        self.assertEqual(self.rehearse.call_args.args[:3], (runner, self.recovery, original))
        self.assertEqual(runner.check_context.call_count, 2)

    def test_rehearsal_requires_exact_reserved_staging_context_before_any_container(self):
        runner, original = self.runner("staging")
        for phase, context in [
            ("production", {"context_id": original["id"]}),
            ("deploy", {"context_id": original["id"]}),
            ("staging", {"context_id": str(uuid4())}),
            ("staging", {"context_id": original["id"], "approved": True}),
        ]:
            runner.phase, runner.context = phase, context
            with (
                self.subTest(phase=phase, context=context),
                patch.object(custody, "OwnedContainer") as create,
            ):
                with self.assertRaisesRegex(ValueError, "STAGING_ONLY"):
                    self.real_qualify(runner, self.recovery, original, {})
                create.assert_not_called()
        self.assertFalse(list(runner.folder.iterdir()))

    def test_owner_and_verified_context_guards_precede_rehearsal(self):
        runner, _ = self.runner()
        for uid, environment in [(10001, {}), (0, {"GITHUB_ACTIONS": "true"})]:
            with (
                patch.object(rollback.os, "geteuid", return_value=uid),
                patch.dict(os.environ, environment, clear=True),
            ):
                with self.assertRaisesRegex(ValueError, "OWNER_ONLY"):
                    rollback.gate(runner)
        runner.check_context.side_effect = ValueError("synthetic revoked reservation")
        with self.assertRaisesRegex(ValueError, "revoked reservation"):
            rollback.gate(runner)
        self.inspect.assert_not_called()
        self.rehearse.assert_not_called()

    def test_exactly_one_matching_verified_context_is_required(self):
        runner, original = self.runner()
        foreign = deepcopy(original)
        foreign["binding"]["candidate_commit"] = "0" * 40
        for records in [[], [foreign], [original, deepcopy(original)]]:
            runner.context_records = records
            with self.subTest(records=records), self.assertRaisesRegex(ValueError, "SIGNED_CONTEXT_REQUIRED"):
                rollback.gate(runner)
        self.rehearse.assert_not_called()
        self.inspect.assert_not_called()

    def test_later_phases_reuse_signed_summary_without_running_any_application(self):
        runner, original = self.runner()
        folder, _, _ = self.receipts(runner, original)
        expected = self.summary(folder, original)
        self.add_qualification_fixture(runner, expected)
        for phase in ["operations", "deploy", "production"]:
            runner.phase = phase
            with self.subTest(phase=phase):
                self.assertEqual(rollback.gate(runner), expected)
        self.rehearse.assert_not_called()
        self.assertTrue(all(call.args[:2] == ("image", "inspect") for call in self.inspect.call_args_list))

    def test_context_only_operations_reuse_same_private_proof_without_rerunning(self):
        runner, original = self.runner("operations")
        folder, _, _ = self.receipts(runner, original)
        self.assertEqual(rollback.gate(runner), self.summary(folder, original))
        self.rehearse.assert_not_called()

    def test_production_cannot_recreate_a_missing_staging_proof(self):
        runner, _ = self.runner("production")
        with self.assertRaises(FileNotFoundError):
            rollback.gate(runner)
        self.rehearse.assert_not_called()
        self.assertTrue(all(call.args[:2] == ("image", "inspect") for call in self.inspect.call_args_list))

    def test_any_rehearsal_failure_prevents_receipt_acceptance(self):
        runner, original = self.runner("staging")
        self.receipts(runner, original)
        self.rehearse.side_effect = ValueError("synthetic cleanup outcome uncertain")
        with self.assertRaisesRegex(ValueError, "cleanup outcome uncertain"):
            rollback.gate(runner)

    def test_changed_receipt_scope_schema_data_or_isolation_is_rejected(self):
        runner, original = self.runner()
        folder, proof, _ = self.receipts(runner, original)
        changes = [
            ("profile", "first-release-disable-only"),
            ("binding", {**self.binding, "candidate_commit": "0" * 40}),
            ("operation_id", str(uuid4())),
            ("context_sha256", "0" * 64),
            ("images", {}),
            ("recovery", {}),
            ("status", "FAIL"),
            ("synthetic_database_restore", "NOT_RUN"),
            ("production_writes", 1),
            ("production_writes", False),
            ("hosted_database_connections", 1),
            ("hosted_database_connections", False),
            ("network", "bridge"),
            ("isolated_containers_removed", False),
            ("cleanup_sha256", "0" * 64),
            ("schema", {"0001": "1" * 64}),
            ("environments", {"staging": proof["environments"]["staging"]}),
        ]
        for field, value in changes:
            self.write_json(folder / "receipt.json", {**proof, field: value})
            with (
                self.subTest(field=field, value=value),
                self.assertRaisesRegex(ValueError, "EXACT_STAGING_ROLLBACK_PROOF"),
            ):
                rollback.gate(runner)
        self.rehearse.assert_not_called()

    def test_cleanup_uncertainty_cannot_be_hidden_by_rehashing_the_receipt(self):
        runner, original = self.runner()
        folder, proof, cleanup = self.receipts(runner, original)
        for changes in [
            {"operation_id": str(uuid4())},
            {"isolated_containers_removed": False},
            {"private_inputs_retained": True},
        ]:
            self.write_json(folder / "cleanup.json", {**cleanup, **changes})
            self.write_json(
                folder / "receipt.json", {**proof, "cleanup_sha256": d.digest(folder / "cleanup.json")}
            )
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(ValueError, "EXACT_STAGING_ROLLBACK_PROOF"),
            ):
                rollback.gate(runner)

    def test_retained_workflow_and_native_role_evidence_must_be_complete_per_slot(self):
        runner, original = self.runner()
        folder, proof, _ = self.receipts(runner, original)
        for environment in ["staging", "production"]:
            for changes in [
                {"source_commit": "0" * 40},
                {"image_id": "sha256:" + "0" * 64},
                {"runtime_sha256": "0" * 64},
                {"migrator_sha256": "0" * 64},
                {"runtime_role": "drone_owner"},
                {"native_worker": False},
                {"checks": {key: "PASS" for key in rollback.CHECKS - {"native_delivery"}}},
                {
                    "checks": {
                        **proof["environments"][environment]["checks"],
                        "native_delivery": "CHECKPOINT_ONLY",
                    }
                },
            ]:
                changed = deepcopy(proof)
                changed["environments"][environment].update(changes)
                self.write_json(folder / "receipt.json", changed)
                with self.subTest(environment=environment, changes=changes):
                    with self.assertRaisesRegex(ValueError, "RETAINED_WORKFLOW_PROOF"):
                        rollback.gate(runner)

    def test_signed_qualification_hash_detects_even_otherwise_valid_receipt_edits(self):
        runner, original = self.runner("production")
        folder, proof, _ = self.receipts(runner, original)
        self.add_qualification_fixture(runner, self.summary(folder, original))
        proof["schema"]["0002-identity"] = "9" * 64
        self.write_json(folder / "receipt.json", proof)
        with self.assertRaisesRegex(ValueError, "SIGNED_ROLLBACK_PROOF_CHANGED"):
            rollback.gate(runner)
        self.rehearse.assert_not_called()

    def test_different_or_duplicate_qualification_summary_is_rejected(self):
        runner, original = self.runner("production")
        folder, _, _ = self.receipts(runner, original)
        correct = self.summary(folder, original)
        for summary in [
            {**correct, "receipt_sha256": "0" * 64},
            {**correct, "qualification_context_id": str(uuid4())},
        ]:
            runner.context_records = [deepcopy(original)]
            self.add_qualification_fixture(runner, summary)
            with (
                self.subTest(summary=summary),
                self.assertRaisesRegex(ValueError, "SIGNED_ROLLBACK_PROOF_CHANGED"),
            ):
                rollback.gate(runner)
        runner.context_records = [deepcopy(original)]
        self.add_qualification_fixture(runner, correct)
        self.add_qualification_fixture(runner, correct)
        with self.assertRaisesRegex(ValueError, "SIGNED_ROLLBACK_PROOF_CHANGED"):
            rollback.gate(runner)

    def test_authority_is_rechecked_after_receipt_inspection(self):
        runner, original = self.runner()
        self.receipts(runner, original)
        calls = []

        def verify():
            calls.append(True)
            if len(calls) == 2:
                runner.context_records[0]["revision"] = "changed-during-inspection"

        runner.check_context.side_effect = verify
        with self.assertRaisesRegex(ValueError, "ROLLBACK_AUTHORITY_CHANGED"):
            rollback.gate(runner)

    def test_failed_gate_stops_backend_and_frontend_before_provider_or_runtime_changes(self):
        runner, _ = self.runner()
        self.plan["retained_artifacts"] = {}
        for phase in ["staging", "deploy"]:
            for component in ["backend", "frontend"]:
                runner.phase, runner.component = phase, component
                with self.subTest(phase=phase, component=component):
                    with (
                        patch.object(runner, "preserved"),
                        patch.object(runner, "frontend_files"),
                        patch.object(runner, "run"),
                        patch.object(runner, "initialize_backend") as backend,
                        patch.object(runner, "deploy_frontend") as frontend,
                        patch.object(
                            rollback, "gate", side_effect=ValueError("synthetic rollback gate refusal")
                        ),
                    ):
                        with self.assertRaisesRegex(ValueError, "rollback gate refusal"):
                            runner.execute()
                        backend.assert_not_called()
                        frontend.assert_not_called()
        self.assertFalse(list(runner.folder.glob("*-intent.json")))


class ApplicationReceiptTests(RollbackFixture):
    def test_seed_checkpoint_cannot_be_presented_as_a_completed_retained_delivery(self):
        schema = {"0001": "1" * 64, "0002-identity": "2" * 64}
        fixture = {"accounts": {"synthetic": True}}
        result = {"schema": schema, "fixture": fixture, "checks": {key: "PASS" for key in rollback.CHECKS}}
        container = Mock()
        container.run.return_value = d.canonical(result)
        with self.assertRaisesRegex(ValueError, "RETAINED_IMAGE_COMPATIBILITY_FAILED"):
            rollback.application(
                container, self.plan, "staging", "drone_rollback_seed_test", schema, fixture, "seed"
            )
        result["checks"]["native_delivery"] = "CHECKPOINT_ONLY"
        container.run.return_value = d.canonical(result)
        rollback.application(
            container, self.plan, "staging", "drone_rollback_seed_test", schema, fixture, "seed"
        )
        with self.assertRaisesRegex(ValueError, "RETAINED_IMAGE_COMPATIBILITY_FAILED"):
            rollback.application(
                container, self.plan, "production", "drone_rollback_restored_test", schema, fixture, "verify"
            )

    def test_retained_response_requires_exact_schema_and_restricted_runtime_check(self):
        schema = {"0001": "1" * 64, "0002-identity": "2" * 64}
        fixture = {"accounts": {"synthetic": True}}
        result = {"schema": schema, "fixture": fixture, "checks": {key: "PASS" for key in rollback.CHECKS}}
        for change in [
            {"schema": {**schema, "0002-identity": "0" * 64}},
            {"checks": {**result["checks"], "restricted_runtime": "NOT_RUN"}},
        ]:
            container = Mock()
            container.run.return_value = d.canonical({**result, **change})
            with (
                self.subTest(change=change),
                self.assertRaisesRegex(ValueError, "RETAINED_IMAGE_COMPATIBILITY_FAILED"),
            ):
                rollback.application(
                    container,
                    self.plan,
                    "production",
                    "drone_rollback_restored_test",
                    schema,
                    fixture,
                    "verify",
                )


if __name__ == "__main__":
    unittest.main()

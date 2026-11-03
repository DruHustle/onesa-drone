"""Synthetic identity release boundaries; no hosted credentials or provider calls."""

import base64
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import oracle_drone as d
import oracle_drone_identity as i
import test_oracle_drone as baseline


class IdentityPlanTests(unittest.TestCase):
    def setUp(self):
        previous = baseline.PlanTests()
        previous.setUp()
        self.addCleanup(previous.doCleanups)
        self.base, self.plan, self.binding, self.root = (
            previous,
            previous.plan,
            previous.binding,
            previous.root,
        )
        self.plan["qualification_profile"] = i.PROFILE
        self.plan["identity"] = {
            key: self.binding[key] for key in ["candidate_commit", "source_tree", "source_sha256"]
        }
        self.plan["identity"]["environments"] = {}
        self.plan["tool_sha256"] = {
            str(Path(i.__file__).with_name(name)): d.digest(Path(i.__file__).with_name(name))
            for name in [
                "oracle_drone_identity.py",
                "oracle_drone_identity_browser.mjs",
                "probe_policy.mjs",
                "oracle_drone_rollback.py",
                "oracle_drone_rollback_containers.py",
            ]
        }
        self.held, self.runtime = {}, {}
        for index, (environment, slot) in enumerate(self.plan["slots"].items(), 1):

            def file(name, value):
                path = self.root / (environment + "-" + name)
                path.write_bytes(d.canonical(value) if isinstance(value, dict) else value.encode())
                path.chmod(0o600)
                slot["configuration_sha256"][str(path)] = d.digest(path)
                return str(path)

            tenant, foreign = str(uuid4()), str(uuid4())
            accounts = {
                actor: {
                    "subject": str(uuid4()),
                    "email": actor + "-" + environment + "@example.test",
                    "tenant_id": foreign if actor == "foreign" else tenant,
                    "role": "viewer" if actor == "viewer" else "admin",
                }
                for actor in i.ACTORS
            }
            secret, encryption = str(index) * 48, base64.urlsafe_b64encode(bytes([index]) * 32).decode()
            entry = {
                "issuer": (
                    "https://portal.onesa.eu"
                    if environment == "production"
                    else "https://onesa-company-portal-fixture.vercel.app"
                )
                + "/api/v1/identity",
                "client_id": "onesa-drone-" + environment,
                "client_secret_sha256": hashlib.sha256(secret.encode()).hexdigest(),
                "encryption_key_sha256": hashlib.sha256(encryption.encode()).hexdigest(),
                "portal_bypass_sha256": None,
                "accounts": accounts,
            }
            self.plan["identity"]["environments"][environment] = entry
            current = {"APP_ORIGIN": slot["origin"], "COOKIE_SECURE": "true", "SIMULATION_WORKER": "true"}
            additions = {
                "ONESA_IDENTITY_ENABLED": "true",
                "ONESA_IDENTITY_ISSUER": entry["issuer"],
                "ONESA_IDENTITY_CLIENT_ID": entry["client_id"],
                "ONESA_IDENTITY_CLIENT_SECRET": secret,
                "ONESA_IDENTITY_CALLBACK": slot["origin"] + "/api/v1/auth/identity/callback",
                "ONESA_IDENTITY_ENCRYPTION_KEY": encryption,
            }

            def encode(data):
                return "\n".join(key + "=" + value for key, value in data.items()) + "\n"

            images = {}
            for role, variable in [
                ("runtime", "DRONE_RUNTIME_ENV_FILE"),
                ("migrator", "DRONE_MIGRATOR_ENV_FILE"),
            ]:
                previous_values = {
                    **current,
                    "DATABASE_URL": "postgresql+psycopg://" + role + "@fixture/" + environment,
                }
                entry["baseline_" + role + "_file"] = file("before-" + role + ".env", encode(previous_values))
                images[variable] = file(role + ".env", encode({**previous_values, **additions}))
            self.runtime[environment] = images["DRONE_RUNTIME_ENV_FILE"]
            slot["images_env"] = file("images.env", encode(images))
            created = datetime.now(timezone.utc)
            held = {
                "schema_version": 1,
                "candidate_commit": self.binding["candidate_commit"],
                "scope": "existing-owned-synthetic-identities",
                "created_at": created.isoformat(),
                "expires_at": (created + timedelta(minutes=45)).isoformat(),
                "portal_bypass": None,
                "accounts": {
                    actor: {
                        **account,
                        "password": "synthetic-private-password",
                        "totp_secret": "JBSWY3DPEHPK3PXP",
                    }
                    for actor, account in accounts.items()
                },
            }
            self.held[environment] = held
            slot["fixture_file"] = file("fixtures.json", held)
            slot["configuration_sha256"][slot["fixture_file"]] = i.credential_pin(slot["fixture_file"])
            slot.update(provision_database=False, previous_image="sha256:" + "f" * 64)
            Path(slot["initialization_file"]).write_bytes(
                d.canonical({"provision_database": False, "previous_image": slot["previous_image"]})
            )
            slot["configuration_sha256"][slot["initialization_file"]] = d.digest(slot["initialization_file"])
        rollback_path = self.root / "identity-rollback.json"
        rollback_path.write_bytes(
            d.canonical(
                {
                    "source_commit": self.binding["candidate_commit"],
                    "strategy": "retained-identity-disabled-v1",
                    "preserve_database": True,
                    "physical_interfaces_disabled": True,
                    "environments": {
                        environment: {
                            "source_commit": "e" * 40,
                            "image_id": slot["previous_image"],
                            "runtime_sha256": slot["configuration_sha256"][
                                self.plan["identity"]["environments"][environment]["baseline_runtime_file"]
                            ],
                            "migrator_sha256": slot["configuration_sha256"][
                                self.plan["identity"]["environments"][environment]["baseline_migrator_file"]
                            ],
                        }
                        for environment, slot in self.plan["slots"].items()
                    },
                }
            )
        )
        rollback_path.chmod(0o600)
        self.plan["rollback_file"] = str(rollback_path)
        for slot in self.plan["slots"].values():
            slot["configuration_sha256"][str(rollback_path)] = d.digest(rollback_path)
        self.base.rebind_native()

    def test_explicit_exact_source_profile_preserves_all_nonidentity_values(self):
        d.validate_plan(self.plan, self.binding)
        self.assertEqual(i.source_profile(self.plan, self.binding), self.plan["identity"])
        path = Path(self.runtime["staging"])
        path.write_text(path.read_text().replace("SIMULATION_WORKER=true", "SIMULATION_WORKER=false"))
        self.plan["slots"]["staging"]["configuration_sha256"][str(path)] = d.digest(path)
        self.base.rebind_native()
        with self.assertRaisesRegex(ValueError, "UNRELATED_CONFIGURATION_CHANGED"):
            d.validate_plan(self.plan, self.binding)

    def renewal(self):
        runner = object.__new__(d.Runner)
        runner.plan, runner.binding, runner.folder = self.plan, self.binding, self.root
        runner.phase = "staging"
        identifier = str(uuid4())
        runner.context = {"context_id": identifier}
        record = {
            "id": identifier,
            "kind": "context",
            "binding": self.binding,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=35)).isoformat(),
        }
        runner.context_records = [record]
        runner.check_context = Mock(return_value=record)
        real_stat = os.fstat

        def fixture_stat(descriptor):
            value = list(real_stat(descriptor))
            value[4] = 0  # Only this disposable lock simulates owner/root custody.
            return os.stat_result(value)

        self.enterContext(patch.object(i.os, "fstat", side_effect=fixture_stat))
        self.enterContext(patch.object(i.os, "geteuid", return_value=0))
        self.enterContext(patch.dict(i.os.environ, {}, clear=True))
        return runner, record

    def test_expired_credentials_renew_only_timestamps_within_verified_operation(self):
        runner, record = self.renewal()
        path = Path(self.plan["slots"]["staging"]["fixture_file"])
        value = i.read(path)
        created = datetime.now(timezone.utc) - timedelta(hours=2)
        value.update(created_at=created.isoformat(), expires_at=(created + timedelta(minutes=45)).isoformat())
        path.write_bytes(d.canonical(value))
        before_binding = deepcopy(self.binding)
        production = Path(self.plan["slots"]["production"]["fixture_file"]).read_bytes()
        d.validate_plan(self.plan, self.binding)
        with self.assertRaisesRegex(ValueError, "CREDENTIAL_EXPIRED"):
            i.credentials(self.plan, self.binding, "staging")
        i.renew_credentials(runner, record)
        observed = i.credentials(self.plan, self.binding, "staging")
        self.assertEqual(observed["expires_at"], record["expires_at"])
        self.assertEqual(i.credential_payload_digest(observed), i.credential_payload_digest(value))
        self.assertEqual(self.binding, before_binding)
        self.assertEqual(Path(self.plan["slots"]["production"]["fixture_file"]).read_bytes(), production)
        accepted = path.read_bytes()
        i.renew_credentials(runner, record)
        self.assertEqual(path.read_bytes(), accepted, "repeated inspection must not extend the lease")
        runner.check_context.assert_called_once()

    def test_credential_payload_changes_cannot_hide_inside_a_renewed_envelope(self):
        runner, record = self.renewal()
        path = Path(self.plan["slots"]["staging"]["fixture_file"])
        value = i.read(path)
        value["accounts"]["operator"]["password"] = "different-synthetic-password"
        path.write_bytes(d.canonical(value))
        with self.assertRaisesRegex(ValueError, "CREDENTIAL_CUSTODY"):
            i.renew_credentials(runner, record)
        runner.check_context.assert_not_called()
        self.assertFalse(list(self.root.glob("identity-credentials-*.json")))

    def test_uncertain_renewal_and_changed_owner_context_cannot_replace_fixture(self):
        runner, record = self.renewal()
        path = Path(self.plan["slots"]["staging"]["fixture_file"])
        original = path.read_bytes()
        runner.check_context.return_value = {**record, "id": str(uuid4())}
        with self.assertRaisesRegex(ValueError, "RENEWAL_AUTHORITY_CHANGED"):
            i.renew_credentials(runner, record)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len(list(self.root.glob("identity-credentials-*.intent.json"))), 1)
        runner.check_context.return_value = record
        with self.assertRaisesRegex(ValueError, "UNCERTAIN_INSPECT_ONLY"):
            i.renew_credentials(runner, record)
        self.assertEqual(path.read_bytes(), original)

    def test_concurrent_custody_change_and_read_only_phases_cannot_renew(self):
        runner, record = self.renewal()
        path = Path(self.plan["slots"]["staging"]["fixture_file"])
        original = path.read_bytes()
        runner.phase = "production"
        with self.assertRaisesRegex(ValueError, "OWNER_CREDENTIAL_RENEWAL_ONLY"):
            i.renew_credentials(runner, record)
        self.assertEqual(path.read_bytes(), original)
        runner.phase = "staging"

        def changed():
            value = i.read(path)
            value["accounts"]["operator"]["password"] = "concurrent-synthetic-password"
            path.write_bytes(d.canonical(value))
            return record

        runner.check_context.side_effect = changed
        with self.assertRaisesRegex(ValueError, "CUSTODY_CHANGED_DURING_RENEWAL"):
            i.renew_credentials(runner, record)
        self.assertEqual(i.read(path)["accounts"]["operator"]["password"], "concurrent-synthetic-password")

    def test_renewal_expires_with_earliest_signed_ancestor(self):
        runner, record = self.renewal()
        ancestor = {
            **record,
            "id": str(uuid4()),
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        }
        runner.context_records.append(ancestor)
        i.renew_credentials(runner, record)
        self.assertEqual(
            i.credentials(self.plan, self.binding, "staging")["expires_at"], ancestor["expires_at"]
        )

    def test_changed_signed_ancestor_cannot_replace_credentials_under_same_top_record(self):
        runner, record = self.renewal()
        path = Path(self.plan["slots"]["staging"]["fixture_file"])
        original = path.read_bytes()
        ancestor = {**record, "id": str(uuid4())}
        runner.context_records.append(ancestor)

        def changed():
            runner.context_records = [record, {**ancestor, "id": str(uuid4())}]
            return record

        runner.check_context.side_effect = changed
        with self.assertRaisesRegex(ValueError, "RENEWAL_AUTHORITY_CHANGED"):
            i.renew_credentials(runner, record)
        self.assertEqual(path.read_bytes(), original)

    def test_renewal_cannot_use_authorization_or_replace_before_durable_intent(self):
        runner, record = self.renewal()
        path = Path(self.plan["slots"]["staging"]["fixture_file"])
        original = path.read_bytes()
        runner.context = {"authorization_id": record["id"]}
        with self.assertRaisesRegex(ValueError, "SIGNED_OPERATION_REQUIRED"):
            i.renew_credentials(runner, record)
        runner.context = {"context_id": record["id"]}
        with patch.object(i, "sync_directory", side_effect=OSError("synthetic fsync interruption")):
            with self.assertRaises(OSError):
                i.renew_credentials(runner, record)
        self.assertEqual(path.read_bytes(), original)
        runner.check_context.assert_not_called()
        with self.assertRaisesRegex(ValueError, "UNCERTAIN_INSPECT_ONLY"):
            i.renew_credentials(runner, record)

    def test_absent_profile_cannot_consume_identity_config_or_stale_helpers(self):
        self.plan.pop("qualification_profile")
        with self.assertRaisesRegex(ValueError, "EXPLICIT_IDENTITY_PROFILE"):
            i.source_profile(self.plan, self.binding)
        self.plan["qualification_profile"] = i.PROFILE
        key = next(iter(self.plan["tool_sha256"]))
        self.plan["tool_sha256"][key] = "0" * 64
        with self.assertRaisesRegex(ValueError, "MATCHED_IDENTITY_HELPER"):
            i.source_profile(self.plan, self.binding)

    def test_foreign_source_shared_principal_or_provisioning_reset_is_rejected(self):
        for change, reason in [
            (lambda p: p["identity"].update(candidate_commit="e" * 40), "SOURCE_BINDING"),
            (lambda p: p["slots"]["staging"].update(provision_database=True), "PRESERVES_EXISTING_DATABASES"),
            (
                lambda p: p["identity"]["environments"]["staging"]["accounts"]["viewer"].update(
                    subject=p["identity"]["environments"]["staging"]["accounts"]["operator"]["subject"]
                ),
                "SEPARATE_ENVIRONMENT_PRINCIPALS",
            ),
            (
                lambda p: p["identity"]["environments"]["production"].update(
                    issuer="https://foreign.example.test/api/v1/identity"
                ),
                "ISSUER_SCOPE",
            ),
        ]:
            plan = deepcopy(self.plan)
            change(plan)
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                i.source_profile(plan, self.binding)

    def test_wrong_callback_encryption_or_source_custody_rejected_before_login(self):
        prepared = i.values(self.runtime["staging"])
        entry = self.plan["identity"]["environments"]["staging"]
        for key, value in [
            ("ONESA_IDENTITY_ENABLED", "false"),
            ("ONESA_IDENTITY_CALLBACK", "https://foreign.example.test/callback"),
            ("ONESA_IDENTITY_ENCRYPTION_KEY", "a" * 44),
            ("ONESA_IDENTITY_CLIENT_SECRET", "wrong"),
        ]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "CONFIGURATION_CHANGED"):
                i.configuration(entry, self.plan["slots"]["staging"]["origin"], {**prepared, key: value})
        value = self.held["staging"]
        value["expires_at"] = value["created_at"]
        Path(self.plan["slots"]["staging"]["fixture_file"]).write_bytes(d.canonical(value))
        with self.assertRaisesRegex(ValueError, "CREDENTIAL_EXPIRED"):
            i.credentials(self.plan, self.binding, "staging")

    def test_real_shared_session_keeps_original_cookie_host_and_revalidates_subject_role(self):
        runner = object.__new__(d.Runner)
        runner.plan, runner.binding = self.plan, self.binding
        identity = i.request(runner, "staging")
        account = identity["accounts"]["operator"]
        value = {
            "schema_version": 1,
            "origin": identity["origin"],
            "issuer": identity["issuer"],
            "subject": account["subject"],
            "role": account["role"],
            "tenant_id": account["tenant_id"],
            "csrf": "a" * 32,
            "cookie": {
                "name": "drone_session",
                "value": "b" * 43,
                "domain": "drone-staging.onesa.eu",
                "path": "/",
                "expires": datetime.now(timezone.utc).timestamp() + 300,
                "httpOnly": True,
                "secure": True,
                "sameSite": "Strict",
            },
        }
        client = d.Client(identity["origin"], identity["origin"])
        observed = {
            "identity_managed": True,
            "global_admin": False,
            "identity_subject": account["subject"],
            "role": account["role"],
            "tenant_id": account["tenant_id"],
            "csrf": value["csrf"],
            "email": account["email"],
        }
        with (
            patch.object(runner, "run", return_value=d.canonical(value)) as run,
            patch.object(client, "call", return_value=observed),
        ):
            self.assertEqual(i.login(runner, client, "staging", "operator"), observed)
            self.assertFalse(run.call_args.kwargs["persist_stdout"])
            self.assertFalse(list(client.jar)[0].domain_specified)
        with self.assertRaisesRegex(ValueError, "ORIGIN_MUST_NOT_BE_REWRITTEN"):
            i.login(runner, d.Client(d.ORIGINS["staging"][1], identity["origin"]), "staging", "operator")
        with (
            patch.object(runner, "run", return_value=d.canonical(value)),
            patch.object(client, "call", return_value={**observed, "global_admin": True}),
        ):
            with self.assertRaisesRegex(ValueError, "LIVE_IDENTITY_SESSION_CHANGED"):
                i.login(runner, client, "staging", "operator")

    def test_identity_migration_adds_only_session_grants_and_never_bootstraps_accounts(self):
        runner = object.__new__(d.Runner)
        runner.plan, runner.binding = self.plan, self.binding
        with (
            patch.object(runner, "run", return_value=("sha256:" + "f" * 64).encode()),
            patch.object(runner, "identity"),
            patch.object(runner, "verify_storage", return_value={"counts": {"missions": 2}}),
            patch.object(runner, "compose") as compose,
        ):
            runner.initialize_backend("staging")
        commands = repr(compose.call_args_list)
        self.assertIn("identity_transactions,public.identity_sessions TO drone_runtime", commands)
        for forbidden in ["bootstrap", "seed", "CREATE ROLE", "TRUNCATE", "DROP"]:
            self.assertNotIn(forbidden, commands)

    def test_accepted_runtime_binds_actual_final_configuration_and_rejects_environment_drift(self):
        runner = object.__new__(d.Runner)
        runner.plan, runner.binding = self.plan, self.binding
        prepared = i.values(self.runtime["staging"])
        row = {
            "Id": "7" * 64,
            "Name": "/" + self.plan["slots"]["staging"]["project"] + "-api-1",
            "Image": self.plan["runtime_images"][self.plan["api_image"]],
            "Config": {
                "Labels": {"org.onesa.source-commit": self.binding["candidate_commit"]},
                "Env": [key + "=" + value for key, value in prepared.items()],
            },
            "State": {"Running": True, "Status": "running", "Health": {"Status": "healthy"}},
            "HostConfig": {"ReadonlyRootfs": True},
            "Mounts": [],
            "NetworkSettings": {"Networks": {"approved": {"NetworkID": "n" * 64}}},
        }
        fingerprint = {key: row[key] for key in ["Config", "HostConfig", "Mounts"]}
        fingerprint["Networks"] = {"approved": "n" * 64}
        with patch.object(runner, "run", return_value=d.canonical([row])) as run:
            observed = runner.accepted_runtime("staging")
        self.assertEqual(
            observed,
            {
                "container_id": row["Id"],
                "image_id": row["Image"],
                "source_commit": self.binding["candidate_commit"],
                "configuration_sha256": hashlib.sha256(d.canonical(fingerprint)).hexdigest(),
            },
        )
        self.assertFalse(run.call_args.kwargs["persist_stdout"])
        row["Config"]["Env"] = [
            value.replace("SIMULATION_WORKER=true", "SIMULATION_WORKER=false")
            for value in row["Config"]["Env"]
        ]
        with patch.object(runner, "run", return_value=d.canonical([row])):
            with self.assertRaisesRegex(ValueError, "configuration differs"):
                runner.accepted_runtime("staging")

    def test_staging_runtime_receipt_is_captured_after_restart_restore_and_final_preservation(self):
        runner = object.__new__(d.Runner)
        runner.plan, runner.binding, runner.folder = self.plan, self.binding, self.root
        runner.context, runner.component, runner.phase = {"context_id": str(uuid4())}, "backend", "staging"
        events = []
        with ExitStack() as stack:
            for name in [
                "preserved",
                "frontend_files",
                "rollback_readiness",
                "initialize_backend",
                "api_check",
                "verify_storage",
                "compose",
                "identity",
                "backup_restore",
                "accepted_runtime",
            ]:

                def observe(*_args, _name=name, **_kwargs):
                    events.append(_name)
                    return "synthetic-runtime"

                stack.enter_context(patch.object(runner, name, side_effect=observe))
            result = runner.execute()
        self.assertEqual(events[-3:], ["backup_restore", "preserved", "accepted_runtime"])
        self.assertEqual(result["backend_runtime"], "synthetic-runtime")
        self.assertEqual(result["deployment_id"], "synthetic-runtime")


class WorkflowTests(unittest.TestCase):
    def test_shared_api_profile_keeps_full_existing_delivery_and_permission_scenarios(self):
        runner = object.__new__(d.Runner)
        runner.binding = {"candidate_commit": "a" * 40}
        runner.context = {"context_id": str(uuid4())}
        runner.plan = {
            "qualification_profile": i.PROFILE,
            "slots": {"staging": {"origin": d.ORIGINS["staging"][0], "api_origin": d.ORIGINS["staging"][1]}},
        }
        calls, logins = [], []
        mission = {"id": str(uuid4()), "revision": 1, "state": "completed", "delivered": True}

        class Client:
            def __init__(self, api, origin):
                self.api, self.origin = api, origin

            def call(self, path, method="GET", data=None, expected=200):
                calls.append((path, method, data, expected))
                if expected in {401, 403, 404, 409}:
                    return {}
                if path.endswith("/health"):
                    return {"mode": "simulation"}
                if path.endswith("/ready"):
                    return {"status": "ready"}
                if path.endswith("/auth/config"):
                    return {"shared_account": True}
                if path.endswith("/operations"):
                    return {"mode": "simulation", "aircraft": ["fixture"], "missions": [mission]}
                if path.endswith("/infrastructure"):
                    return {
                        "services": [
                            {"name": name, "status": "healthy"}
                            for name in ["Backend", "Database", "Telemetry", "Simulation"]
                        ],
                        "metrics": {"worker_failures": 0},
                    }
                if path.endswith("/security"):
                    return {"controls": {"simulation_only": True, "physical_adapter": "disabled"}}
                if path.endswith("/missions"):
                    return {"tracking_token": "fixture", "mission": mission}
                if path.endswith("/commands"):
                    return mission
                if path.endswith("/history"):
                    return {"telemetry": ["fixture"], "events": [{"state": "completed"}]}
                if "/tracking/" in path:
                    return {"delivered": True}
                raise AssertionError("Unexpected fixture path")

        def login(_runner, client, slot, actor):
            logins.append(actor)
            self.assertEqual(client.api, client.origin)
            return {"role": "admin" if actor != "viewer" else "viewer"}

        with (
            patch.object(d, "Client", Client),
            patch.object(
                i,
                "credentials",
                return_value={"accounts": {key: {"email": key + "@example.test"} for key in i.ACTORS}},
            ),
            patch.object(i, "login", side_effect=login),
            patch.object(runner, "verify_identity_probe"),
            patch.object(runner, "ensure_viewer") as create_viewer,
        ):
            result = runner.api_check("staging", workflow=True)
        create_viewer.assert_not_called()
        self.assertEqual(logins, ["operator", "foreign", "viewer"])
        self.assertTrue(result["tenant_scope"])
        self.assertTrue(any(path.endswith("/history") and expected == 404 for path, _, _, expected in calls))
        self.assertTrue(any(path.endswith("/commands") and expected == 403 for path, _, _, expected in calls))
        self.assertEqual(
            [
                data["action"]
                for path, _, data, status in calls
                if path.endswith("/commands") and status == 200
            ],
            ["plan", "validate", "authorize", "launch"],
        )
        self.assertTrue(any(path.endswith("/auth/login") and status == 409 for path, _, _, status in calls))


if __name__ == "__main__":
    unittest.main()

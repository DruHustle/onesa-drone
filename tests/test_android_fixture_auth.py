"""Native startup failure reports cannot echo credential-bearing logs or UI."""
import json
import unittest
from unittest.mock import MagicMock, call, patch

from scripts.android_fixture_auth import (
    APP_ID, expire_product_session, last_exit_reason, main, portal_observations,
    reset_native_planner, startup_classification,
)


class StartupDiagnosticsTests(unittest.TestCase):
    @patch("scripts.android_fixture_auth.time.sleep")
    @patch("scripts.android_fixture_auth.shell")
    def test_reset_waits_out_the_old_process_then_opens_a_fresh_launcher_task(self, shell, sleep):
        shell.side_effect = ["", "135", "", "Success", "Status: ok"]
        reset_native_planner()
        self.assertEqual(shell.call_args_list, [
            call("am", "force-stop", APP_ID),
            call("pidof", APP_ID, check=False), call("pidof", APP_ID, check=False),
            call("pm", "clear", APP_ID),
            call("am", "start", "-W", "-a", "android.intent.action.MAIN",
                 "-c", "android.intent.category.LAUNCHER", "-f", "0x10008000",
                 "-n", APP_ID + "/.MainActivity", timeout=75),
        ])
        sleep.assert_called_once()

    @patch.dict("os.environ", {"EXPO_PUBLIC_DRONE_DEV_ORIGIN": "https://127.0.0.1:54844"})
    @patch("scripts.android_fixture_auth.record_startup_failure")
    @patch("scripts.android_fixture_auth.reset_native_planner", side_effect=ValueError("launch failed"))
    @patch("scripts.android_fixture_auth.shell", side_effect=["33", "Success"])
    @patch("scripts.android_fixture_auth.adb", return_value="OnesaIdentityFixture")
    def test_failed_launcher_records_diagnostics_before_any_account_entry(self, adb, shell, reset, record):
        with self.assertRaisesRegex(ValueError, "launch failed"):
            main()
        reset.assert_called_once_with()
        record.assert_called_once_with(before_credentials=True)

    @patch.dict("os.environ", {"ONESA_FIXTURE_CONTROL": "fixture-key", "FIXTURE_CA": "test-ca"})
    @patch("scripts.android_fixture_auth.ssl.create_default_context")
    @patch("scripts.android_fixture_auth.http.client.HTTPSConnection")
    def test_scoped_expiry_requires_verified_role_subject_and_unchanged_portal(self, connect, context):
        response = MagicMock(status=200)
        connect.return_value.getresponse.return_value = response
        receipt = {"expiredProductSessions": 1, "portalSessionRowsUnchanged": True,
                   "expectedRoleVerified": True, "expectedProductSubjectVerified": True}
        response.read.return_value = json.dumps(receipt).encode()
        expire_product_session("member")
        context.assert_called_once_with(cafile="test-ca")
        connect.assert_called_once_with("127.0.0.1", 54844, context=context.return_value, timeout=15)
        connect.return_value.request.assert_called_once_with("POST", "/__onesa_fixture/expire-product-session",
            headers={"x-onesa-fixture-control": "fixture-key", "x-onesa-fixture-role": "member"})
        for key in receipt:
            with self.subTest(key=key):
                response.read.return_value = json.dumps(receipt | {key: False}).encode()
                with self.assertRaisesRegex(ValueError, "scoped expiry"):
                    expire_product_session("member")
        response.status = 409
        with self.assertRaisesRegex(ValueError, "refused"):
            expire_product_session("member")

    def test_exit_reason_allowlist_never_emits_history(self):
        self.assertEqual(last_exit_reason("reason=10 (USER REQUESTED) detail=private"), "user-requested")
        self.assertEqual(last_exit_reason("reason=3 (LOW_MEMORY) reason=10 (USER REQUESTED)"), "low-memory")
        self.assertEqual(last_exit_reason("reason=6 (PRIVATE) secret"), "unknown")

    def test_system_dialog_and_rendered_planner_are_distinguished(self):
        result = startup_classification(
            'System UI isn\'t responding <node text="Mission planner"/>', True
        )
        self.assertEqual(result["observations"], ["system-ui-not-responding", "planner-visible"])

    def test_untrusted_account_values_never_enter_diagnostic_result(self):
        private = "synthetic-password-example callback?code=private-example person@example.test"
        for text in (private, "TypeError: " + private, "FATAL EXCEPTION " + private,
                     "Unable to load script " + private):
            with self.subTest(text=text):
                result = startup_classification(text, False)
                self.assertNotIn(private, json.dumps(result))
                self.assertNotIn("private-example", json.dumps(result))
                self.assertFalse(result["processRunning"])

    def test_unknown_failure_is_explicit_without_fabricating_cause(self):
        self.assertEqual(startup_classification("unrecognized state", True)["observations"],
                         ["no-recognized-signature"])

    def test_portal_checkpoint_output_cannot_publish_urls_or_account_values(self):
        output = json.dumps(["cdp-connected", "https://localhost/callback?code=private", "secret", 3])
        self.assertEqual(portal_observations(output), ["cdp-connected"])
        self.assertEqual(portal_observations(b"untrusted exception containing private values"),
                         ["diagnostic-unavailable"])


if __name__ == "__main__":
    unittest.main()

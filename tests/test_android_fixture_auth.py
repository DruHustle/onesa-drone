"""Native startup failure reports cannot echo credential-bearing logs or UI."""
import json
import unittest

from scripts.android_fixture_auth import portal_observations, startup_classification


class StartupDiagnosticsTests(unittest.TestCase):
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

import unittest
import json
import tempfile
from pathlib import Path

from scripts.ios_account_diagnostics import summarize
from scripts.acceptance.native_start_diagnostics import read_start_diagnostics


class IOSAccountDiagnosticsTests(unittest.TestCase):
    def test_private_text_is_never_returned(self):
        result = summarize("""
Test Case '-[AccountTests testPortalSignInAndSystemCallback]' started.
ONESA_ACCOUNT_CHECKPOINT member:cold:start
ONESA_ACCOUNT_CHECKPOINT member:cold:account-screen-ready
ONESA_ACCOUNT_CHECKPOINT member:cold:consent-tapped
ONESA_ACCOUNT_CHECKPOINT member:cold:credentials-filled
ONESA_ACCOUNT_CHECKPOINT member:cold:credentials-filled
/private/secret/AccountTests.swift:53: error: XCTAssertTrue failed - secret@example.test
https://issuer.invalid/callback?code=secret
Type 'private password'
ONESA_ACCOUNT_CHECKPOINT admin:warm:https://private.invalid
""")
        self.assertEqual(result, {
            "checkpoints": ["member:cold:start", "member:cold:account-screen-ready", "member:cold:consent-tapped", "member:cold:credentials-filled"],
            "categories": ["test-started", "assertion-failed"],
            "account_test_source_lines": [53],
        })

    def test_build_failure_is_distinct_from_account_assertion(self):
        result = summarize("/private/source.swift:10:3: error: secret\n** TEST BUILD FAILED **")
        self.assertEqual(result["categories"], ["test-build-failed", "compiler-error"])
        self.assertEqual(result["checkpoints"], [])

    def test_unknown_failure_stays_unknown(self):
        self.assertEqual(summarize("private unexpected message")["categories"],
                         ["unclassified-failure"])

    def test_browser_state_uses_only_whole_allowlisted_flags(self):
        result = summarize("""
ONESA_ACCOUNT_CHECKPOINT member:cold:sign-in-tapped
ONESA_ACCOUNT_CHECKPOINT member:cold:browser-wait-failed
ONESA_ACCOUNT_STATE member:cold:contacting-visible
ONESA_ACCOUNT_STATE member:cold:contacting-visible
ONESA_ACCOUNT_STATE member:cold:service-unavailable-visible
ONESA_ACCOUNT_STATE admin:warm:consent-continue-visible
ONESA_ACCOUNT_STATE member:cold:app-foreground private-password
ONESA_ACCOUNT_STATE member:cold:email-field-visible?code=private
ONESA_ACCOUNT_STATE member:cold:https://issuer.invalid/private
ONESA_ACCOUNT_STATE person@example.test:cold:app-foreground
""")
        self.assertEqual(result["checkpoints"], ["member:cold:sign-in-tapped", "member:cold:browser-wait-failed"])
        self.assertEqual(result["observed_states"], [
            "member:cold:contacting-visible", "member:cold:service-unavailable-visible",
            "admin:warm:consent-continue-visible",
        ])
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn("@", json.dumps(result))

    def test_start_diagnostics_publish_only_bounded_counter_shape(self):
        valid = {"version": 1, "attempts": 2, "responses200": 1,
                 "responsesOther2xx": 0, "responses3xx": 0, "responses4xx": 0,
                 "responses5xx": 1, "responsesOther": 0, "proxyErrors": 0}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "start.json"
            self.assertEqual(read_start_diagnostics(path), {"status": "not-recorded"})
            path.write_text(json.dumps(valid))
            self.assertEqual(read_start_diagnostics(path), {"status": "recorded", **valid})
            for invalid in [
                valid | {"url": "https://issuer.invalid/?code=private"},
                valid | {"attempts": True}, valid | {"version": True},
                valid | {"attempts": -1}, valid | {"attempts": 1000},
                valid | {"responses200": "private"},
                {"attempts": 1}, [valid], None,
            ]:
                with self.subTest(invalid=type(invalid).__name__):
                    path.write_text(json.dumps(invalid))
                    self.assertEqual(read_start_diagnostics(path), {"status": "invalid-diagnostics"})
            path.write_text("private" * 1000)
            self.assertEqual(read_start_diagnostics(path), {"status": "invalid-diagnostics"})


class ButtonGeometryDiagnosticsTests(unittest.TestCase):
    def test_only_bounded_fixed_geometry_is_exported(self):
        valid = {"x": 10.5, "y": 120, "width": 250, "height": 48,
                 "exists": True, "enabled": True, "hittable": True, "centerInWindow": True}
        row = "ONESA_ACCOUNT_BUTTON member:cold:before:" + json.dumps(valid)
        result = summarize(row + "\n" + row)
        self.assertEqual(result["button_geometry"], [{"scenario": "member:cold", "stage": "before", **valid}])
        for bad in [valid | {"label": "private@example.test"}, valid | {"x": True},
                    valid | {"width": -1}, valid | {"x": float("nan")},
                    valid | {"height": 10001}, valid | {"hittable": "secret"}]:
            result = summarize("ONESA_ACCOUNT_BUTTON member:cold:failure:" + json.dumps(bad))
            self.assertNotIn("button_geometry", result)
            self.assertNotIn("private", json.dumps(result))

    def test_fixed_timeout_and_tls_categories_are_retained_without_text(self):
        result = summarize("ONESA_ACCOUNT_STATE member:cold:timeout-failure-visible\n"
                           "ONESA_ACCOUNT_STATE member:cold:tls-failure-visible\n"
                           "ONESA_ACCOUNT_STATE member:cold:tls-failure-visible secret")
        self.assertEqual(result["observed_states"], ["member:cold:timeout-failure-visible",
                                                     "member:cold:tls-failure-visible"])

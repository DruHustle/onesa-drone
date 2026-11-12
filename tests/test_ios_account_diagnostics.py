import unittest

from scripts.ios_account_diagnostics import summarize


class IOSAccountDiagnosticsTests(unittest.TestCase):
    def test_private_text_is_never_returned(self):
        result = summarize("""
Test Case '-[AccountTests testPortalSignInAndSystemCallback]' started.
ONESA_ACCOUNT_CHECKPOINT member:cold:start
ONESA_ACCOUNT_CHECKPOINT member:cold:credentials-filled
ONESA_ACCOUNT_CHECKPOINT member:cold:credentials-filled
/private/secret/AccountTests.swift:53: error: XCTAssertTrue failed - secret@example.test
https://issuer.invalid/callback?code=secret
Type 'private password'
ONESA_ACCOUNT_CHECKPOINT admin:warm:https://private.invalid
""")
        self.assertEqual(result, {
            "checkpoints": ["member:cold:start", "member:cold:credentials-filled"],
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

import unittest
from unittest.mock import patch

from scripts.verify_native_metro import NoRedirect, inspect_bundle


class NativeMetroPreflightTests(unittest.TestCase):
    def test_configured_debug_entry_emits_only_receipt_metadata(self):
        body = b'var __DEV__=true;const API="https://127.0.0.1:54844"+"/api/v1/auth/mobile";/*private*/'
        result = inspect_bundle(body)
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(result['debugPrelude'] and result['expectedLoopbackOrigin'])
        self.assertEqual(result['bytes'], len(body))
        self.assertNotIn('private', str(result))
        self.assertNotIn('const API', str(result))

    def test_wrong_mode_origin_or_missing_account_module_fail_closed(self):
        valid = b'var __DEV__=true;"https://127.0.0.1:54844";"/api/v1/auth/mobile"'
        for body in [b'', b'\xff', valid.replace(b'true', b'false'),
                     valid.replace(b'54844', b'12345'), valid.replace(b'/api/v1/auth/mobile', b'/other')]:
            with self.subTest(size=len(body)):
                with self.assertRaises((ValueError, UnicodeError)):
                    inspect_bundle(body)
        with patch('scripts.verify_native_metro.LIMIT', 8):
            with self.assertRaises(ValueError):
                inspect_bundle(valid)

    def test_redirects_are_never_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, None, {}, 'https://outside.invalid'))

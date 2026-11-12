import io
import json
import unittest
import urllib.error
from unittest.mock import Mock, patch

from scripts.verify_native_metro import NoRedirect, PreflightFailure, evaluate, inspect_bundle


class NativeMetroPreflightTests(unittest.TestCase):
    VALID = b'var __DEV__=true;const API="https://127.0.0.1:54844"+"/api/v1/auth/mobile";/*private*/'

    def response(self, body=None, status=200, content_type='application/javascript; charset=UTF-8'):
        response = Mock()
        response.status = status
        response.headers = {'Content-Type': content_type}
        response.read.return_value = self.VALID if body is None else body
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return Mock(open=Mock(return_value=response))

    def test_configured_debug_entry_emits_only_receipt_metadata(self):
        result = inspect_bundle(self.VALID)
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(result['debugPrelude'] and result['expectedLoopbackOrigin'])
        self.assertEqual(result['bytes'], len(self.VALID))
        self.assertNotIn('private', str(result))
        self.assertNotIn('const API', str(result))

    def test_wrong_mode_origin_or_missing_account_module_fail_closed(self):
        for body in [b'', b'\xff', self.VALID.replace(b'true', b'false'),
                     self.VALID.replace(b'54844', b'12345'), self.VALID.replace(b'/api/v1/auth/mobile', b'/other')]:
            with self.subTest(size=len(body)):
                with self.assertRaises(PreflightFailure):
                    inspect_bundle(body)
        with patch('scripts.verify_native_metro.LIMIT', 8):
            with self.assertRaises(PreflightFailure):
                inspect_bundle(self.VALID)

    def test_redirects_are_never_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, None, {}, 'https://outside.invalid'))

    def test_actual_response_categories_do_not_export_headers_body_or_exception(self):
        secret = 'PRIVATE-TOKEN-https://account.invalid/?code=not-public'
        cases = [
            (self.response(status=503, content_type='application/json; ' + secret), 'http-status'),
            (self.response(content_type='text/html; ' + secret), 'content-type'),
            (self.response(body=b''), 'size'),
            (self.response(body=b'\xff' + secret.encode()), 'encoding'),
            (self.response(body=secret.encode()), 'config'),
            (Mock(open=Mock(side_effect=TimeoutError(secret))), 'timeout'),
            (Mock(open=Mock(side_effect=urllib.error.URLError(TimeoutError(secret)))), 'timeout'),
            (Mock(open=Mock(side_effect=urllib.error.URLError(secret))), 'transport'),
            (Mock(open=Mock(side_effect=ConnectionRefusedError(secret))), 'transport'),
            (Mock(open=Mock(side_effect=RuntimeError(secret))), 'unexpected'),
            (Mock(open=Mock(side_effect=urllib.error.HTTPError(secret, 302, secret,
              {'Content-Type': 'text/html; ' + secret}, io.BytesIO(secret.encode())))), 'http-status'),
        ]
        for opener, category in cases:
            with self.subTest(category=category):
                result = evaluate(opener)
                self.assertEqual((result['status'], result['category']), ('FAIL', category))
                self.assertNotIn(secret, json.dumps(result))
                self.assertNotIn('account.invalid', json.dumps(result))
                self.assertIs(type(result['elapsedMilliseconds']), int)
                self.assertGreaterEqual(result['elapsedMilliseconds'], 0)
                self.assertLessEqual(result['elapsedMilliseconds'], 600000)
        self.assertEqual(evaluate(self.response(body=secret.encode()))['expectedLoopbackOrigin'], False)

    def test_response_bounds_timeout_and_positive_shape_are_preserved(self):
        opener = self.response()
        result = evaluate(opener)
        self.assertEqual((result['status'], result['httpStatus'], result['contentKind']), ('PASS', 200, 'javascript'))
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 120)
        opener.open.return_value.read.assert_called_once_with(64 * 1024 * 1024 + 1)
        self.assertEqual(len(result['sha256']), 64)
        self.assertNotIn('category', result)

"""Verify the prepared public iOS debug bundle without exposing bundle contents."""
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

LIMIT = 64 * 1024 * 1024
COMPILE_TIMEOUT = 120
ORIGIN = 'https://127.0.0.1:54844'
URL = ('http://127.0.0.1:8081/.expo/.virtual-metro-entry.bundle'
       '?platform=ios&dev=true&minify=false&modulesOnly=false&runModule=true')


def inspect_bundle(body):
    if not isinstance(body, bytes) or not 0 < len(body) <= LIMIT:
        raise ValueError('debug-bundle-size')
    source = body.decode('utf-8')
    debug = re.search(r'\b__DEV__\s*=\s*true\b', source[:4096]) is not None
    configured = ORIGIN in source
    account_module = '/api/v1/auth/mobile' in source
    if not (debug and configured and account_module):
        raise ValueError('debug-bundle-config')
    return {'status': 'PASS', 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
            'debugPrelude': debug, 'expectedLoopbackOrigin': configured,
            'mobileAccountModule': account_module,
            'scope': 'Prepared Metro response; this does not independently prove which bundle the simulator consumed.'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


if __name__ == '__main__':
    try:
        # Explicit local address and disabled proxy discovery prevent any provider request.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(URL, timeout=COMPILE_TIMEOUT) as response:
            if response.status != 200 or 'javascript' not in response.headers.get('Content-Type', ''):
                raise ValueError('debug-bundle-response')
            result = inspect_bundle(response.read(LIMIT + 1))
        Path(sys.argv[1]).write_text(json.dumps(result) + '\n')
        print('ONESA_METRO_PREFLIGHT ' + json.dumps(result), flush=True)
    except Exception:
        # Never publish response bodies, URL-bearing transport exceptions or paths.
        print('ONESA_METRO_PREFLIGHT {"status":"FAIL","category":"debug-bundle-preflight"}', flush=True)
        raise SystemExit(1)

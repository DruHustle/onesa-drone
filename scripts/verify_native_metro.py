"""Verify the prepared public iOS debug bundle without exposing bundle contents."""
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

LIMIT = 64 * 1024 * 1024
COMPILE_TIMEOUT = 120
ORIGIN = 'https://127.0.0.1:54844'
URL = ('http://127.0.0.1:8081/.expo/.virtual-metro-entry.bundle'
       '?platform=ios&dev=true&minify=false&modulesOnly=false&runModule=true')


class PreflightFailure(ValueError):
    def __init__(self, category, metadata=None):
        super().__init__(category)
        self.category = category
        self.metadata = metadata or {}


def content_kind(value):
    # Only an enum leaves the process, never arbitrary response header content.
    value = value.lower() if isinstance(value, str) else ''
    if 'javascript' in value:
        return 'javascript'
    if 'json' in value:
        return 'json'
    if 'html' in value:
        return 'html'
    return 'other' if value else 'missing'


def status_code(value):
    return value if type(value) is int and 100 <= value <= 599 else 0


def inspect_bundle(body):
    size = len(body) if isinstance(body, bytes) else 0
    metadata = {'bytes': min(size, LIMIT + 1)}
    if not isinstance(body, bytes) or not 0 < size <= LIMIT:
        raise PreflightFailure('size', metadata)
    metadata['sha256'] = hashlib.sha256(body).hexdigest()
    try:
        source = body.decode('utf-8')
    except UnicodeDecodeError:
        raise PreflightFailure('encoding', metadata) from None
    metadata.update(
        debugPrelude=re.search(r'\b__DEV__\s*=\s*true\b', source[:4096]) is not None,
        expectedLoopbackOrigin=ORIGIN in source,
        mobileAccountModule='/api/v1/auth/mobile' in source,
    )
    if not all(metadata[key] for key in ('debugPrelude', 'expectedLoopbackOrigin', 'mobileAccountModule')):
        raise PreflightFailure('config', metadata)
    return {'status': 'PASS', **metadata,
            'scope': 'Prepared Metro response; this does not independently prove which bundle the simulator consumed.'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def evaluate(opener=None):
    start = time.monotonic()
    metadata = {}
    result = None
    try:
        # Explicit local address and disabled proxy discovery prevent any provider request.
        if opener is None:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(URL, timeout=COMPILE_TIMEOUT) as response:
            metadata['httpStatus'] = status_code(response.status)
            metadata['contentKind'] = content_kind(response.headers.get('Content-Type', ''))
            if metadata['httpStatus'] != 200:
                raise PreflightFailure('http-status')
            if metadata['contentKind'] != 'javascript':
                raise PreflightFailure('content-type')
            result = inspect_bundle(response.read(LIMIT + 1))
    except PreflightFailure as error:
        result = {'status': 'FAIL', 'category': error.category, **error.metadata}
    except urllib.error.HTTPError as error:
        # Redirect/error bodies and URL-bearing reasons are never read or printed.
        metadata.update(httpStatus=status_code(error.code),
                        contentKind=content_kind(error.headers.get('Content-Type', '') if error.headers else ''))
        result = {'status': 'FAIL', 'category': 'http-status'}
    except urllib.error.URLError as error:
        result = {'status': 'FAIL', 'category': 'timeout' if isinstance(error.reason, TimeoutError) else 'transport'}
    except TimeoutError:
        result = {'status': 'FAIL', 'category': 'timeout'}
    except OSError:
        result = {'status': 'FAIL', 'category': 'transport'}
    except Exception:
        result = {'status': 'FAIL', 'category': 'unexpected'}
    return {**result, **metadata, 'elapsedMilliseconds': min(600000, max(0, int((time.monotonic() - start) * 1000)))}


if __name__ == '__main__':
    print('ONESA_METRO_PREFLIGHT_START ' + json.dumps({'timeoutSeconds': COMPILE_TIMEOUT, 'maximumBytes': LIMIT}), flush=True)
    result = evaluate()
    try:
        Path(sys.argv[1]).write_text(json.dumps(result) + '\n')
    except Exception:
        # Preserve safe diagnostic progress if the private receipt cannot be written.
        result = {**result, 'status': 'FAIL', 'category': 'output'}
    print('ONESA_METRO_PREFLIGHT ' + json.dumps(result), flush=True)
    raise SystemExit(0 if result['status'] == 'PASS' else 1)

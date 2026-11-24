import hashlib
import secrets
import hmac
import time
from threading import Lock
from fastapi import HTTPException


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


HASH_PREFIX = "scrypt$16384$8$5$"


def password_hash(password):
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=5).hex()
    return HASH_PREFIX + salt + "$" + value


def password_valid(password, encoded):
    # Fixed accepted parameters prevent a corrupted record from choosing unbounded work.
    legacy = not encoded.startswith(HASH_PREFIX)
    try:
        salt, value = encoded.split(":") if legacy else encoded[len(HASH_PREFIX) :].split("$")
        if len(salt) != 32 or len(value) != 128:
            raise ValueError("Invalid hash record")
    except ValueError:
        salt, value, legacy = "0" * 32, "0" * 128, False
    actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1 if legacy else 5).hex()
    if legacy:
        # Equal total work while existing local development hashes migrate on login.
        hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=4)
    return hmac.compare_digest(value, actual)


DUMMY_HASH = password_hash("unusable-internal-account-placeholder")


class Limiter:
    """Bounded fixed-window limiter with isolated budgets for high-cardinality routes."""

    MAX_ENTRIES = 4096
    NAMESPACES = frozenset({
        "login", "login-peer", "login-account", "identity-login",
        "stream", "dispatch", "flight-plan", "assistant",
    })

    def __init__(self):
        self.entries, self.lock, self.bucket = {}, Lock(), None

    def check(self, key, limit=120):
        with self.lock:
            # Rate-limit windows must not be reset by NTP/manual wall-clock changes.
            # monotonic() advances independently of civil time adjustments.
            bucket = int(time.monotonic() // 60)
            if self.bucket != bucket:
                # Every namespace belongs to one fixed-minute bucket. Clearing
                # only on rollover keeps memory bounded and lockouts stable.
                self.entries.clear()
                self.bucket = bucket
            prefix = key.partition(":")[0]
            namespace = prefix if prefix in self.NAMESPACES else "request"
            entries = self.entries.setdefault(namespace, {})
            if key not in entries and len(entries) >= self.MAX_ENTRIES:
                # Do not evict a live lockout. Saturation in one namespace must
                # not deny unrelated API traffic or another limiter's keys.
                raise HTTPException(429, "Request limit reached; retry after one minute")
            count = entries.get(key, 0) + 1
            entries[key] = count
            if count > limit:
                raise HTTPException(429, "Request limit reached; retry after one minute")

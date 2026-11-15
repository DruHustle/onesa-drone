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
    """Fixed-window, in-process limiter that never evicts active lockouts."""

    MAX_ENTRIES = 4096

    def __init__(self):
        self.entries, self.lock, self.bucket = {}, Lock(), None

    def check(self, key, limit=120):
        with self.lock:
            # Rate-limit windows must not be reset by NTP/manual wall-clock changes.
            # monotonic() advances independently of civil time adjustments.
            bucket = int(time.monotonic() // 60)
            if self.bucket != bucket:
                # Every entry belongs to one fixed-minute bucket. Clearing only
                # on minute rollover avoids unbounded memory and stale limits.
                self.entries.clear()
                self.bucket = bucket
            if key not in self.entries and len(self.entries) >= self.MAX_ENTRIES:
                # Evicting a current-minute account key lets a distributed
                # spray reset its login limit. Fail closed until rollover.
                raise HTTPException(429, "Request limit reached; retry after one minute")
            count = self.entries.get(key, 0) + 1
            self.entries[key] = count
            if count > limit:
                raise HTTPException(429, "Request limit reached; retry after one minute")

import hashlib
import secrets
import hmac
import time
from collections import OrderedDict
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
    def __init__(self):
        self.entries, self.lock = OrderedDict(), Lock()

    def check(self, key, limit=120):
        with self.lock:
            bucket = int(time.time() / 60)
            old, count = self.entries.pop(key, (bucket, 0))
            count = count + 1 if old == bucket else 1
            self.entries[key] = (bucket, count)
            while len(self.entries) > 4096:
                self.entries.popitem(last=False)
            if count > limit:
                raise HTTPException(429, "Request limit reached; retry after one minute")

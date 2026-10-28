import hashlib
import secrets
import hmac
import time
from collections import OrderedDict
from threading import Lock
from fastapi import HTTPException


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    salt = secrets.token_hex(16)
    return salt + ":" + hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()


def password_valid(password, encoded):
    salt, value = encoded.split(":")
    return hmac.compare_digest(
        value, hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    )


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

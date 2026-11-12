"""Expire one product session in this harness's disposable databases only."""

import json
import os
import sys
import time
from urllib.parse import urlsplit

import psycopg


def validate_database(url, name):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "postgresql"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 56882
        or parsed.username != "fixture"
        or parsed.path != "/" + name
        or not parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("disposable database scope required")
    return url


def examine(role, mutation="expire"):
    if mutation not in {"expire", "verify"}:
        raise ValueError("known fixture action required")
    if role not in {"member", "admin"}:
        raise ValueError("known fixture role required")
    drone_url = validate_database(os.environ["DRONE_FIXTURE_DATABASE_URL"], "drone_test")
    portal_url = validate_database(os.environ["PORTAL_FIXTURE_DATABASE_URL"], "portal_test")
    expected_user = os.environ["FIXTURE_" + role.upper() + "_ID"]
    expected_role = "member" if role == "member" else "administrator"
    now = time.time()
    with psycopg.connect(portal_url, autocommit=True) as portal, psycopg.connect(drone_url) as drone:
        account = portal.execute(
            "SELECT id,role FROM users WHERE email=%s", (role + "@example.test",)
        ).fetchall()
        if len(account) != 1 or str(account[0][0]) != expected_user or account[0][1] != expected_role:
            raise ValueError("expected synthetic role required")
        before = portal.execute("SELECT * FROM identity_sessions ORDER BY token_hash").fetchall()
        active = portal.execute("SELECT user_id FROM identity_sessions WHERE expires_at>now()").fetchall()
        if len(active) != 1 or str(active[0][0]) != expected_user:
            raise ValueError("one active expected Portal session required")
        rows = drone.execute(
            "SELECT token_hash,issuer,subject FROM identity_sessions WHERE expires>%s FOR UPDATE", (now,)
        ).fetchall()
        if (
            len(rows) != 1
            or rows[0][1] != os.environ["FIXTURE_EXPECTED_ISSUER"]
            or rows[0][2] != expected_user
        ):
            raise ValueError("one active expected Drone session required")
        if mutation == "expire":
            result = drone.execute(
                "UPDATE identity_sessions SET expires=%s WHERE token_hash=%s", (now - 1, rows[0][0])
            )
            if result.rowcount != 1:
                raise ValueError("one product row must expire")
        after = portal.execute("SELECT * FROM identity_sessions ORDER BY token_hash").fetchall()
        if before != after:
            raise ValueError("Portal session rows changed")
    return {
        "expiredProductSessions": 1 if mutation == "expire" else 0,
        "portalSessionRowsUnchanged": True,
        "expectedRoleVerified": True,
        "expectedProductSubjectVerified": True,
    }


def verify_native_audit(audit):
    flows = audit.get("flows")
    if not isinstance(flows, list) or len(flows) != 4:
        raise ValueError("four real native starts required")
    for index, (flow, credentials) in enumerate(zip(flows, [1, 0, 2, 0], strict=True)):
        if (
            not isinstance(flow, dict)
            or type(flow.get("credentialPosts")) is not int
            or flow["credentialPosts"] != credentials
            or type(flow.get("continuePosts")) is not int
            or flow["continuePosts"] not in ([0] if index % 2 == 0 else [0, 1])
        ):
            raise ValueError("cold MFA and credential-free warm flows required")
    if (
        type(audit.get("fixtureExpirations")) is not int
        or audit["fixtureExpirations"] != 2
        or type(audit.get("expiredAccountResponses")) is not int
        or audit["expiredAccountResponses"] < 2
        or type(audit.get("verifiedWarmSubjects")) is not int
        or audit["verifiedWarmSubjects"] != 2
        or audit.get("warmSubjectVerificationFailed") is not False
        or audit.get("unexpectedCredentialRoute") is not False
    ):
        raise ValueError("two scoped expirations, real401s and immutable warm subjects required")


if __name__ == "__main__":
    try:
        print(json.dumps(examine(sys.argv[1], sys.argv[2])))
    except Exception:
        print(json.dumps({"error": "fixture-session-expiry-refused"}))
        sys.exit(1)

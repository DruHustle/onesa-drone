"""The installed-test expiry helper must never reach another database or identity."""

from unittest.mock import patch

import pytest

from scripts.acceptance.expire_native_session import examine, validate_database


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://fixture:synthetic@database.example/drone_test",
        "postgresql://fixture:synthetic@localhost:56882/drone_test",
        "postgresql://fixture:synthetic@127.0.0.1:5432/drone_test",
        "postgresql://owner:synthetic@127.0.0.1:56882/drone_test",
        "postgresql://fixture:synthetic@127.0.0.1:56882/production",
        "postgresql://fixture@127.0.0.1:56882/drone_test",
        "https://fixture:synthetic@127.0.0.1:56882/drone_test",
        "postgresql://fixture:synthetic@127.0.0.1:56882/drone_test?host=database.example",
        "postgresql://fixture:synthetic@127.0.0.1:56882/drone_test?dbname=production",
        "postgresql://fixture:synthetic@127.0.0.1:56882/drone_test#fragment",
    ],
)
def test_database_scope_rejects_unowned_target(url):
    with pytest.raises(ValueError):
        validate_database(url, "drone_test")


class Rows:
    def __init__(self, values=(), count=0):
        self.values, self.rowcount = list(values), count

    def fetchall(self):
        return self.values


class Portal:
    def __init__(self, *, role="member", user="synthetic-member", changed=False):
        self.role, self.user, self.changed = role, user, changed
        self.snapshots = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, _params=()):
        if query.startswith("SELECT id,role FROM users"):
            return Rows([(self.user, self.role)])
        if query.startswith("SELECT user_id"):
            return Rows([(self.user,)])
        assert query.startswith("SELECT * FROM identity_sessions")
        self.snapshots += 1
        return Rows([("synthetic-row", self.changed and self.snapshots == 2)])


class Drone:
    def __init__(self, rows=None):
        self.rows = (
            rows
            if rows is not None
            else [("synthetic-hash", "https://localhost:54843/api/v1/identity", "synthetic-member")]
        )
        self.writes = 0
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        self.committed = kind is None
        return False

    def execute(self, query, params=()):
        if query.startswith("SELECT token_hash,issuer,subject"):
            return Rows(self.rows)
        assert query.startswith("UPDATE identity_sessions SET expires=")
        assert params[1] == self.rows[0][0]
        self.writes += 1
        return Rows(count=1)


def call_fixture(portal, drone, action="expire"):
    env = {
        "DRONE_FIXTURE_DATABASE_URL": "postgresql://fixture:synthetic@127.0.0.1:56882/drone_test",
        "PORTAL_FIXTURE_DATABASE_URL": "postgresql://fixture:synthetic@127.0.0.1:56882/portal_test",
        "FIXTURE_MEMBER_ID": "synthetic-member",
        "FIXTURE_EXPECTED_ISSUER": "https://localhost:54843/api/v1/identity",
    }
    with patch.dict("os.environ", env, clear=True), patch("psycopg.connect", side_effect=[portal, drone]):
        return examine("member", action)


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [("one", "https://localhost:54843/api/v1/identity", "synthetic-member")] * 2,
        [("one", "https://wrong.example", "synthetic-member")],
        [("one", "https://localhost:54843/api/v1/identity", "different-subject")],
    ],
)
def test_wrong_or_ambiguous_product_identity_never_mutates(rows):
    drone = Drone(rows)
    with pytest.raises(ValueError):
        call_fixture(Portal(), drone)
    assert drone.writes == 0
    assert not drone.committed


def test_wrong_portal_authority_never_mutates():
    drone = Drone()
    with pytest.raises(ValueError):
        call_fixture(Portal(role="administrator"), drone)
    assert drone.writes == 0


def test_portal_row_change_rolls_back_product_expiry():
    drone = Drone()
    with pytest.raises(ValueError):
        call_fixture(Portal(changed=True), drone)
    assert drone.writes == 1
    assert not drone.committed


def test_exact_expiry_preserves_portal_and_verifies_immutable_subject():
    drone = Drone()
    result = call_fixture(Portal(), drone)
    assert result == {
        "expiredProductSessions": 1,
        "portalSessionRowsUnchanged": True,
        "expectedRoleVerified": True,
        "expectedProductSubjectVerified": True,
    }
    assert drone.writes == 1 and drone.committed


def test_warm_subject_verification_never_mutates():
    drone = Drone()
    result = call_fixture(Portal(), drone, "verify")
    assert result["expiredProductSessions"] == 0
    assert result["expectedProductSubjectVerified"]
    assert drone.writes == 0


def audit_fixture(*, interactive=False):
    return {
        "flows": [
            {"credentialPosts": count, "continuePosts": int(interactive and index % 2 == 1)}
            for index, count in enumerate([1, 0, 2, 0])
        ],
        "fixtureExpirations": 2,
        "expiredAccountResponses": 2,
        "verifiedWarmSubjects": 2,
        "warmSubjectVerificationFailed": False,
        "unexpectedCredentialRoute": False,
    }


@pytest.mark.parametrize("interactive", [False, True])
def test_real_warm_auto_sso_and_explicit_continue_both_require_zero_credentials(interactive):
    from scripts.acceptance.expire_native_session import verify_native_audit

    verify_native_audit(audit_fixture(interactive=interactive))


@pytest.mark.parametrize(
    "change",
    [
        lambda a: a["flows"].pop(),
        lambda a: a["flows"][1].update(credentialPosts=1),
        lambda a: a["flows"][2].update(credentialPosts=1),
        lambda a: a["flows"][3].update(credentialPosts=False),
        lambda a: a["flows"][3].update(continuePosts=2),
        lambda a: a.update(expiredAccountResponses=1),
        lambda a: a.update(fixtureExpirations=1),
        lambda a: a.update(verifiedWarmSubjects=1),
        lambda a: a.update(warmSubjectVerificationFailed=True),
        lambda a: a.update(unexpectedCredentialRoute=True),
    ],
)
def test_native_acceptance_rejects_missing_or_weakened_flow_evidence(change):
    from scripts.acceptance.expire_native_session import verify_native_audit

    audit = audit_fixture()
    change(audit)
    with pytest.raises(ValueError):
        verify_native_audit(audit)

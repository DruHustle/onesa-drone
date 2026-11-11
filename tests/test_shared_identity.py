"""Local synthetic contract tests. No production/staging account or flight is used."""

from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4
import asyncio
import time
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, create_engine, text
from sqlalchemy.engine import make_url
from cryptography.fernet import Fernet

from backend.app.config import Settings
from backend.app.db import Store
from backend.app.main import create_app
from backend.app.models import Tenant, User, SchemaRevision, Audit
from backend.app.identity import IdentitySession, IdentityTransaction, TRANSACTION_COOKIE
from backend.app import onesa_identity as protocol
from backend.app.security import digest


@pytest.fixture
def identity_database(tmp_path):
    target = os.getenv("DRONE_TEST_DATABASE_URL", f"sqlite:///{tmp_path}/identity.db")
    if target.startswith("sqlite:"):
        yield target
        return
    url = make_url(target)
    if url.host not in {"127.0.0.1", "localhost"} or not (url.database or "").startswith("drone_test"):
        pytest.fail("Identity migration fixtures require a disposable loopback drone_test database")
    schema = "identity_test_" + uuid4().hex
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield url.set(query={**url.query, "options": f"-csearch_path={schema}"}).render_as_string(
            hide_password=False
        )
    finally:
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@pytest.fixture
def shared(identity_database, monkeypatch):
    cfg = Settings(
        database_url=identity_database,
        worker=False,
        identity_enabled=True,
        identity_issuer="http://127.0.0.1:8500/api/v1/identity",
        identity_client_id="onesa-drone-test",
        identity_client_secret="synthetic-test-secret-" * 3,
        identity_callback="http://127.0.0.1:3400/api/v1/auth/identity/callback",
        identity_encryption_key=Fernet.generate_key().decode("ascii"),
    )
    app = create_app(cfg)
    store = app.state.store
    store.initialize()
    with store.transaction() as db:
        first, second = Tenant(name="First synthetic workspace"), Tenant(name="Second synthetic workspace")
        db.add_all([first, second])
        db.flush()
        first_id, second_id = first.id, second.id
    account = protocol.Identity(
        cfg.identity_issuer,
        str(uuid4()),
        "central@example.test",
        "Synthetic Account",
        int(time.time()) + 3600,
        int(time.time()),
        ("pwd", "otp"),
        ("global_admin",),
        ("ai", "drone", "robot"),
        {"drone": "admin"},
        (),
    )
    state = {"identity": account, "active": True, "exchanges": [], "revocations": []}

    def validate(config, token):
        assert config.issuer == cfg.identity_issuer
        assert token == "synthetic-server-only-central-grant"
        if not state["active"]:
            raise protocol.IdentityError("identity_rejected", "Your Onesa session is no longer valid")
        return state["identity"]

    def exchange(config, code, verifier):
        assert code == "synthetic-authorization-code"
        state["exchanges"].append(verifier)
        return "synthetic-server-only-central-grant"

    def revoke(config, token, **kwargs):
        state["revocations"].append({"token": token, **kwargs})
        state["active"] = False
        return True

    monkeypatch.setattr(protocol, "validate_session", validate)
    monkeypatch.setattr(protocol, "exchange_code", exchange)
    monkeypatch.setattr(protocol, "revoke_session", revoke)
    with TestClient(app) as client:
        yield {
            "app": app,
            "cfg": cfg,
            "store": store,
            "client": client,
            "first": first_id,
            "second": second_id,
            "state": state,
        }


def begin(shared, reauthenticate=False, headers=None):
    response = shared["client"].post(
        "/api/v1/auth/identity/start",
        json={"reauthenticate": reauthenticate},
        headers=headers or {"Origin": shared["cfg"].origin},
    )
    assert response.status_code == 200, response.text
    return parse_qs(urlsplit(response.json()["authorization_url"]).query)


def complete(shared, query=None):
    query = query or begin(shared)
    response = shared["client"].get(
        "/api/v1/auth/identity/callback",
        params={"state": query["state"][0], "code": "synthetic-authorization-code"},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response


def headers(shared):
    response = shared["client"].get("/api/v1/auth/me")
    assert response.status_code == 200, response.text
    return {"Origin": shared["cfg"].origin, "X-CSRF-Token": response.json()["csrf"]}


def select_workspace(shared, tenant=None):
    return shared["client"].post(
        "/api/v1/auth/workspace", json={"tenant_id": tenant or shared["first"]}, headers=headers(shared)
    )


def test_shared_login_uses_one_account_without_local_password_or_user_record(shared):
    query = begin(shared)
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["openid email profile onesa"]
    assert complete(shared, query).headers["location"] == "/"
    client = shared["client"]
    account = client.get("/api/v1/auth/me").json()
    assert account["global_admin"] and account["identity_managed"]
    assert account["tenant_id"] is None
    assert account["role"] == "admin"
    assert "_identity" not in account and "identity_token" not in account
    assert "synthetic-server-only-central-grant" not in str(account)
    assert client.get("/api/v1/operations").status_code == 409
    with shared["store"].session() as db:
        assert db.scalar(select(User)) is None
        session = db.scalar(select(IdentitySession))
        assert session.issuer == shared["cfg"].identity_issuer
        assert session.encrypted_token != "synthetic-server-only-central-grant"
        assert (
            shared["app"].state.identity.decrypt(session.encrypted_token)
            == "synthetic-server-only-central-grant"
        )
        assert db.scalar(select(IdentityTransaction)) is None


def test_login_state_requires_same_browser_and_is_consumed_once(shared):
    query = begin(shared)
    browser = shared["client"].cookies.get(TRANSACTION_COOKIE)
    shared["client"].cookies.clear()
    assert "identity_callback_invalid" in complete(shared, query).headers["location"]
    assert not shared["state"]["exchanges"]
    shared["client"].cookies.set(
        TRANSACTION_COOKIE, browser, domain="testserver.local", path="/api/v1/auth/identity"
    )
    assert complete(shared, query).headers["location"] == "/"
    assert "identity_callback_invalid" in complete(shared, query).headers["location"]
    assert len(shared["state"]["exchanges"]) == 1


def test_normal_account_switch_retires_previous_session_without_strict_callback_cookie(shared):
    complete(shared)
    old_token = shared["client"].cookies.get("drone_session")
    old_subject = shared["state"]["identity"].subject
    query = begin(shared)
    # Cross-site top-level redirects carry the Lax flow cookie, but not Strict
    # application session cookies. The old session must still be retired.
    shared["client"].cookies.delete("drone_session")
    shared["state"]["identity"] = replace(shared["state"]["identity"], subject=str(uuid4()))
    assert complete(shared, query).headers["location"] == "/"
    assert shared["client"].cookies.get("drone_session") != old_token
    with shared["store"].session() as db:
        assert db.get(IdentitySession, digest(old_token)) is None
        sessions = list(db.scalars(select(IdentitySession)))
        assert len(sessions) == 1
        assert sessions[0].subject == shared["state"]["identity"].subject != old_subject


def test_untrusted_origin_and_legacy_password_login_cannot_bypass_shared_sign_in(shared):
    client = shared["client"]
    assert (
        client.post(
            "/api/v1/auth/identity/start", json={}, headers={"Origin": "https://attacker.example.test"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "central@example.test", "password": "guess"},
            headers={"Origin": shared["cfg"].origin},
        ).status_code
        == 409
    )


def test_global_admin_selects_existing_tenants_with_csrf_and_audit(shared):
    complete(shared)
    client = shared["client"]
    choices = client.get("/api/v1/auth/workspaces").json()["workspaces"]
    assert {row["id"] for row in choices} == {shared["first"], shared["second"]}
    assert client.post("/api/v1/auth/workspace", json={"tenant_id": shared["first"]}).status_code == 403
    old_csrf = headers(shared)["X-CSRF-Token"]
    selected = select_workspace(shared)
    assert selected.status_code == 200
    assert selected.json()["tenant_id"] == shared["first"]
    assert selected.json()["csrf"] != old_csrf
    assert client.get("/api/v1/users").status_code == 200
    assert select_workspace(shared, shared["second"]).status_code == 200
    assert client.get("/api/v1/auth/me").json()["tenant_id"] == shared["second"]
    with shared["store"].session() as db:
        audits = list(db.scalars(select(Audit).where(Audit.action == "identity.workspace_selected")))
        assert {row.tenant_id for row in audits} == {shared["first"], shared["second"]}
        assert all(row.actor.startswith("identity:") for row in audits)


def test_shared_administration_cannot_silently_create_or_disable_legacy_password_accounts(shared):
    complete(shared)
    assert select_workspace(shared).status_code == 200
    with shared["store"].transaction() as db:
        legacy = User(
            tenant_id=shared["first"],
            email="existing-local@example.test",
            password="synthetic-test-password-verifier",
            role="viewer",
        )
        db.add(legacy)
        db.flush()
        legacy_id = legacy.id
    client = shared["client"]
    assert (
        client.post(
            "/api/v1/users",
            json={"email": "second@example.test", "password": "synthetic-test-password", "role": "viewer"},
            headers=headers(shared),
        ).status_code
        == 409
    )
    assert client.post("/api/v1/users/" + legacy_id + "/disable", headers=headers(shared)).status_code == 409
    with shared["store"].session() as db:
        assert db.get(User, legacy_id).active
        assert len(list(db.scalars(select(User)))) == 1


@pytest.mark.parametrize("change", ["csrf", "tenant_id", "subject"])
def test_concurrent_workspace_transition_cannot_reuse_old_authorization(shared, monkeypatch, change):
    complete(shared)
    client = shared["client"]
    csrf = headers(shared)
    local_token = client.cookies.get("drone_session")
    service = shared["app"].state.identity
    workspaces = service.workspaces

    def change_after_admission(identity):
        choices = workspaces(identity)
        with shared["store"].transaction() as db:
            row = db.get(IdentitySession, digest(local_token))
            setattr(row, change, shared["second"] if change == "tenant_id" else "synthetic-replacement")
        return choices

    monkeypatch.setattr(service, "workspaces", change_after_admission)
    response = client.post("/api/v1/auth/workspace", json={"tenant_id": shared["first"]}, headers=csrf)
    assert response.status_code == 409
    with shared["store"].session() as db:
        assert db.get(IdentitySession, digest(local_token)).tenant_id != shared["first"]
        assert db.scalar(select(Audit).where(Audit.action == "identity.workspace_selected")) is None


def test_normal_account_needs_explicit_membership_and_never_inherits_an_email_role(shared):
    state = shared["state"]
    state["identity"] = replace(
        state["identity"], roles=(), amr=("pwd",), product_roles={"drone": "viewer"}, memberships=()
    )
    complete(shared)
    assert shared["client"].get("/api/v1/auth/workspaces").json()["workspaces"] == []
    assert select_workspace(shared).status_code == 403
    assert shared["client"].get("/api/v1/operations").status_code == 409
    state["identity"] = replace(
        state["identity"], memberships=({"product": "drone", "tenant_id": shared["first"], "role": "viewer"},)
    )
    assert select_workspace(shared).status_code == 200
    assert shared["client"].get("/api/v1/users").status_code == 403
    assert select_workspace(shared, shared["second"]).status_code == 403


def test_revocation_and_membership_removal_apply_to_the_next_request(shared):
    state = shared["state"]
    state["identity"] = replace(
        state["identity"],
        roles=(),
        amr=("pwd",),
        product_roles={"drone": "operator"},
        memberships=({"product": "drone", "tenant_id": shared["first"], "role": "operator"},),
    )
    complete(shared)
    assert shared["client"].get("/api/v1/operations").status_code == 200
    state["identity"] = replace(state["identity"], memberships=())
    assert shared["client"].get("/api/v1/operations").status_code == 403
    state["active"] = False
    assert shared["client"].get("/api/v1/auth/me").status_code == 401


def test_workspace_role_is_capped_by_live_product_role(shared):
    state = shared["state"]
    state["identity"] = replace(
        state["identity"],
        roles=(),
        product_roles={"drone": "admin"},
        memberships=({"product": "drone", "tenant_id": shared["first"], "role": "admin"},),
    )
    complete(shared)
    client = shared["client"]
    assert client.get("/api/v1/auth/me").json()["role"] == "admin"
    assert client.get("/api/v1/users").status_code == 200
    state["identity"] = replace(state["identity"], product_roles={"drone": "operator"})
    assert client.get("/api/v1/auth/me").json()["role"] == "operator"
    assert client.get("/api/v1/users").status_code == 403
    state["identity"] = replace(state["identity"], product_roles={"drone": "viewer"})
    assert client.get("/api/v1/auth/workspaces").json()["workspaces"][0]["role"] == "viewer"
    state["identity"] = replace(
        state["identity"],
        product_roles={"drone": "admin"},
        memberships=({"product": "drone", "tenant_id": shared["first"], "role": "viewer"},),
    )
    assert client.get("/api/v1/auth/me").json()["role"] == "viewer"
    assert client.get("/api/v1/users").status_code == 403


def test_local_revocation_during_issuer_validation_cannot_resurrect_session(shared, monkeypatch):
    complete(shared)
    token = shared["client"].cookies.get("drone_session")
    validate = protocol.validate_session

    def revoke_during_validation(*args, **kwargs):
        result = validate(*args, **kwargs)
        with shared["store"].transaction() as db:
            db.delete(db.get(IdentitySession, digest(token)))
        return result

    monkeypatch.setattr(protocol, "validate_session", revoke_during_validation)
    assert shared["client"].get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize(
    "params",
    [
        {"iss": "https://other.example.test/api/v1/identity"},
        {"return_to": "https://attacker.example.test"},
        {"state": ["first-synthetic-state", "second-synthetic-state"]},
    ],
)
def test_callback_rejects_foreign_issuer_unknown_fields_and_duplicates(shared, params):
    query = begin(shared)
    response = shared["client"].get(
        "/api/v1/auth/identity/callback",
        params={"code": "synthetic-authorization-code", "state": query["state"][0], **params},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/?account_error=identity_callback_invalid"
    assert not shared["state"]["exchanges"]


def test_admin_step_up_uses_real_auth_time_and_preserves_chosen_workspace(shared):
    complete(shared)
    assert select_workspace(shared).status_code == 200
    shared["state"]["identity"] = replace(shared["state"]["identity"], auth_time=int(time.time()) - 600)
    rejected = select_workspace(shared, shared["second"])
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "identity_reauthentication_required"
    query = begin(shared, reauthenticate=True, headers=headers(shared))
    assert query["prompt"] == ["login"] and query["max_age"] == ["0"]
    shared["state"]["identity"] = replace(shared["state"]["identity"], auth_time=int(time.time()))
    assert complete(shared, query).headers["location"] == "/"
    assert shared["client"].get("/api/v1/auth/me").json()["tenant_id"] == shared["first"]


def test_admin_confirmation_requires_existing_session_and_csrf(shared):
    client = shared["client"]
    assert (
        client.post(
            "/api/v1/auth/identity/start",
            json={"reauthenticate": True},
            headers={"Origin": shared["cfg"].origin},
        ).status_code
        == 401
    )
    complete(shared)
    assert (
        client.post(
            "/api/v1/auth/identity/start",
            json={"reauthenticate": True},
            headers={"Origin": shared["cfg"].origin},
        ).status_code
        == 403
    )


@pytest.mark.parametrize("change", ["signed_out", "workspace_changed", "expired"])
def test_admin_confirmation_cannot_restore_a_changed_browser_session(shared, change):
    complete(shared)
    assert select_workspace(shared).status_code == 200
    previous_token = shared["client"].cookies.get("drone_session")
    query = begin(shared, reauthenticate=True, headers=headers(shared))
    with shared["store"].transaction() as db:
        row = db.get(IdentitySession, digest(previous_token))
        if change == "signed_out":
            db.delete(row)
        elif change == "workspace_changed":
            row.tenant_id = shared["second"]
            row.csrf = "synthetic-replacement-csrf"
        else:
            row.expires = time.time() - 1
    response = complete(shared, query)
    assert response.headers["location"] == "/?account_error=identity_reauthentication_expired"
    assert shared["client"].cookies.get("drone_session") == previous_token
    with shared["store"].session() as db:
        assert not list(
            db.scalars(select(IdentitySession).where(IdentitySession.token_hash != digest(previous_token)))
        )


def test_admin_confirmation_rereads_local_session_after_issuer_reply(shared, monkeypatch):
    complete(shared)
    query = begin(shared, reauthenticate=True, headers=headers(shared))
    previous_token = shared["client"].cookies.get("drone_session")
    validate = protocol.validate_session

    def sign_out_before_return(*args, **kwargs):
        result = validate(*args, **kwargs)
        with shared["store"].transaction() as db:
            db.delete(db.get(IdentitySession, digest(previous_token)))
        return result

    monkeypatch.setattr(protocol, "validate_session", sign_out_before_return)
    assert complete(shared, query).headers["location"] == "/?account_error=identity_reauthentication_expired"
    with shared["store"].session() as db:
        assert db.scalar(select(IdentitySession)) is None


@pytest.mark.parametrize("change", ["subject", "stale_auth_time", "missing_mfa"])
def test_admin_confirmation_rejects_different_account_or_missing_fresh_proof(shared, change):
    complete(shared)
    previous_token = shared["client"].cookies.get("drone_session")
    query = begin(shared, reauthenticate=True, headers=headers(shared))
    identity = shared["state"]["identity"]
    if change == "subject":
        identity = replace(identity, subject=str(uuid4()))
        error = "identity_account_changed"
    elif change == "stale_auth_time":
        identity = replace(identity, auth_time=int(time.time()) - 600)
        error = "identity_reauthentication_required"
    else:
        identity = replace(identity, roles=(), amr=("pwd",))
        error = "identity_reauthentication_required"
    shared["state"]["identity"] = identity
    assert complete(shared, query).headers["location"] == "/?account_error=" + error
    assert shared["client"].cookies.get("drone_session") == previous_token
    with shared["store"].session() as db:
        assert len(list(db.scalars(select(IdentitySession)))) == 1


def test_shared_signout_revokes_central_account_and_local_session(shared):
    complete(shared)
    token = shared["client"].cookies.get("drone_session")
    response = shared["client"].post("/api/v1/auth/logout", headers=headers(shared))
    assert response.status_code == 200
    assert response.json()["central_signed_out"] is True
    assert shared["state"]["revocations"] == [
        {"token": "synthetic-server-only-central-grant", "all_sessions": True}
    ]
    assert shared["client"].cookies.get("drone_session") is None
    with shared["store"].session() as db:
        assert db.get(IdentitySession, digest(token)) is None


def test_shared_signout_clears_local_session_even_when_issuer_is_unavailable(shared, monkeypatch):
    complete(shared)
    csrf = headers(shared)
    token = shared["client"].cookies.get("drone_session")

    def unavailable(*args, **kwargs):
        raise protocol.IdentityError("identity_unavailable", "Onesa sign-in is temporarily unavailable", 503)

    monkeypatch.setattr(protocol, "validate_session", unavailable)
    monkeypatch.setattr(protocol, "revoke_session", unavailable)
    response = shared["client"].post("/api/v1/auth/logout", headers=csrf)
    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "shared_account": True,
        "local_signed_out": True,
        "central_signed_out": False,
    }
    assert shared["client"].cookies.get("drone_session") is None
    with shared["store"].session() as db:
        assert db.get(IdentitySession, digest(token)) is None


@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        ("identity_unavailable", 503, 'event: unavailable\ndata: {"reason":"identity"}\n\n'),
        ("identity_rejected", 401, "event: expired\ndata: {}\n\n"),
        ("identity_mfa_required", 403, "event: expired\ndata: {}\n\n"),
    ],
)
def test_shared_stream_distinguishes_outage_from_lost_access(shared, monkeypatch, code, status, expected):
    complete(shared)
    account = select_workspace(shared).json()
    app = shared["app"]
    route = next(r for r in app.routes if r.path == "/api/v1/stream")
    request = SimpleNamespace(
        cookies={"drone_session": shared["client"].cookies.get("drone_session")},
        is_disconnected=lambda: asyncio.sleep(0, result=False),
    )

    def fail_validation(*args):
        raise protocol.IdentityError(code, "Synthetic validation failure", status)

    async def exercise():
        response = await route.endpoint(request, account)
        with monkeypatch.context() as patch:
            patch.setattr(protocol, "validate_session", fail_validation)
            assert [frame async for frame in response.body_iterator] == [expected]
        assert app.state.health["streams"] == 0
        if status == 503:
            recovered = await route.endpoint(request, account)
            try:
                assert (await anext(recovered.body_iterator)).startswith("event: telemetry\n")
            finally:
                await recovered.body_iterator.aclose()

    asyncio.run(exercise())


def test_expired_central_grant_does_not_claim_everywhere_logout(shared, monkeypatch):
    complete(shared)
    csrf = headers(shared)
    monkeypatch.setattr(protocol, "revoke_session", lambda *args, **kwargs: False)
    response = shared["client"].post("/api/v1/auth/logout", headers=csrf)
    assert response.status_code == 200
    assert response.json()["local_signed_out"] is True
    assert response.json()["central_signed_out"] is False
    assert shared["client"].cookies.get("drone_session") is None


def test_identity_secrets_are_encrypted_and_tampering_fails_closed(shared):
    query = begin(shared)
    with shared["store"].session() as db:
        pending = db.scalar(select(IdentityTransaction))
        verifier = shared["app"].state.identity.decrypt(pending.encrypted_verifier)
        assert pending.encrypted_verifier != verifier and verifier not in pending.encrypted_verifier
    complete(shared, query)
    with shared["store"].transaction() as db:
        db.scalar(select(IdentitySession)).encrypted_token = "invalid-synthetic-ciphertext"
    assert shared["client"].get("/api/v1/auth/me").status_code == 401


def test_additive_migration_preserves_original_schema_and_requires_explicit_enable(identity_database):
    url = identity_database
    legacy = Store(url)
    legacy.initialize()
    with legacy.session() as db:
        original = db.get(SchemaRevision, "0001").checksum
    shared = Store(url, identity_enabled=True)
    with pytest.raises(RuntimeError, match="Shared identity migration"):
        shared.verify()
    shared.initialize()
    shared.verify()
    legacy.verify()
    with shared.session() as db:
        assert db.get(SchemaRevision, "0001").checksum == original
        assert db.get(SchemaRevision, "0002-identity").checksum == shared.identity_checksum()


@pytest.mark.parametrize(
    "change",
    [
        {"identity_issuer": "https://attacker.test/api/v1/identity?redirect=x"},
        {"identity_callback": "https://attacker.test/callback"},
        {"identity_client_secret": "short"},
        {"identity_encryption_key": "not-a-fernet-key"},
    ],
)
def test_shared_configuration_rejects_partial_or_unsafe_setup(shared, change):
    with pytest.raises(ValueError):
        replace(shared["cfg"], **change).validate()

"""Local Auth0-compatible issuance and Product-owned resource identity."""

import json
import time
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app.managed_oidc import NS, exchange, validate
from backend.app.onesa_identity import IdentityConfig, IdentityError, authorization_url, new_transaction


@pytest.fixture
def signed():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    config = IdentityConfig(
        "https://issuer.example/",
        "drone-web",
        "test" * 10,
        "https://ai.example/callback",
        "drone",
        False,
        "https://api.drone.example",
        json.dumps({"keys": [{**public, "kid": "fixture"}]}),
        "https://legacy.example/api/v1/identity",
        "https://admin.example/account",
    )
    uid = str(uuid4())

    def pair(at=None, profile=None):
        now = int(time.time())
        shared = {"iss": config.issuer, "sub": "auth0|synthetic", "iat": now, "exp": now + 240}
        access = {
            **shared,
            "aud": config.audience,
            NS + "products": ["drone"],
            NS + "roles": ["viewer"],
            NS + "user_id": uid,
            **(at or {}),
        }
        user = {
            **shared,
            "aud": config.client_id,
            "email_verified": True,
            "email": "member@example.com",
            "name": "Member",
            "nonce": "registered-nonce",
            **(profile or {}),
        }
        return {
            k: jwt.encode(v, key, algorithm="RS256", headers={"kid": "fixture"})
            for k, v in [("access_token", access), ("id_token", user)]
        }

    return config, uid, pair


def test_provider_exchange_and_local_key_restart(signed):
    config, uid, pair = signed
    state, nonce, verifier = new_transaction()
    url = urlsplit(authorization_url(config, state, nonce, verifier, reauthenticate=True))
    q = parse_qs(url.query)
    assert (
        url.path == "/authorize"
        and q["audience"] == [config.audience]
        and q["code_challenge_method"] == ["S256"]
    )

    def response(req):
        assert req.url.path == "/oauth/token" and req.method == "POST"
        assert parse_qs(req.content.decode())["code_verifier"] == [verifier]
        return httpx.Response(200, json={**pair(), "token_type": "Bearer"})

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        packed = exchange(config, "controlled-code", verifier, "registered-nonce", client)
        with pytest.raises(IdentityError):
            exchange(config, "controlled-code", verifier, "wrong-nonce", client)
    recovered = validate(replace(config), packed)
    assert recovered.subject == uid and recovered.issuer == config.issuer
    assert recovered.email == "member@example.com" and not recovered.global_admin


@pytest.mark.parametrize(
    ("changes", "profile"),
    [
        ({"aud": "other"}, {}),
        ({NS + "products": ["ai"]}, {}),
        ({NS + "user_id": "member@example.com"}, {}),
        ({NS + "roles": ["admin"]}, {}),
        ({"exp": int(time.time()) + 600}, {}),
        ({"exp": 10}, {}),
        ({}, {"sub": "other"}),
        ({}, {"email_verified": False}),
        ({}, {"aud": "other"}),
    ],
)
def test_mismatch_or_privilege_denied(signed, changes, profile):
    config, _, pair = signed
    with pytest.raises(IdentityError):
        validate(config, json.dumps(pair(changes, profile)))


def test_web_and_native_callbacks_preserve_local_workspace_when_issuer_is_unavailable(
    tmp_path, monkeypatch, signed
):
    from cryptography.fernet import Fernet
    from fastapi.testclient import TestClient

    from backend.app import managed_oidc
    from backend.app.config import Settings
    from backend.app.identity import ManagedMembership
    from backend.app.main import create_app
    from backend.app.managed_memberships import import_memberships
    from backend.app.models import Tenant

    provider, stable, issue = signed
    config = Settings(
        database_url=f"sqlite:///{tmp_path}/managed.sqlite3",
        worker=False,
        identity_enabled=True,
        identity_issuer=provider.issuer,
        identity_client_id=provider.client_id,
        identity_client_secret=provider.client_secret,
        identity_callback="http://127.0.0.1:3400/api/v1/auth/identity/callback",
        identity_encryption_key=Fernet.generate_key().decode(),
        identity_audience=provider.audience,
        identity_public_jwks=provider.public_jwks,
        identity_mapping_issuer=provider.mapping_issuer,
        identity_account_url=provider.account_url,
    )
    app = create_app(config)
    store = app.state.store
    store.initialize()
    with store.transaction() as db:
        allowed = Tenant(name="Original assigned workspace")
        other = Tenant(name="Unassigned workspace")
        db.add_all([allowed, other])
        db.flush()
        allowed_id, other_id = allowed.id, other.id
    rows = [{"user_id": stable, "tenant_id": allowed_id, "role": "operator"}]
    assert import_memberships(store, rows) == 1
    assert import_memberships(store, rows) == 0
    with pytest.raises(ValueError):
        import_memberships(store, [{**rows[0], "role": "admin"}])
    nonce = ""

    def reply(cfg, path, **kwargs):
        assert path == "oauth/token"
        return {**issue(profile={"nonce": nonce}), "token_type": "Bearer"}

    monkeypatch.setattr(managed_oidc, "_request", reply)
    with TestClient(app, base_url=config.origin) as client:
        client.headers["origin"] = config.origin
        start = client.post("/api/v1/auth/identity/start", json={}).json()
        params = parse_qs(urlsplit(start["authorization_url"]).query)
        nonce = params["nonce"][0]
        cb = client.get(
            "/api/v1/auth/identity/callback",
            params={"state": params["state"][0], "code": "one-use"},
            follow_redirects=False,
        )
        assert cb.status_code == 303 and cb.headers["location"] == "/"
        me = client.get("/api/v1/auth/me").json()
        assert me["identity_subject"] == stable and me["tenant_id"] == allowed_id and me["role"] == "viewer"
        client.headers["x-csrf-token"] = me["csrf"]
        assert client.post("/api/v1/auth/workspace", json={"tenant_id": other_id}).status_code == 403
        start = client.post("/api/v1/auth/mobile/start").json()
        nonce = parse_qs(urlsplit(start["authorization_url"]).query)["nonce"][0]
        data = {"state": start["state"], "proof": start["proof"], "code": "mobile-code"}
        mobile = client.post("/api/v1/auth/mobile/exchange", json=data)
        assert mobile.status_code == 200, mobile.text
        bearer = {"authorization": "Bearer " + mobile.json()["session"]}
        profile = client.get("/api/v1/auth/mobile/account", headers=bearer)
        import hashlib

        assert (
            profile.json()["storage_scope"]
            == hashlib.sha256((provider.mapping_issuer + "\x00" + stable).encode()).hexdigest()
        )

        def offline(*args, **kwargs):
            raise AssertionError("Unexpected issuer dependency")

        monkeypatch.setattr(managed_oidc, "_request", offline)
        assert client.get("/api/v1/operations").status_code == 200
        with store.transaction() as db:
            db.delete(db.get(ManagedMembership, (stable, allowed_id)))
        assert client.get("/api/v1/operations").status_code == 403

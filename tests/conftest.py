import os
import secrets
import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.config import Settings
from backend.app.models import Tenant, User
from backend.app.security import password_hash


@pytest.fixture
def stack(tmp_path):
    url = os.getenv("DRONE_TEST_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    if not url.startswith("sqlite:") and "/drone_test" not in url:
        pytest.fail("Integration target must be a disposable drone_test database")
    app = create_app(Settings(database_url=url, worker=False))
    store = app.state.store
    store.initialize()
    # PostgreSQL fixture uses unique tenant IDs; no truncation of any storage.
    email = f"operator-{secrets.token_hex(5)}@example.test"
    password = "Synthetic-test-only-password-579!"
    with store.transaction() as db:
        tenant = Tenant(name="Synthetic lab")
        db.add(tenant)
        db.flush()
        tid = tenant.id
        user = User(tenant_id=tid, email=email, password=password_hash(password), role="admin")
        db.add(user)
        db.flush()
        uid = user.id
        other = Tenant(name="Other tenant")
        db.add(other)
        db.flush()
        otherid = other.id
        viewer = User(tenant_id=tid, email="viewer-" + email, password=password_hash(password), role="viewer")
        db.add(viewer)
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            headers={"Origin": app.state.settings.origin},
        )
        assert r.status_code == 200, r.text
        headers = {"Origin": app.state.settings.origin, "X-CSRF-Token": r.json()["csrf"]}
        yield {
            "app": app,
            "store": store,
            "client": client,
            "tenant": tid,
            "user": uid,
            "other": otherid,
            "headers": headers,
            "email": email,
            "password": password,
        }


@pytest.fixture
def aircraft(stack):
    r = stack["client"].post(
        "/api/v1/aircraft",
        json={
            "name": "SIM-001",
            "model": "Reference quad",
            "manufacturer": "Illustrative",
            "category": "multirotor",
            "capacity": 4,
            "endurance": 35,
        },
        headers={**stack["headers"], "Idempotency-Key": secrets.token_hex(12)},
    )
    assert r.status_code == 201, r.text
    return r.json()


def delivery(stack, scenario="nominal", **overrides):
    body = {
        "label": "Synthetic parcel",
        "package_weight": 1.2,
        "package_kind": "standard",
        "origin": {"lat": 52.52, "lon": 13.405},
        "destination": {"lat": 52.523, "lon": 13.411},
        "scenario": scenario,
        **overrides,
    }
    r = stack["client"].post(
        "/api/v1/missions", json=body, headers={**stack["headers"], "Idempotency-Key": secrets.token_hex(12)}
    )
    assert r.status_code == 201, r.text
    return r.json()


def cmd(stack, m, action, **kwargs):
    return stack["client"].post(
        "/api/v1/missions/" + m["id"] + "/commands",
        json={"action": action, "revision": m["revision"], **kwargs},
        headers={**stack["headers"], "Idempotency-Key": secrets.token_hex(12)},
    )


def launch(stack, scenario="nominal"):
    result = delivery(stack, scenario)
    m = result["mission"]
    for action in ["plan", "validate", "authorize", "launch"]:
        r = cmd(stack, m, action)
        assert r.status_code == 200, r.text
        m = r.json()
    return m, result["tracking_token"]

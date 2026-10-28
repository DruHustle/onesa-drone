import json
import time
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from backend.app.models import Mission, Aircraft, Audit
from backend.app.service import mission_out
from conftest import delivery, cmd


def test_dispatch_preview_is_tenant_scoped_read_only_and_revalidated(stack, aircraft):
    m = delivery(stack)["mission"]
    with stack["store"].transaction() as db:
        other = Mission(
            tenant_id=stack["other"],
            label="Other tenant private delivery",
            package_weight=1,
            package_kind="standard",
            origin=json.dumps(m["origin"]),
            destination=json.dumps(m["destination"]),
            track_hash="synthetic-other-tenant-tracking",
            track_expires=0,
        )
        db.add(other)
        before = db.scalar(select(func.count()).select_from(Audit))
    anonymous = TestClient(stack["app"])
    assert anonymous.get("/api/v1/dispatch/preview").status_code == 401
    anonymous.close()
    r = stack["client"].get("/api/v1/dispatch/preview")
    assert r.status_code == 200
    result = r.json()
    assert result["advisory"] and result["mode"] == "simulation"
    assert [entry["mission_id"] for entry in result["entries"]] == [m["id"]]
    assert "Other tenant" not in r.text
    with stack["store"].session() as db:
        assert mission_out(db.get(Mission, m["id"])) == m
        assert db.get(Aircraft, aircraft["id"]).active_mission_id is None
        assert db.scalar(select(func.count()).select_from(Audit)) == before
    # A preview cannot reserve its suggested aircraft or bypass changed fleet state.
    competitor = delivery(stack)["mission"]
    assert cmd(stack, competitor, "plan").status_code == 200
    assert cmd(stack, m, "plan", aircraft_id=result["entries"][0]["aircraft_id"]).status_code == 422


def test_alternative_plan_persists_and_cannot_bypass_authorization(stack, aircraft):
    m = delivery(stack)["mission"]
    r = cmd(stack, m, "plan", route_index=1)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["plan"]["route_index"] == 1
    with stack["store"].session() as db:
        assert json.loads(db.get(Mission, m["id"]).plan) == m["plan"]
    assert cmd(stack, m, "launch").status_code == 422
    for action in ["validate", "authorize"]:
        m = cmd(stack, m, action).json()
    m = cmd(stack, m, "replan").json()
    assert m["authorized_until"] is None and m["plan"] == {}
    m = cmd(stack, m, "plan", route_index=2).json()
    assert m["plan"]["route_index"] == 2
    assert cmd(stack, m, "launch").status_code == 422


def test_dispatch_preview_throttles_recomputation(stack, monkeypatch):
    now = time.time()
    monkeypatch.setattr("backend.app.security.time.time", lambda: now)
    for _ in range(6):
        assert stack["client"].get("/api/v1/dispatch/preview").status_code == 200
    assert stack["client"].get("/api/v1/dispatch/preview").status_code == 429

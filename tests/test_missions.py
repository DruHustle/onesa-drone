import json
import time
import secrets
import pytest
from sqlalchemy import select, func
from backend.app.models import Mission, Aircraft, MissionEvent, Telemetry
from backend.app.service import advance, mission_out
from conftest import delivery, cmd, launch


def tick(stack, identifier, count=1):
    for _ in range(count):
        with stack["store"].transaction(stack["tenant"]) as db:
            advance(db, db.get(Mission, identifier))
    with stack["store"].session() as db:
        return mission_out(db.get(Mission, identifier))


def test_complete_delivery_and_persisted_replay(stack, aircraft):
    m, token = launch(stack)
    m = tick(stack, m["id"], 150)
    assert m["state"] == "completed" and m["delivered"]
    with stack["store"].session() as db:
        a = db.get(Aircraft, aircraft["id"])
        assert a.active_mission_id is None and a.status == "available" and 25 < a.battery < 100
        states = list(
            db.scalars(
                select(MissionEvent.state).where(MissionEvent.mission_id == m["id"]).order_by(MissionEvent.at)
            )
        )
        assert states == [
            "requested",
            "planned",
            "validated",
            "authorized",
            "taking_off",
            "outbound",
            "delivering",
            "returning",
            "landing",
            "completed",
        ]
    history = stack["client"].get(f"/api/v1/missions/{m['id']}/history").json()
    assert len(history["telemetry"]) > 15 and history["events"][-1]["state"] == "completed"
    tracked = stack["client"].get("/api/v1/tracking/" + token).json()
    assert tracked["delivered"] and tracked["progress_percent"] == 100
    assert not {"aircraft_id", "destination", "position", "label", "origin"} & tracked.keys()


def test_duplicate_command_and_payload_conflict(stack, aircraft):
    m = delivery(stack)["mission"]
    key = secrets.token_hex(12)
    headers = {**stack["headers"], "Idempotency-Key": key}
    body = {"action": "plan", "revision": m["revision"]}
    first = stack["client"].post(f"/api/v1/missions/{m['id']}/commands", json=body, headers=headers)
    again = stack["client"].post(f"/api/v1/missions/{m['id']}/commands", json=body, headers=headers)
    assert first.status_code == 200 and first.json() == again.json()
    conflict = stack["client"].post(
        f"/api/v1/missions/{m['id']}/commands", json={**body, "action": "launch"}, headers=headers
    )
    assert conflict.status_code == 409
    with stack["store"].session() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(MissionEvent).where(MissionEvent.mission_id == m["id"])
            )
            == 2
        )


def test_conflicting_aircraft_assignments(stack, aircraft):
    a = delivery(stack)["mission"]
    b = delivery(stack)["mission"]
    assert cmd(stack, a, "plan").status_code == 200
    assert cmd(stack, b, "plan").status_code == 422


@pytest.mark.parametrize("action", ["launch", "authorize", "validate", "recover", "reschedule"])
def test_invalid_state_transitions(stack, aircraft, action):
    m = delivery(stack)["mission"]
    assert cmd(stack, m, action).status_code == 422


def test_authorization_expiry_and_launch_revalidation(stack, aircraft):
    m = delivery(stack)["mission"]
    for action in ["plan", "validate", "authorize"]:
        m = cmd(stack, m, action).json()
    with stack["store"].transaction(stack["tenant"]) as db:
        db.get(Mission, m["id"]).authorized_until = time.time() - 1
    assert cmd(stack, m, "launch").status_code == 422
    with stack["store"].transaction(stack["tenant"]) as db:
        db.get(Mission, m["id"]).authorized_until = time.time() + 100
        db.get(Aircraft, aircraft["id"]).battery = 1
    assert cmd(stack, m, "launch").status_code == 422


@pytest.mark.parametrize(
    "scenario",
    ["low_battery", "communication_loss", "gps_degradation", "weather", "obstruction", "aircraft_fault"],
)
def test_failure_injection_and_recovery(stack, aircraft, scenario):
    m, _ = launch(stack, scenario)
    m = tick(stack, m["id"], 12)
    assert m["state"] in {"returning", "paused"} and not m["delivered"]
    if m["state"] == "paused":
        m = cmd(stack, m, "recover").json()
    m = tick(stack, m["id"], 100)
    assert m["state"] == "aborted" and not m["delivered"]
    with stack["store"].session() as db:
        assert db.get(Aircraft, aircraft["id"]).active_mission_id is None


def test_active_cancellation_returns_home(stack, aircraft):
    m, _ = launch(stack)
    m = tick(stack, m["id"], 6)
    m = cmd(stack, m, "cancel").json()
    assert m["state"] == "returning"
    m = tick(stack, m["id"], 100)
    assert m["state"] == "cancelled" and not m["delivered"]


def test_prelaunch_cancel_releases_aircraft(stack, aircraft):
    m = cmd(stack, delivery(stack)["mission"], "plan").json()
    m = cmd(stack, m, "cancel").json()
    assert m["state"] == "cancelled"
    assert cmd(stack, delivery(stack)["mission"], "plan").status_code == 200


def test_restart_checkpoint_is_deterministic(stack, aircraft):
    from backend.app.db import Store

    m, _ = launch(stack)
    m = tick(stack, m["id"], 7)
    checkpoint = m["tick"]
    fresh = Store(stack["app"].state.settings.database_url)
    with fresh.transaction(stack["tenant"]) as db:
        advance(db, db.get(Mission, m["id"]))
    with fresh.session() as db:
        next_m = db.get(Mission, m["id"])
        assert next_m.tick == checkpoint + 1
        sample = json.loads(next_m.last_telemetry)
        assert sample["seq"] == checkpoint + 1
    fresh.engine.dispose()


def test_telemetry_retention_is_bounded(stack, aircraft):
    m, _ = launch(stack)
    with stack["store"].transaction(stack["tenant"]) as db:
        row = db.get(Mission, m["id"])
        row.state = "outbound"
        row.phase_tick = -1000
        for _ in range(30):
            advance(db, row, 5)
    with stack["store"].session() as db:
        assert (
            db.scalar(select(func.count()).select_from(Telemetry).where(Telemetry.mission_id == m["id"])) == 5
        )


def test_revision_conflict_and_reschedule_invalidates_authorization(stack, aircraft):
    first = delivery(stack)["mission"]
    m = cmd(stack, first, "plan").json()
    assert cmd(stack, first, "validate").status_code == 409
    m = cmd(stack, m, "reschedule", scheduled_at=time.time() + 60).json()
    assert m["state"] == "requested" and m["aircraft_id"] is None and not m["plan"]
    m = cmd(stack, m, "plan").json()
    assert cmd(stack, m, "validate").status_code == 422


def test_no_nan_and_oversize_payloads(stack):
    c = stack["client"]
    assert c.post("/api/v1/missions", content=b"x" * 20000, headers=stack["headers"]).status_code == 413
    assert (
        c.post(
            "/api/v1/aircraft",
            json={"name": "x", "capacity": "NaN"},
            headers={**stack["headers"], "Idempotency-Key": secrets.token_hex(12)},
        ).status_code
        == 422
    )


def test_changed_planning_policy_requires_replan(stack, aircraft):
    m = delivery(stack)["mission"]
    for action in ["plan", "validate", "authorize"]:
        m = cmd(stack, m, action).json()
    r = stack["client"].put(
        "/api/v1/settings",
        json={
            "currency": "ZAR",
            "units": "metric",
            "language": "en",
            "region": "Synthetic Southern campus",
            "virtual_radius_m": 2000,
            "wind_mps": 5,
            "reserve_percent": 35,
            "altitude_m": 50,
        },
        headers=stack["headers"],
    )
    assert r.status_code == 200
    r = cmd(stack, m, "launch")
    assert r.status_code == 422 and "policy changed" in r.text
    m = cmd(stack, m, "replan").json()
    m = cmd(stack, m, "plan").json()
    assert m["plan"]["reserve_percent"] == 35 and m["plan"]["altitude_m"] == 50

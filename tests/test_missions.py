import json
import time
import secrets
import pytest
from sqlalchemy import select, func
from backend.app.models import Mission, Aircraft, MissionEvent, Telemetry
from backend.app.service import advance, mission_out
from autonomy.navigation.geometry import distance, xy
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
    assert abs(m["plan"]["duration_min"] * 60 - m["tick"] * 5) <= 0.31
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


@pytest.mark.parametrize("scenario", ["gps_degradation", "obstruction", "aircraft_fault"])
def test_held_sample_is_persisted_and_replayable(stack, aircraft, scenario):
    m, _ = launch(stack, scenario)
    before = tick(stack, m["id"], 9)
    with stack["store"].transaction(stack["tenant"]) as db:
        advance(db, db.get(Mission, m["id"]), limit=5)
    held = tick(stack, m["id"], 3)
    history = stack["client"].get(f"/api/v1/missions/{m['id']}/history").json()
    latest = history["telemetry"][-1]
    assert held["state"] == latest["flight_mode"] == "paused"
    assert latest == held["last_telemetry"]
    assert latest["seq"] == held["tick"] == 10
    assert latest["simulation_seconds"] == 50
    assert latest["ground_speed_mps"] == 0
    assert latest["position"] == before["last_telemetry"]["position"]
    assert latest["altitude_m"] == before["last_telemetry"]["altitude_m"]
    assert latest["mode"] == "simulation"
    assert [sample["seq"] for sample in history["telemetry"]] == list(range(6, 11))
    if scenario == "gps_degradation":
        assert latest["gps_quality"] == "simulated-degraded"
    if scenario == "aircraft_fault":
        assert latest["motor_health"] == "simulated-fault"
    resumed = cmd(stack, held, "recover").json()
    resumed = tick(stack, resumed["id"])
    history = stack["client"].get(f"/api/v1/missions/{m['id']}/history").json()
    assert history["telemetry"][-2] == latest
    assert history["telemetry"][-1]["seq"] == 11
    assert resumed["state"] == "returning"


def test_active_cancellation_returns_home(stack, aircraft):
    m, _ = launch(stack)
    m = tick(stack, m["id"], 6)
    m = cmd(stack, m, "cancel").json()
    assert m["state"] == "returning"
    m = tick(stack, m["id"], 100)
    assert m["state"] == "cancelled" and not m["delivered"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("endurance", float("inf")),
        ("endurance", 0),
        ("capacity", float("inf")),
        ("capacity", 0),
        ("battery", 101),
    ],
)
def test_launch_rechecks_aircraft_observations_after_authorization(stack, aircraft, field, value):
    mission = delivery(stack)["mission"]
    for action in ["plan", "validate", "authorize"]:
        response = cmd(stack, mission, action)
        assert response.status_code == 200
        mission = response.json()
    with stack["store"].transaction(stack["tenant"]) as db:
        setattr(db.get(Aircraft, aircraft["id"]), field, value)
    denied = cmd(stack, mission, "launch")
    assert denied.status_code == 422
    with stack["store"].session() as db:
        row = db.get(Mission, mission["id"])
        assert row.state == "authorized" and row.tick == 0
        assert row.last_telemetry == "{}"
        assert db.get(Aircraft, aircraft["id"]).status == "available"


def test_unavailable_endurance_during_simulation_holds_without_inventing_an_estimate(stack, aircraft):
    mission, _ = launch(stack)
    before = tick(stack, mission["id"], 6)
    with stack["store"].transaction(stack["tenant"]) as db:
        db.get(Aircraft, aircraft["id"]).endurance = float("inf")
        advance(db, db.get(Mission, mission["id"]))
    held = tick(stack, mission["id"])
    assert held["state"] == "paused"
    assert held["last_telemetry"]["endurance_quality"] == "unavailable"
    assert held["last_telemetry"]["position"] == before["last_telemetry"]["position"]
    operations = stack["client"].get("/api/v1/operations")
    assert operations.status_code == 200
    assert operations.json()["aircraft"][0]["endurance"] is None
    assert cmd(stack, held, "recover").status_code == 422
    with stack["store"].transaction(stack["tenant"]) as db:
        db.get(Aircraft, aircraft["id"]).endurance = 35
    assert cmd(stack, held, "recover").status_code == 200
    resumed = tick(stack, mission["id"])
    assert "endurance_quality" not in resumed["last_telemetry"]


@pytest.mark.parametrize("state", ["taking_off", "outbound", "delivering", "returning", "landing"])
def test_invalid_battery_holds_every_active_phase_and_keeps_replay_truthful(stack, aircraft, state):
    m, _ = launch(stack)
    for _ in range(150):
        if m["state"] == state:
            break
        m = tick(stack, m["id"])
    assert m["state"] == state
    before = m["last_telemetry"]
    with stack["store"].transaction(stack["tenant"]) as db:
        a = db.get(Aircraft, aircraft["id"])
        a.battery = float("inf")
        advance(db, db.get(Mission, m["id"]))
    held = tick(stack, m["id"], 3)
    assert held["state"] == "paused" and held["outcome"] == "aborted"
    assert held["tick"] == m["tick"] + 1
    assert held["last_telemetry"]["battery_quality"] == "unavailable"
    assert held["last_telemetry"]["ground_speed_mps"] == 0
    assert held["last_telemetry"].get("position") == before.get("position")
    history = stack["client"].get(f"/api/v1/missions/{m['id']}/history").json()
    assert history["telemetry"][-1] == held["last_telemetry"]
    assert "Invalid battery observation" in history["events"][-1]["detail"]["reason"]
    operations = stack["client"].get("/api/v1/operations")
    assert operations.status_code == 200
    assert operations.json()["aircraft"][0]["battery"] is None
    assert operations.json()["missions"][0]["last_telemetry"] == held["last_telemetry"]
    assert cmd(stack, held, "recover").status_code == 422
    # Repairing a synthetic observation does not automatically resume motion.
    with stack["store"].transaction(stack["tenant"]) as db:
        db.get(Aircraft, aircraft["id"]).battery = 75
    assert tick(stack, m["id"])["state"] == "paused"
    recovered = cmd(stack, held, "recover").json()
    resumed = tick(stack, recovered["id"])
    assert resumed["state"] == ("landing" if state == "landing" else "returning")
    assert "battery_quality" not in resumed["last_telemetry"]


@pytest.mark.parametrize(("state", "phase_ticks"), [("returning", 4), ("landing", 1)])
@pytest.mark.parametrize("action", ["recover", "cancel"])
def test_held_return_or_landing_preserves_progress_after_operator_action(
    stack, aircraft, state, phase_ticks, action
):
    m, _ = launch(stack)
    for _ in range(150):
        if m["state"] == state:
            break
        m = tick(stack, m["id"])
    assert m["state"] == state
    before = tick(stack, m["id"], phase_ticks)["last_telemetry"]
    with stack["store"].transaction(stack["tenant"]) as db:
        db.get(Aircraft, aircraft["id"]).battery = float("inf")
        advance(db, db.get(Mission, m["id"]))
    held = tick(stack, m["id"])
    assert held["state"] == "paused"
    assert held["last_telemetry"]["position"] == before["position"]
    assert held["last_telemetry"]["altitude_m"] == before["altitude_m"]
    with stack["store"].transaction(stack["tenant"]) as db:
        db.get(Aircraft, aircraft["id"]).battery = 75
    response = cmd(stack, held, action)
    assert response.status_code == 200
    resumed = tick(stack, m["id"])
    latest = resumed["last_telemetry"]
    assert latest["flight_mode"] == state
    if state == "landing":
        assert latest["position"] == m["origin"]
        assert 0 < latest["altitude_m"] < before["altitude_m"]
    else:
        home = m["origin"]
        assert distance(xy(latest["position"], home), xy(before["position"], home)) <= 50.1
        assert distance(xy(latest["position"], home), (0, 0)) < distance(xy(before["position"], home), (0, 0))
    terminal = tick(stack, m["id"], 100)
    assert terminal["state"] == ("cancelled" if action == "cancel" else "aborted")
    assert terminal["last_telemetry"]["position"] == m["origin"]
    assert terminal["last_telemetry"]["altitude_m"] == 0


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

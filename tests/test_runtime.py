import asyncio
import json
import time
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from backend.app.models import Session, Mission, Aircraft
from backend.app.monitoring import Hysteresis
from conftest import delivery, cmd


def test_hysteresis_deduplicates_flapping():
    m = Hysteresis()
    for v in [True, False, True, False, False, True]:
        assert not m.observe(v)
    assert m.status == "unknown"
    for v in [False, False, False]:
        m.observe(v)
    assert m.status == "degraded" and m.transitions == 1
    for _ in range(10):
        assert not m.observe(False)
    assert not m.observe(True)
    assert not m.observe(True)
    assert m.observe(True)
    assert m.status == "healthy" and m.transitions == 2


def test_sse_rechecks_expiry_and_releases_capacity(stack):
    app = stack["app"]
    route = next(r for r in app.routes if r.path == "/api/v1/stream")
    token = stack["client"].cookies.get("drone_session")
    request = SimpleNamespace(
        cookies={"drone_session": token}, is_disconnected=lambda: asyncio.sleep(0, result=False)
    )
    a = {"id": stack["user"], "tenant_id": stack["tenant"]}

    async def exercise():
        response = await route.endpoint(request, a)
        assert app.state.health["streams"] == 1
        first = await anext(response.body_iterator)
        assert first.startswith("event: telemetry")
        with stack["store"].transaction() as db:
            for s in db.scalars(select(Session)):
                s.expires = time.time() - 1
        expired = await anext(response.body_iterator)
        assert expired.startswith("event: expired")
        await response.body_iterator.aclose()
        assert app.state.health["streams"] == 0

    asyncio.run(exercise())


def test_sse_disconnect_has_no_unbounded_queue(stack):
    app = stack["app"]
    route = next(r for r in app.routes if r.path == "/api/v1/stream")
    request = SimpleNamespace(
        cookies={"drone_session": stack["client"].cookies.get("drone_session")},
        is_disconnected=lambda: asyncio.sleep(0, result=True),
    )

    async def exercise():
        response = await route.endpoint(request, {"id": stack["user"], "tenant_id": stack["tenant"]})
        rows = [row async for row in response.body_iterator]
        assert rows == []
        assert app.state.health["streams"] == 0

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("battery", float("inf")),
        ("battery", float("-inf")),
        ("battery", 101),
        ("capacity", float("inf")),
        ("endurance", float("inf")),
        ("capacity", 0),
        ("endurance", 0),
    ],
)
def test_invalid_aircraft_observations_remain_readable_but_cannot_be_planned(stack, aircraft, field, value):
    with stack["store"].transaction(stack["tenant"]) as db:
        setattr(db.get(Aircraft, aircraft["id"]), field, value)
    response = stack["client"].get("/api/v1/operations")
    assert response.status_code == 200
    fleet = response.json()["aircraft"]
    assert fleet[0][field] is None
    if field == "battery":
        assert fleet[0]["battery_quality"] == "unavailable"

    route = next(r for r in stack["app"].routes if r.path == "/api/v1/stream")
    request = SimpleNamespace(
        cookies={"drone_session": stack["client"].cookies.get("drone_session")},
        is_disconnected=lambda: asyncio.sleep(0, result=False),
    )

    async def exercise():
        stream = await route.endpoint(request, {"id": stack["user"], "tenant_id": stack["tenant"]})
        try:
            frame = await anext(stream.body_iterator)
            assert frame.startswith("event: telemetry\ndata: ")
            data = json.loads(frame.split("data: ", 1)[1])
            assert data["aircraft"] == fleet
        finally:
            await stream.body_iterator.aclose()
        assert stack["app"].state.health["streams"] == 0

    asyncio.run(exercise())
    mission = delivery(stack)["mission"]
    denied = cmd(stack, mission, "plan")
    assert denied.status_code == 422
    assert "unavailable" in denied.json()["detail"]
    preview = stack["client"].get("/api/v1/dispatch/preview")
    assert preview.status_code == 200
    assert preview.json()["entries"] == []
    assert "unavailable" in preview.json()["unassigned"][0]["reason"]


def test_scenarios_are_real_catalog(stack):
    r = stack["client"].get("/api/v1/scenarios")
    assert r.status_code == 200
    assert len(r.json()) == 7 and r.json()[0]["id"] == "nominal"


def test_failed_transition_transaction_rolls_back(stack, aircraft, monkeypatch):
    from sqlalchemy.exc import OperationalError
    import backend.app.service as service

    m = delivery(stack)["mission"]

    def failure(*args):
        raise OperationalError("injected storage failure", {}, Exception("synthetic"))

    monkeypatch.setattr(service, "audit", failure)
    assert cmd(stack, m, "plan").status_code == 503
    with stack["store"].session() as db:
        assert db.get(Mission, m["id"]).state == "requested"
        assert db.get(Aircraft, aircraft["id"]).active_mission_id is None


def test_concurrent_assignments_are_serialized(stack, aircraft):
    from concurrent.futures import ThreadPoolExecutor

    missions = [delivery(stack)["mission"], delivery(stack)["mission"]]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda m: cmd(stack, m, "plan").status_code, missions))
    assert sorted(results) == [200, 422]

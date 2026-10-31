"""Offline QGC compatibility and authenticated, non-mutating preview contracts."""

import hashlib
import json
import socket
import time
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.models import Aircraft, Audit, Mission, Tenant, User
from conftest import cmd, delivery
from edge.boundary import DisabledFlightAdapter
from integrations.mavlink.plan import CONTRACT, MAX_ITEMS, PlanError, preview_plan


def plan():
    """Synthetic coordinates, following the documented QGC v1/v2 format."""
    return {
        "fileType": "Plan",
        "version": 1,
        "groundStation": "QGroundControl",
        "geoFence": {"version": 2, "circles": [], "polygons": []},
        "rallyPoints": {"version": 2, "points": []},
        "mission": {
            "version": 2,
            "firmwareType": 12,
            "vehicleType": 2,
            "plannedHomePosition": [52.52, 13.405, 45],
            "globalPlanAltitudeMode": 1,
            "cruiseSpeed": 15,
            "hoverSpeed": 5,
            "items": [
                {
                    "type": "SimpleItem",
                    "command": 22,
                    "frame": 3,
                    "autoContinue": True,
                    "doJumpId": 1,
                    "params": [15, 0, 0, None, 52.52, 13.405, 60],
                    "Altitude": 60,
                    "AltitudeMode": 1,
                    "AMSLAltAboveTerrain": None,
                },
                {
                    "type": "SimpleItem",
                    "command": 16,
                    "frame": 3,
                    "autoContinue": True,
                    "doJumpId": 2,
                    "params": [4, 3, 0, None, 52.523, 13.405, 60],
                    "Altitude": 60,
                    "AltitudeMode": 1,
                },
                {
                    "type": "SimpleItem",
                    "command": 20,
                    "frame": 2,
                    "autoContinue": True,
                    "doJumpId": 3,
                    "params": [0, 0, 0, 0, 0, 0, 0],
                },
            ],
        },
    }


def preview(value, radius=3000):
    return preview_plan(json.dumps(value), {"radius_m": radius})


def test_offline_preview_preserves_navigation_without_creating_authority(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Offline plan inspection must not create a network connection")

    monkeypatch.setattr(socket, "socket", forbidden)
    document = plan()
    original = deepcopy(document)
    raw = json.dumps(document, indent=2)
    result = preview_plan(raw, {"radius_m": 3000})
    assert result["contract_version"] == CONTRACT
    assert result["source_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert result["mode"] == "offline-preview" and result["transport"] == "disabled"
    assert not result["mission_created"] and not result["execution_authorized"]
    assert result["home"]["altitude_amsl_m"] == 45
    assert result["items"][0]["relative_altitude_m"] == 60  # Never subtract home AMSL.
    assert result["items"][-1]["relative_altitude_m"] is None  # RTL altitude is not invented.
    assert [row["parameters"] for row in result["items"]] == [
        row["params"] for row in document["mission"]["items"]
    ]
    assert result["route"][-1]["lat"] == result["home"]["lat"]
    assert result["horizontal_distance_m"] == pytest.approx(667.9, abs=0.1)
    assert result["issues"] == [] and document == original
    with pytest.raises(PermissionError):
        DisabledFlightAdapter().send(result)


def test_ardupilot_land_with_explicit_empty_fence_and_rally_sections():
    value = plan()
    value["mission"]["firmwareType"] = 3
    value["mission"]["items"][-1].update(command=21, frame=3, params=[0, 2, 0, None, 52.52, 13.405, 0])
    result = preview(value)
    assert result["firmware"] == "ArduPilot"
    assert result["items"][-1]["command"] == "land"
    assert result["items"][-1]["relative_altitude_m"] == 0


def test_utf8_bom_is_retained_in_exact_source_identity():
    source = "\ufeff" + json.dumps(plan())
    result = preview_plan(source, {"radius_m": 3000})
    assert result["source_sha256"] == hashlib.sha256(source.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(
    "edit",
    [
        lambda p: p.update(version=2),
        lambda p: p.update(version=True),
        lambda p: p.update(groundStation="other"),
        lambda p: p.update(unknown="private-unsupported-data"),
        lambda p: p.pop("geoFence"),
        lambda p: p.pop("rallyPoints"),
        lambda p: p["mission"].pop("globalPlanAltitudeMode"),
        lambda p: p["mission"].update(version=1),
        lambda p: p["mission"].update(firmwareType=99),
        lambda p: p["mission"].update(vehicleType=1),
        lambda p: p["mission"].update(globalPlanAltitudeMode=4),
        lambda p: p["mission"].update(hoverSpeed=False),
        lambda p: p["mission"].update(plannedHomePosition=[90, 0, 0]),
        lambda p: p["mission"].update(hoverSpeed=10**500),
        lambda p: p["geoFence"].update(circles=[{"private": "unsupported-data"}]),
        lambda p: p["rallyPoints"].update(points=[[52.52, 13.405, 100]]),
        lambda p: p["mission"]["items"][1].update(type="ComplexItem"),
        lambda p: p["mission"]["items"][1].update(command=178),
        lambda p: p["mission"]["items"][1].update(command=183),
        lambda p: p["mission"]["items"][1].update(command=177),
        lambda p: p["mission"]["items"][1].update(frame=10),
        lambda p: p["mission"]["items"][1].update(frame=6),
        lambda p: p["mission"]["items"][1].update(doJumpId=1),
        lambda p: p["mission"]["items"][1].update(doJumpId=True),
        lambda p: p["mission"]["items"][1].update(autoContinue=False),
        lambda p: p["mission"]["items"][1].update(autoContinue=1),
        lambda p: p["mission"]["items"][1].update(params=[0, 0]),
        lambda p: p["mission"]["items"][1].update(Altitude=61),
        lambda p: p["mission"]["items"][1].update(AltitudeMode=2),
        lambda p: p["mission"]["items"][1].update(AMSLAltAboveTerrain=200),
        lambda p: p["mission"]["items"][1]["params"].__setitem__(4, "52.52"),
        lambda p: p["mission"]["items"][1]["params"].__setitem__(5, float("inf")),
        lambda p: p["mission"]["items"][1]["params"].__setitem__(6, float("nan")),
        lambda p: p["mission"]["items"].reverse(),
        lambda p: p["mission"]["items"].pop(),
        lambda p: p["mission"]["items"][-1].update(frame=3),
        lambda p: p["mission"]["items"][-1]["params"].__setitem__(4, 52.52),
    ],
)
def test_unsupported_or_ambiguous_plans_fail_closed_without_echo(edit):
    value = plan()
    edit(value)
    with pytest.raises(PlanError) as error:
        preview(value)
    assert "private-unsupported-data" not in str(error.value)


@pytest.mark.parametrize(
    "source",
    [
        "{",
        "[]",
        '{"fileType":"Plan","fileType":"Plan"}',
        "[" * 2000 + "0" + "]" * 2000,
        "x" * 12289,
        "€" * 4097,
        "\ud800",
    ],
)
def test_invalid_json_nesting_duplicate_keys_and_utf8_byte_limit(source):
    with pytest.raises(PlanError):
        preview_plan(source, {"radius_m": 3000})


def test_item_count_and_complete_order_are_bounded():
    value = plan()
    value["mission"]["items"] = [value["mission"]["items"][1]] * (MAX_ITEMS + 1)
    with pytest.raises(PlanError):
        preview(value)


def test_preview_reports_local_radius_zone_and_altitude_issues_without_rewriting_route():
    value = plan()
    waypoint = value["mission"]["items"][1]
    waypoint["params"][4:7] = [52.523, 13.411, 120]
    waypoint["Altitude"] = 120
    result = preview(value, radius=100)
    assert {issue["code"] for issue in result["issues"]} == {
        "virtual-radius",
        "restricted-zone",
        "relative-altitude",
    }
    assert result["items"][1]["position"] == {"lat": 52.523, "lon": 13.411}
    assert result["items"][1]["relative_altitude_m"] == 120
    assert not result["execution_authorized"]


def test_authenticated_preview_uses_only_current_tenant_policy_and_mutates_no_records(stack, aircraft):
    mission = delivery(stack)["mission"]
    with stack["store"].transaction() as db:
        db.get(Tenant, stack["tenant"]).settings = json.dumps({"virtual_radius_m": 100})
        db.get(Tenant, stack["other"]).settings = json.dumps({"virtual_radius_m": 3000})
        before = {
            model: db.scalar(select(func.count()).select_from(model)) for model in (Mission, Aircraft, Audit)
        }
    payload = {"source": json.dumps(plan())}
    with TestClient(stack["app"]) as anonymous:
        assert anonymous.post("/api/v1/flight-plans/preview", json=payload).status_code == 401
    assert stack["client"].post("/api/v1/flight-plans/preview", json=payload).status_code == 403
    response = stack["client"].post("/api/v1/flight-plans/preview", json=payload, headers=stack["headers"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["virtual_radius_m"] == 100 and result["issues"][0]["code"] == "virtual-radius"
    assert response.headers["Cache-Control"] == "no-store"
    with stack["store"].session() as db:
        assert {model: db.scalar(select(func.count()).select_from(model)) for model in before} == before
        assert db.get(Mission, mission["id"]).state == "requested"
        assert db.get(Aircraft, aircraft["id"]).active_mission_id is None
    assert cmd(stack, mission, "launch").status_code == 422
    # Foreign command data cannot become an authorized application plan.
    assert cmd(stack, mission, "plan", plan=result).status_code == 422


def test_viewer_can_inspect_but_preview_is_rate_limited_and_size_bounded(stack, monkeypatch):
    now = time.time()
    monkeypatch.setattr("backend.app.security.time.time", lambda: now)
    with stack["store"].transaction() as db:
        db.get(User, stack["user"]).role = "viewer"
    payload = {"source": json.dumps(plan())}
    for _ in range(6):
        assert (
            stack["client"]
            .post("/api/v1/flight-plans/preview", json=payload, headers=stack["headers"])
            .status_code
            == 200
        )
    assert (
        stack["client"]
        .post("/api/v1/flight-plans/preview", json=payload, headers=stack["headers"])
        .status_code
        == 429
    )
    assert (
        stack["client"]
        .post("/api/v1/flight-plans/preview", content="x" * 16385, headers=stack["headers"])
        .status_code
        == 413
    )


def test_malformed_preview_returns_fixed_contract_error(stack):
    response = stack["client"].post(
        "/api/v1/flight-plans/preview", json={"source": "{"}, headers=stack["headers"]
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Plan JSON is malformed or nested too deeply"

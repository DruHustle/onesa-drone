import pytest
from autonomy.mission_planning.planner import plan_route
from autonomy.navigation.geometry import geo, xy, segment_clear
from autonomy.safety_supervisor.supervisor import physical_command
from autonomy.mission_planning.dispatch import sequence_deliveries

HOME = {"lat": -22.56, "lon": 17.08}
AIRCRAFT = {"capacity": 4, "category": "multirotor", "endurance": 35, "battery": 100}


def test_deterministic_detour_avoids_restriction():
    destination = geo(240, 200, HOME)
    p = plan_route(HOME, destination, AIRCRAFT, 1)
    assert p == plan_route(HOME, destination, AIRCRAFT, 1)
    assert len(p["waypoints"]) > 2
    points = [xy(x, HOME) for x in p["waypoints"]]
    assert all(segment_clear(a, b, p["zones"]) for a, b in zip(points, points[1:]))


@pytest.mark.parametrize(
    "weight,aircraft,destination,constraints",
    [
        (5, AIRCRAFT, geo(200, 0, HOME), {}),
        (1, {**AIRCRAFT, "battery": 1}, geo(200, 0, HOME), {}),
        (1, AIRCRAFT, geo(4000, 0, HOME), {}),
        (1, AIRCRAFT, geo(200, 0, HOME), {"wind_mps": 30}),
        (1, {**AIRCRAFT, "category": "fixed-wing"}, geo(200, 0, HOME), {}),
    ],
)
def test_infeasible_missions_rejected(weight, aircraft, destination, constraints):
    with pytest.raises(ValueError):
        plan_route(HOME, destination, aircraft, weight, constraints=constraints)


def test_restricted_destination_rejected():
    with pytest.raises(ValueError):
        plan_route(HOME, geo(120, 100, HOME), AIRCRAFT, 1)


def test_physical_boundary_fails_closed():
    with pytest.raises(PermissionError):
        physical_command("arm")


def test_alternatives_are_deterministic_distinct_and_constrained():
    destination = geo(240, 200, HOME)
    p = plan_route(HOME, destination, AIRCRAFT, 1)
    assert len(p["alternatives"]) == 3
    assert len({str(option["waypoints"]) for option in p["alternatives"]}) == 3
    assert p["distance_m"] == min(option["distance_m"] for option in p["alternatives"])
    for option in p["alternatives"]:
        selected = plan_route(HOME, destination, AIRCRAFT, 1, route_index=option["route_index"])
        assert selected["waypoints"] == option["waypoints"]
        points = [xy(point, HOME) for point in option["waypoints"]]
        assert all(segment_clear(a, b, p["zones"]) for a, b in zip(points, points[1:]))
        assert option["energy_percent"] + p["reserve_percent"] <= AIRCRAFT["battery"]


def test_unavailable_alternative_is_rejected_not_substituted():
    with pytest.raises(ValueError, match="alternative route is unavailable"):
        plan_route(HOME, geo(240, 200, HOME), AIRCRAFT, 1, route_index=1, include_alternatives=False)


def queued(identifier, meters=400, **overrides):
    return {
        "id": identifier,
        "label": "Synthetic " + identifier,
        "revision": 1,
        "origin": HOME,
        "destination": geo(meters, 0, HOME),
        "package_weight": 1,
        "created_at": 10,
        "scheduled_at": None,
        **overrides,
    }


def fleet(identifier, **overrides):
    return {**AIRCRAFT, "id": identifier, "name": identifier, **overrides}


def test_dispatch_parallelism_turnaround_and_input_order_determinism():
    missions = [queued("c"), queued("b"), queued("a")]
    aircraft = [fleet("beta"), fleet("alpha")]
    result = sequence_deliveries(missions, aircraft, 100)
    assert result == sequence_deliveries(list(reversed(missions)), list(reversed(aircraft)), 100)
    entries = result["entries"]
    assert [entry["mission_id"] for entry in entries] == ["a", "b", "c"]
    assert entries[0]["estimated_start"] == entries[1]["estimated_start"] == 100
    assert entries[2]["estimated_start"] >= entries[0]["estimated_end"] + 60
    assert entries[2]["predecessor_id"] == "a"
    assert entries[2]["estimated_battery_after"] < entries[0]["estimated_battery_after"]


def test_dispatch_honors_future_start_and_exhausted_reserve():
    result = sequence_deliveries(
        [queued("a", scheduled_at=1000), queued("b")], [fleet("one", battery=35)], 100
    )
    assert result["entries"][0]["mission_id"] == "b"
    assert result["unassigned"][0]["mission_id"] == "a"
    assert "battery/depot" in result["unassigned"][0]["reason"]
    future = sequence_deliveries([queued("a", scheduled_at=1000)], [fleet("one")], 100)
    assert future["entries"][0]["estimated_start"] == 1000


def test_dispatch_does_not_invent_reposition_or_ignore_payload():
    other_home = geo(1500, 0, HOME)
    result = sequence_deliveries(
        [
            queued("a", meters=100),
            queued("b", origin=other_home, destination=geo(100, 0, other_home)),
            queued("c", package_weight=20),
        ],
        [fleet("one")],
        100,
    )
    assert [entry["mission_id"] for entry in result["entries"]] == ["a"]
    assert {entry["mission_id"] for entry in result["unassigned"]} == {"b", "c"}
    assert "capacity" in next(entry["reason"] for entry in result["unassigned"] if entry["mission_id"] == "c")


def test_dispatch_capacity_is_bounded():
    with pytest.raises(ValueError, match="bounded planning capacity"):
        sequence_deliveries([queued(str(index)) for index in range(26)], [fleet("one")], 100)

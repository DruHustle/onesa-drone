"""The independent supervisor must not trust numeric comparisons with NaN."""

from copy import deepcopy

import pytest

from autonomy.mission_planning.planner import plan_route
from autonomy.navigation.geometry import geo
from autonomy.safety_supervisor.supervisor import supervision, validate_launch


HOME = {"lat": -22.56, "lon": 17.08}
AIRCRAFT = {
    "capacity": 4,
    "category": "multirotor",
    "endurance": 35,
    "battery": 100,
    "status": "available",
    "connectivity": "simulated",
}


def mission():
    return {
        "plan": plan_route(HOME, geo(400, 0, HOME), AIRCRAFT, 1),
        "origin": HOME.copy(),
        "package_weight": 1,
        "scheduled_at": None,
    }


def test_valid_plan_still_passes_independent_supervisor():
    assert validate_launch(mission(), AIRCRAFT, 100) == []


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf"), None, True, "25"])
@pytest.mark.parametrize(
    "target,key",
    [
        ("aircraft", "battery"),
        ("aircraft", "capacity"),
        ("aircraft", "endurance"),
        ("mission", "package_weight"),
        ("mission", "scheduled_at"),
        ("plan", "energy_percent"),
        ("plan", "reserve_percent"),
        ("plan", "wind_mps"),
        ("plan", "altitude_m"),
        ("origin", "lat"),
        ("origin", "lon"),
        ("waypoint", "lat"),
        ("waypoint", "lon"),
    ],
)
def test_nonfinite_or_untyped_launch_data_is_refused(invalid, target, key):
    if target == "mission" and key == "scheduled_at" and invalid is None:
        assert validate_launch(mission(), AIRCRAFT, 100) == []
        return
    candidate = mission()
    aircraft = AIRCRAFT.copy()
    section = {
        "aircraft": aircraft,
        "mission": candidate,
        "plan": candidate["plan"],
        "origin": candidate["origin"],
        "waypoint": candidate["plan"]["waypoints"][1],
    }[target]
    section[key] = invalid
    assert validate_launch(candidate, aircraft, 100)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf"), None, True])
def test_invalid_clock_refuses_launch(invalid):
    assert validate_launch(mission(), AIRCRAFT, invalid)


@pytest.mark.parametrize("waypoints", [None, {}, "invalid", [None, HOME]])
def test_malformed_route_is_refused_without_crashing(waypoints):
    candidate = deepcopy(mission())
    candidate["plan"]["waypoints"] = waypoints
    assert validate_launch(candidate, AIRCRAFT, 100)


@pytest.mark.parametrize("battery", [float("nan"), float("inf"), float("-inf"), None, True, "75", -1, 101])
def test_invalid_battery_holds_simulation(battery):
    decision = supervision("nominal", 5, battery, 35)
    assert decision and decision[0] == "paused"


def test_valid_supervision_behavior_is_preserved():
    assert supervision("nominal", 5, 100, 35) is None
    assert supervision("nominal", 5, 0, 35)[0] == "returning"
    assert supervision("gps_degradation", 10, 75, 35)[0] == "paused"


@pytest.mark.parametrize(
    "field,value", [("battery", 101), ("battery", -1), ("capacity", 0), ("endurance", 0)]
)
def test_invalid_observation_ranges_refuse_launch(field, value):
    assert validate_launch(mission(), {**AIRCRAFT, field: value}, 100)


@pytest.mark.parametrize("endurance", [float("nan"), float("inf"), float("-inf"), None, True, "35", 0, -1])
def test_invalid_endurance_holds_simulation(endurance):
    assert supervision("nominal", 5, 75, endurance)[0] == "paused"

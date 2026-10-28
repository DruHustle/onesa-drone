import pytest
from autonomy.mission_planning.planner import plan_route
from autonomy.navigation.geometry import geo, xy, segment_clear
from autonomy.safety_supervisor.supervisor import physical_command

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

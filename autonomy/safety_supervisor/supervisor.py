"""Independent deterministic authority. No generative dependencies or I/O."""

from autonomy.navigation.geometry import xy, segment_clear, distance
from autonomy.mission_planning.planner import DEFAULT_ZONES
from autonomy.observations import finite_number, positive_number, valid_battery

FAILURES = {
    "low_battery",
    "communication_loss",
    "gps_degradation",
    "weather",
    "obstruction",
    "aircraft_fault",
}


def finite_point(value):
    return isinstance(value, dict) and all(finite_number(value.get(key)) for key in ("lat", "lon"))


def validate_launch(mission, aircraft, current_time, policy=None):
    issues = []
    p = mission["plan"]
    if not isinstance(p, dict) or not p or p.get("mode") != "simulation":
        issues.append("A simulation plan is required")
        return issues
    values = [
        current_time,
        mission.get("package_weight"),
        aircraft.get("capacity"),
        aircraft.get("endurance"),
        aircraft.get("battery"),
    ]
    if mission.get("scheduled_at") is not None:
        values.append(mission["scheduled_at"])
    values.extend(p.get(key) for key in ("energy_percent", "reserve_percent", "wind_mps", "altitude_m"))
    waypoints = p.get("waypoints")
    if (
        not all(finite_number(value) for value in values)
        or not finite_point(mission.get("origin"))
        or not isinstance(waypoints, list)
        or not all(finite_point(point) for point in waypoints)
    ):
        return ["Mission safety data must contain finite numeric observations"]
    if not valid_battery(aircraft["battery"]) or any(
        not positive_number(aircraft[key]) for key in ("capacity", "endurance")
    ):
        return ["Aircraft battery, capacity or endurance observation is unavailable"]
    if aircraft["status"] != "available":
        issues.append("Aircraft is unavailable")
    if aircraft["connectivity"] != "simulated":
        issues.append("Simulation device identity required")
    if mission["package_weight"] > aircraft["capacity"]:
        issues.append("Payload exceeds capacity")
    if p and aircraft["battery"] < p["energy_percent"] + p["reserve_percent"]:
        issues.append("Battery reserve check failed")
    if mission.get("scheduled_at") and mission["scheduled_at"] > current_time:
        issues.append("Scheduled launch time has not arrived")
    if p:
        if policy and any(p.get("constraints", {}).get(k) != v for k, v in policy.items()):
            issues.append("Safety policy changed; release and replan the mission")
        points = [xy(w, mission["origin"]) for w in p.get("waypoints", [])]
        if len(points) < 2 or any(not segment_clear(a, b, DEFAULT_ZONES) for a, b in zip(points, points[1:])):
            issues.append("Route violates virtual restricted-zone policy")
        if p.get("wind_mps", 100) > 10 or p.get("altitude_m", 1000) > 100:
            issues.append("Plan exceeds simulation safety policy")
        if any(distance((0, 0), point) > 3000 for point in points):
            issues.append("Virtual geofence check failed")
    return issues


def supervision(scenario, tick, battery, endurance):
    if not valid_battery(battery):
        return "paused", "Invalid battery observation: simulation held for operator recovery"
    if not positive_number(endurance):
        return "paused", "Invalid endurance observation: simulation held for operator recovery"
    if battery < 20:
        return "returning", "Low battery: virtual return-to-home"
    if tick == 10 and scenario in FAILURES:
        if scenario in {"gps_degradation", "aircraft_fault", "obstruction"}:
            return "paused", f"{scenario}: simulation held for operator recovery"
        return "returning", f"{scenario}: virtual return-to-home"
    return None


def physical_command(*_args, **_kwargs):
    raise PermissionError(
        "Physical aircraft interfaces are disabled. Separate authorization and safety validation are required."
    )

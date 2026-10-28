"""Replayable discrete kinematics, intentionally not a flight dynamics model."""

from math import atan2, degrees, ceil
from autonomy.navigation.geometry import xy, geo, distance

STEP_SECONDS = 5


def path_position(points, fraction, home):
    nodes = [xy(p, home) for p in points]
    lengths = [distance(a, b) for a, b in zip(nodes, nodes[1:])]
    remaining = max(0, min(1, fraction)) * sum(lengths)
    for a, b, d in zip(nodes, nodes[1:], lengths):
        if remaining <= d:
            t = remaining / d if d else 0
            return geo(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, home), degrees(
                atan2(b[0] - a[0], b[1] - a[1])
            ) % 360
        remaining -= d
    return points[-1], 0


def sample(mission, aircraft, previous):
    state = mission.state
    p = __import__("json").loads(mission.plan)
    home = __import__("json").loads(mission.origin)
    n = max(4, ceil(p["distance_m"] / 2 / 10 / STEP_SECONDS))
    phase = mission.phase_tick
    pos, heading = path_position(p["waypoints"], min(1, phase / n), home)
    if state == "returning":
        start = previous.get("return_start") or previous.get("position") or p["waypoints"][-1]
        # Reverse the flown safe route rather than cutting through a virtual restriction.
        prior = previous.get("return_path")
        if not prior:
            prefix = previous.get("path_prefix") or [home]
            prior = [start, *reversed(prefix)]
        pos, heading = path_position(prior, min(1, phase / n), home)
    else:
        prior = None
        start = None
    altitude = p["altitude_m"]
    if state == "taking_off":
        pos = home
        altitude = min(1, phase / 3) * altitude
    if state == "landing":
        pos = home
        altitude = max(0, 1 - phase / 3) * altitude
    if state == "delivering":
        pos = p["waypoints"][-1]
        altitude = 6
    prefix = [
        w
        for i, w in enumerate(p["waypoints"])
        if i == 0
        or mission.phase_tick / n
        >= sum(
            distance(xy(a, home), xy(b, home)) for a, b in zip(p["waypoints"][:i], p["waypoints"][1 : i + 1])
        )
        / (p["distance_m"] / 2)
    ]
    total_ticks = 6 + 2 * n + 3
    battery = max(0, aircraft.battery - p["energy_percent"] / total_ticks)
    return {
        "seq": mission.tick,
        "mode": "simulation",
        "simulation_seconds": mission.tick * STEP_SECONDS,
        "position": pos,
        "altitude_m": round(altitude, 1),
        "ground_speed_mps": 10 if state in {"outbound", "returning"} else 0,
        "heading": round(heading, 1),
        "battery_percent": round(battery, 3),
        "remaining_endurance_min": round(aircraft.endurance * battery / 100, 1),
        "motor_health": "illustrative-nominal",
        "flight_mode": state,
        "connectivity": "simulated-link-lost"
        if mission.scenario == "communication_loss" and mission.tick >= 10
        else "simulated",
        "gps_quality": "simulated-nominal",
        "payload_state": "delivered" if mission.delivered else "aboard",
        "progress_percent": min(99, round(mission.tick / total_ticks * 100)),
        "return_start": start,
        "return_path": prior,
        "path_prefix": prefix if state == "outbound" else previous.get("path_prefix", [home]),
        "leg_ticks": n,
    }

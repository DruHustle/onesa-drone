"""Deterministic visibility graph. Constraints are synthetic, not aviation data."""

from heapq import heappush, heappop
from math import cos, sin, pi, hypot
from autonomy.navigation.geometry import xy, geo, distance, segment_clear

DEFAULT_ZONES = [{"x": 120, "y": 100, "radius": 55, "label": "Illustrative restricted campus area"}]
DEFAULT_CONSTRAINTS = {
    "radius_m": 3000,
    "wind_mps": 5,
    "max_wind_mps": 10,
    "reserve_percent": 25,
    "altitude_m": 60,
}


def plan_route(home, destination, aircraft, weight, zones=None, constraints=None):
    c = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
    zones = DEFAULT_ZONES if zones is None else zones
    end = xy(destination, home)
    if hypot(*end) < 20:
        raise ValueError("Destination must be at least 20 m from home")
    if hypot(*end) > c["radius_m"]:
        raise ValueError("Outside virtual operating radius")
    if weight > aircraft["capacity"]:
        raise ValueError("Payload exceeds illustrative aircraft capacity")
    if aircraft["category"] == "fixed-wing":
        raise ValueError("Fixed-wing delivery requires a qualified runway model; viewer only")
    if c["wind_mps"] > c["max_wind_mps"]:
        raise ValueError("Virtual wind exceeds planning policy")
    nodes = [(0, 0), end]
    for z in zones:
        # Circumscribed polygon edges maintain clearance around circular constraints.
        radius = (z["radius"] + 22) / cos(pi / 8)
        nodes.extend((z["x"] + cos(k * pi / 4) * radius, z["y"] + sin(k * pi / 4) * radius) for k in range(8))
    q = [(0, 0)]
    costs = {0: 0}
    prev = {}
    while q:
        cost, i = heappop(q)
        if cost != costs[i]:
            continue
        if i == 1:
            break
        for j, p in enumerate(nodes):
            if i == j or hypot(*p) > c["radius_m"] or not segment_clear(nodes[i], p, zones):
                continue
            nc = cost + distance(nodes[i], p)
            if nc < costs.get(j, float("inf")):
                costs[j] = nc
                prev[j] = i
                heappush(q, (nc, j))
    if 1 not in costs:
        raise ValueError("No route satisfies virtual restricted-zone clearance")
    route = [1]
    while route[-1] != 0:
        route.append(prev[route[-1]])
    points = [geo(*nodes[i], home) for i in reversed(route)]
    duration = (costs[1] * 2 / 10 + 24) / 60
    energy = duration / aircraft["endurance"] * 100 * (1 + weight / aircraft["capacity"] * 0.3)
    if energy + c["reserve_percent"] > aircraft["battery"]:
        raise ValueError("Insufficient estimated energy including return and reserve")
    return {
        "waypoints": points,
        "distance_m": round(costs[1] * 2, 1),
        "duration_min": round(duration, 2),
        "energy_percent": round(energy, 2),
        "reserve_percent": c["reserve_percent"],
        "altitude_m": c["altitude_m"],
        "wind_mps": c["wind_mps"],
        "zones": zones,
        "constraints": c,
        "algorithm": "visibility-graph-dijkstra-v1",
        "mode": "simulation",
        "physics": "illustrative-kinematic",
        "advisories": ["Synthetic zones and weather; no authoritative airspace or aviation clearance."],
    }

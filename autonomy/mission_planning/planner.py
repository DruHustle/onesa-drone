"""Deterministic visibility graph. Constraints are synthetic, not aviation data."""

from heapq import heappush, heappop
from math import cos, sin, pi, hypot, ceil
from autonomy.navigation.geometry import xy, geo, distance, segment_clear

DEFAULT_ZONES = [{"x": 120, "y": 100, "radius": 55, "label": "Illustrative restricted campus area"}]
DEFAULT_CONSTRAINTS = {
    "radius_m": 3000,
    "wind_mps": 5,
    "max_wind_mps": 10,
    "reserve_percent": 25,
    "altitude_m": 60,
}


def shortest_path(nodes, zones, radius_m, excluded=frozenset(), exclude_direct=False):
    q = [(0, 0)]
    costs = {0: 0}
    prev = {}
    while q:
        cost, i = heappop(q)
        if cost != costs[i]:
            continue
        if i == 1:
            route = [1]
            while route[-1] != 0:
                route.append(prev[route[-1]])
            return list(reversed(route)), cost
        for j, p in enumerate(nodes):
            if (
                i == j
                or j in excluded
                or (exclude_direct and {i, j} == {0, 1})
                or hypot(*p) > radius_m
                or not segment_clear(nodes[i], p, zones)
            ):
                continue
            nc = cost + distance(nodes[i], p)
            if nc < costs.get(j, float("inf")):
                costs[j] = nc
                prev[j] = i
                heappush(q, (nc, j))
    return None


def plan_route(
    home,
    destination,
    aircraft,
    weight,
    zones=None,
    constraints=None,
    route_index=0,
    include_alternatives=True,
):
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
    # Two bounded lateral candidates also allow alternatives for a clear direct leg.
    length = hypot(*end)
    offset = min(350, max(80, length * 0.35))
    nodes.extend(
        (end[0] / 2 + sign * -end[1] / length * offset, end[1] / 2 + sign * end[0] / length * offset)
        for sign in (-1, 1)
    )
    primary = shortest_path(nodes, zones, c["radius_m"])
    if primary is None:
        raise ValueError("No route satisfies virtual restricted-zone clearance")
    paths = [primary]
    excluded = set(primary[0][1:-1])
    if include_alternatives:
        for _ in range(2):
            alternate = shortest_path(nodes, zones, c["radius_m"], excluded, exclude_direct=True)
            if alternate is None:
                break
            paths.append(alternate)
            excluded.update(alternate[0][1:-1])
    options = []
    for indices, meters in sorted(paths, key=lambda path: (path[1], path[0])):
        # Match both quantized flight legs and the three 15-second ground phases.
        duration = (2 * max(4, ceil(meters / 50)) * 5 + 45) / 60
        energy = duration / aircraft["endurance"] * 100 * (1 + weight / aircraft["capacity"] * 0.3)
        if energy + c["reserve_percent"] <= aircraft["battery"]:
            options.append(
                {
                    "route_index": len(options),
                    "waypoints": [geo(*nodes[i], home) for i in indices],
                    "distance_m": round(meters * 2, 1),
                    "duration_min": round(duration, 2),
                    "energy_percent": round(energy, 2),
                }
            )
    if not options:
        raise ValueError("Insufficient estimated energy including return and reserve")
    if route_index < 0 or route_index >= len(options):
        raise ValueError("Requested alternative route is unavailable under current constraints")
    return {
        **options[route_index],
        "alternatives": options,
        "reserve_percent": c["reserve_percent"],
        "altitude_m": c["altitude_m"],
        "wind_mps": c["wind_mps"],
        "zones": zones,
        "constraints": c,
        "algorithm": "visibility-graph-dijkstra-v2",
        "mode": "simulation",
        "physics": "illustrative-kinematic",
        "advisories": ["Synthetic zones and weather; no authoritative airspace or aviation clearance."],
    }

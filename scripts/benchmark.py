"""Deterministic local planner latency benchmark; no hardware capability claim."""

from time import perf_counter
from statistics import median
import json
from autonomy.mission_planning.planner import plan_route
from autonomy.navigation.geometry import geo

home = {"lat": -22.56, "lon": 17.08}
a = {"capacity": 4, "category": "multirotor", "endurance": 35, "battery": 100}
times = []
for i in range(100):
    destination = geo(240 + i, 200, home)
    start = perf_counter()
    plan_route(home, destination, a, 1)
    times.append((perf_counter() - start) * 1000)
print(
    json.dumps(
        {
            "scope": "local-kinematic-planner-only",
            "iterations": 100,
            "median_ms": round(median(times), 3),
            "p95_ms": round(sorted(times)[94], 3),
            "max_ms": round(max(times), 3),
        }
    )
)

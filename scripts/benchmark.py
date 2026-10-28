"""Deterministic local planner latency benchmark; no hardware capability claim."""

from time import perf_counter
from statistics import median
import json
from autonomy.mission_planning.planner import plan_route
from autonomy.navigation.geometry import geo
from autonomy.mission_planning.dispatch import sequence_deliveries

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
deliveries = [
    {
        "id": f"mission-{i:02}",
        "label": "Synthetic benchmark",
        "revision": 1,
        "origin": home,
        "destination": geo(240 + i, 200, home),
        "package_weight": 1,
        "created_at": 0,
        "scheduled_at": None,
    }
    for i in range(25)
]
fleet = [{**a, "id": f"aircraft-{i:02}", "name": f"SIM-{i:02}"} for i in range(50)]
dispatch_times = []
for _ in range(5):
    start = perf_counter()
    result = sequence_deliveries(deliveries, fleet, 100)
    dispatch_times.append((perf_counter() - start) * 1000)
print(
    json.dumps(
        {
            "scope": "bounded-dispatch-preview-only",
            "missions": 25,
            "aircraft": 50,
            "iterations": 5,
            "assigned": len(result["entries"]),
            "median_ms": round(median(dispatch_times), 3),
            "max_ms": round(max(dispatch_times), 3),
        }
    )
)

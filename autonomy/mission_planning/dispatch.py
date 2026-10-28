"""Bounded advisory sequencing of single-delivery round trips, never launch authority."""

from autonomy.mission_planning.planner import plan_route, DEFAULT_CONSTRAINTS
from autonomy.navigation.geometry import xy, distance

MAX_DELIVERIES = 25
MAX_AIRCRAFT = 50
TURNAROUND_SECONDS = 60


def sequence_deliveries(deliveries, aircraft, now, constraints=None):
    if len(deliveries) > MAX_DELIVERIES or len(aircraft) > MAX_AIRCRAFT:
        raise ValueError("Dispatch preview exceeds bounded planning capacity")
    policy = {**DEFAULT_CONSTRAINTS, **(constraints or {})}
    fleet = {a["id"]: a for a in sorted(aircraft, key=lambda a: a["id"])}
    remaining = {m["id"]: m for m in deliveries}
    ready = dict.fromkeys(fleet, now)
    battery = {key: a["battery"] for key, a in fleet.items()}
    depot, prior, plans, reasons = {}, {}, {}, {}
    for m in sorted(deliveries, key=lambda m: m["id"]):
        reasons[m["id"]] = set()
        for key, a in fleet.items():
            try:
                plans[m["id"], key] = plan_route(
                    m["origin"],
                    m["destination"],
                    a,
                    m["package_weight"],
                    constraints=policy,
                    include_alternatives=False,
                )
            except ValueError as error:
                reasons[m["id"]].add(str(error))
    entries = []
    while remaining:
        candidates = []
        for mid, m in remaining.items():
            for aid in fleet:
                p = plans.get((mid, aid))
                if not p or p["energy_percent"] + p["reserve_percent"] > battery[aid]:
                    continue
                # Every round trip returns to its own origin. No invented repositioning.
                if aid in depot and distance(xy(m["origin"], depot[aid]), (0, 0)) > 0.1:
                    continue
                start = max(ready[aid], m.get("scheduled_at") or now)
                end = start + p["duration_min"] * 60
                candidates.append((start, end, m["created_at"], mid, aid))
        if not candidates:
            break
        start, end, _, mid, aid = min(candidates)
        m = remaining.pop(mid)
        p = plans[mid, aid]
        battery[aid] = round(battery[aid] - p["energy_percent"], 2)
        entries.append(
            {
                "mission_id": mid,
                "mission_revision": m["revision"],
                "label": m["label"],
                "aircraft_id": aid,
                "aircraft_name": fleet[aid]["name"],
                "predecessor_id": prior.get(aid),
                "estimated_start": start,
                "estimated_end": end,
                "distance_m": p["distance_m"],
                "energy_percent": p["energy_percent"],
                "estimated_battery_after": battery[aid],
            }
        )
        depot[aid] = m["origin"]
        prior[aid] = mid
        ready[aid] = end + TURNAROUND_SECONDS
    return {
        "mode": "simulation",
        "advisory": True,
        "at": now,
        "algorithm": "earliest-release-shortest-completion-v1",
        "entries": entries,
        "unassigned": [
            {
                "mission_id": mid,
                "label": m["label"],
                "reason": (
                    "No remaining battery/depot-compatible slot; recharge and repositioning are not scheduled"
                    if any(pair[0] == mid for pair in plans)
                    else "; ".join(sorted(reasons[mid])) or "No available aircraft"
                ),
            }
            for mid, m in sorted(remaining.items())
        ],
        "turnaround_seconds": TURNAROUND_SECONDS,
        "notice": "Preview reserves nothing. Each mission still needs a fresh plan, preflight and explicit authorization.",
    }

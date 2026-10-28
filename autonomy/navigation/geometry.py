"""Local geographic projection for synthetic short-range campus routes."""

from math import radians, cos, hypot


def xy(point, home):
    return (
        (point["lon"] - home["lon"]) * 111320 * cos(radians(home["lat"])),
        (point["lat"] - home["lat"]) * 111320,
    )


def geo(x, y, home):
    return {"lat": home["lat"] + y / 111320, "lon": home["lon"] + x / (111320 * cos(radians(home["lat"])))}


def distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])


def segment_clear(a, b, zones, clearance=20):
    for z in zones:
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = (
            max(0, min(1, ((z["x"] - a[0]) * dx + (z["y"] - a[1]) * dy) / (dx * dx + dy * dy)))
            if dx or dy
            else 0
        )
        if hypot(a[0] + t * dx - z["x"], a[1] + t * dy - z["y"]) <= z["radius"] + clearance:
            return False
    return True

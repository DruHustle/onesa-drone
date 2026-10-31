"""Bounded QGroundControl plan inspection, independent of execution authority.

References and the deliberately limited supported subset are documented beside
this module. It performs no I/O, constructs no MAVLink packets and creates no
application mission. Every original navigation parameter is retained for review.
"""

import hashlib
import json
import math

from autonomy.mission_planning.planner import DEFAULT_ZONES
from autonomy.navigation.geometry import distance, segment_clear, xy

CONTRACT = "onesa-flight-plan-preview-v1"
MAX_PLAN_BYTES = 12 * 1024
MAX_ITEMS = 25
COMMANDS = {16: "waypoint", 20: "return-to-launch", 21: "land", 22: "takeoff"}
FIRMWARE = {3: "ArduPilot", 12: "PX4"}
MULTIROTORS = {2, 3, 4, 13, 14, 15}


class PlanError(ValueError):
    """A fixed, safe explanation; input values are never echoed in errors."""


def require(condition, message):
    if not condition:
        raise PlanError(message)


def number(value, low, high, message):
    require(type(value) in (int, float) and low <= value <= high and math.isfinite(value), message)
    return value


def integer(value, allowed, message):
    require(type(value) is int and value in allowed, message)
    return value


def fields(value, required, optional, message):
    require(type(value) is dict and required <= value.keys() and value.keys() <= required | optional, message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON fields are not supported")
        result[key] = value
    return result


def invalid_constant(_value):
    raise PlanError("Plan numbers must be finite JSON numbers")


def empty_section(value, names, message):
    fields(value, {"version", *names}, set(), message)
    integer(value["version"], {2}, message)
    require(all(value[name] == [] for name in names), message)


def preview_plan(source, policy):
    try:
        raw = source.encode("utf-8")
    except (AttributeError, UnicodeError):
        raise PlanError("A UTF-8 QGroundControl .plan document is required") from None
    require(0 < len(raw) <= MAX_PLAN_BYTES, "Plan file must be at most 12 KiB")
    try:
        plan = json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except PlanError:
        raise
    except (ValueError, RecursionError):
        raise PlanError("Plan JSON is malformed or nested too deeply") from None
    fields(
        plan,
        {"fileType", "version", "groundStation", "mission", "geoFence", "rallyPoints"},
        set(),
        "Unsupported Plan document fields",
    )
    require(
        plan["fileType"] == "Plan" and plan["groundStation"] == "QGroundControl",
        "QGroundControl Plan required",
    )
    integer(plan["version"], {1}, "Only Plan file version 1 is supported")
    if "geoFence" in plan:
        empty_section(
            plan["geoFence"],
            {"circles", "polygons"},
            "Imported geofences are not supported; they cannot be dropped",
        )
    if "rallyPoints" in plan:
        empty_section(
            plan["rallyPoints"], {"points"}, "Imported rally points are not supported; they cannot be dropped"
        )
    mission = plan["mission"]
    fields(
        mission,
        {
            "version",
            "firmwareType",
            "vehicleType",
            "plannedHomePosition",
            "items",
            "cruiseSpeed",
            "hoverSpeed",
            "globalPlanAltitudeMode",
        },
        set(),
        "Unsupported mission fields",
    )
    integer(mission["version"], {2}, "Only mission version 2 is supported")
    firmware = integer(mission["firmwareType"], FIRMWARE, "Only PX4 and ArduPilot plan metadata is supported")
    vehicle = integer(mission["vehicleType"], MULTIROTORS, "Only multirotor plan metadata is supported")
    if "globalPlanAltitudeMode" in mission:
        integer(
            mission["globalPlanAltitudeMode"], {0, 1}, "Absolute and terrain altitude modes are not supported"
        )
    speeds = {
        name: number(mission[name], 0.1, 100, "Plan speed must be finite and between 0.1 and 100 m/s")
        for name in ("cruiseSpeed", "hoverSpeed")
    }
    home_values = mission["plannedHomePosition"]
    require(
        type(home_values) is list and len(home_values) == 3,
        "Planned home requires latitude, longitude and AMSL altitude",
    )
    home = {
        "lat": number(home_values[0], -85, 85, "Home latitude is outside the local projection range"),
        "lon": number(home_values[1], -180, 180, "Invalid home longitude"),
        "altitude_amsl_m": number(home_values[2], -500, 10000, "Invalid home AMSL altitude"),
    }
    original = mission["items"]
    require(
        type(original) is list and 3 <= len(original) <= MAX_ITEMS,
        "Use 3 to 25 items: takeoff, waypoints, then land or return",
    )
    items, route = [], [{"sequence": 0, **home, "x_m": 0, "y_m": 0}]
    for sequence, item in enumerate(original, 1):
        fields(
            item,
            {"type", "command", "frame", "params", "autoContinue", "doJumpId"},
            {"Altitude", "AltitudeMode", "AMSLAltAboveTerrain"},
            "Only simple navigation items with known fields are supported",
        )
        require(item["type"] == "SimpleItem", "Complex survey and scan items require a separate adapter")
        command = integer(
            item["command"],
            COMMANDS,
            "Unsupported command; camera, speed, jumps and actuation are not imported",
        )
        integer(item["doJumpId"], {sequence}, "Item identifiers must be consecutive from 1")
        require(item["autoContinue"] is True, "Paused mission items are not supported")
        expected = {22} if sequence == 1 else {20, 21} if sequence == len(original) else {16}
        require(command in expected, "Use takeoff first, waypoints in order, and land or return last")
        params = item["params"]
        require(
            type(params) is list and len(params) == 7, "Every simple item requires exactly seven parameters"
        )
        if command == 20:
            integer(item["frame"], {2}, "Return-to-launch must use the mission frame")
            require(
                all(type(v) in (int, float) and v == 0 for v in params),
                "Return-to-launch parameters must be zero",
            )
            require(
                not (item.keys() & {"Altitude", "AltitudeMode", "AMSLAltAboveTerrain"}),
                "Return-to-launch cannot specify an altitude",
            )
            point, altitude = {"lat": home["lat"], "lon": home["lon"]}, None
        else:
            integer(
                item["frame"],
                {3},
                "Navigation must use global latitude/longitude and altitude relative to home (frame 3)",
            )
            number(
                params[0],
                0,
                600 if command == 16 else 90 if command == 22 else 1000,
                "Invalid navigation parameter 1",
            )
            number(
                params[1],
                0,
                1000 if command == 16 else 2 if command == 21 else 0,
                "Invalid navigation parameter 2",
            )
            if command == 21:
                require(params[1] in {0, 1, 2}, "Unsupported precision landing mode")
            number(
                params[2],
                -1000 if command == 16 else 0,
                1000 if command == 16 else 0,
                "Invalid navigation parameter 3",
            )
            if params[3] is not None:
                number(params[3], -360, 360, "Yaw must be a bounded angle or null")
            point = {
                "lat": number(params[4], -85, 85, "Waypoint latitude is outside the local projection range"),
                "lon": number(params[5], -180, 180, "Invalid waypoint longitude"),
            }
            altitude = number(params[6], 0, 10000, "Relative altitude must be finite and nonnegative")
            if "Altitude" in item:
                require(
                    number(item["Altitude"], 0, 10000, "Invalid display altitude") == altitude,
                    "Display altitude disagrees with the navigation parameter",
                )
            if "AltitudeMode" in item:
                integer(item["AltitudeMode"], {0, 1}, "Absolute and terrain altitude modes are not supported")
            require(item.get("AMSLAltAboveTerrain") is None, "Terrain-derived altitude is not supported")
        x, y = xy(point, home)
        route.append({"sequence": sequence, **point, "x_m": x, "y_m": y})
        items.append(
            {
                "sequence": sequence,
                "command": COMMANDS[command],
                "command_id": command,
                "frame": item["frame"],
                "position": point,
                "relative_altitude_m": altitude,
                "parameters": list(params),
            }
        )

    radius = number(policy.get("radius_m"), 100, 3000, "Current virtual radius policy is unavailable")
    issues = []
    for item, prior, point in zip(items, route, route[1:]):
        location = (point["x_m"], point["y_m"])
        if distance((0, 0), location) > radius:
            issues.append(
                {
                    "sequence": item["sequence"],
                    "code": "virtual-radius",
                    "detail": "Outside this workspace's virtual operating radius",
                }
            )
        if not segment_clear((prior["x_m"], prior["y_m"]), location, DEFAULT_ZONES):
            issues.append(
                {
                    "sequence": item["sequence"],
                    "code": "restricted-zone",
                    "detail": "Leg crosses the illustrative restricted zone or its 20 m clearance",
                }
            )
        altitude = item["relative_altitude_m"]
        if altitude is not None and (altitude > 100 or (item["command_id"] != 21 and altitude < 10)):
            issues.append(
                {
                    "sequence": item["sequence"],
                    "code": "relative-altitude",
                    "detail": "Outside the illustrative 10–100 m navigation altitude range",
                }
            )
    return {
        "contract_version": CONTRACT,
        "mode": "offline-preview",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "firmware": FIRMWARE[firmware],
        "vehicle_type": vehicle,
        "home": home,
        "speeds_mps": speeds,
        "items": items,
        "route": route,
        "horizontal_distance_m": round(
            sum(distance((a["x_m"], a["y_m"]), (b["x_m"], b["y_m"])) for a, b in zip(route, route[1:])), 1
        ),
        "virtual_radius_m": radius,
        "zones": [dict(zone) for zone in DEFAULT_ZONES],
        "issues": issues,
        "transport": "disabled",
        "mission_created": False,
        "execution_authorized": False,
        "notice": "Geometry preview only. Home is planned, return altitude is controller-defined, and route, timing, energy and controller behavior are not flight-qualified.",
    }

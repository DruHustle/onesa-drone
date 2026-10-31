# Offline flight-controller plan boundary

`plan.py` inspects a bounded QGroundControl `.plan` file and produces the
`onesa-flight-plan-preview-v1` read-only contract. In the console, open **Flight
plans**, select a synthetic file, and choose **Preview flight plan**. The checked
fixture is `tests/fixtures/controller-preview.plan`.

The parser follows the official [QGC Plan format](https://docs.qgroundcontrol.com/Stable_V5.0/en/qgc-dev-guide/file_formats/plan.html)
and [MAVLink command/frame definitions](https://mavlink.io/en/messages/common.html),
inspected on 31 October 2026. This is an independently implemented, deliberately
limited profile; no QGC, firmware or MAVLink library is downloaded at runtime.

## Accepted profile

- UTF-8 JSON, at most 12 KiB; Plan version 1 and mission version 2.
- QGroundControl metadata, PX4 or ArduPilot firmware type, multirotor vehicle type.
- Explicit home latitude/longitude/AMSL altitude, cruise/hover speeds and global
  altitude mode. `geoFence` and `rallyPoints` must exist with version 2 and empty
  arrays; unsupported fences or rally points are never silently discarded.
- Three to 25 `SimpleItem` entries, consecutive IDs and `autoContinue=true`:
  takeoff (22), one or more waypoints (16), then land (21) or return-to-launch (20).
- Coordinate items use MAVLink frame 3: geographic degrees and metres relative to
  home. Frame 2 is accepted only for return-to-launch with zero parameters. Local,
  integer-coordinate, absolute and terrain frames are rejected.
- Display altitude must agree with parameter 7. Explicit frame 3 remains required
  when the QGC altitude selector is unspecified/mixed (0) or relative (1); absolute
  and terrain selector values are rejected. Terrain-derived altitude is unsupported.
- All seven navigation parameters remain in the preview. Unsupported commands,
  complex patterns, duplicate fields/IDs, non-finite numbers, excessive nesting,
  ambiguous or unknown fields fail with bounded errors that omit input values.

The SHA-256 identifies the exact UTF-8 source bytes submitted. Planned home AMSL
and relative navigation altitude remain distinct. Return position is shown as
planned home; the controller's return altitude is **unknown**, not fabricated.
The local projection reports horizontal route length and conflicts with the current
tenant's illustrative radius, circular restriction/clearance and altitude range.
It does not estimate flight time, fuel/energy, wind feasibility or real airspace.

## Application and execution separation

`POST /api/v1/flight-plans/preview` requires the current session, Origin and CSRF,
including for viewers. Inspection is limited to six requests per user per minute
and the existing 16 KiB total request-body ceiling. It reads only the current
tenant's policy, saves no file/mission/audit payload, reserves no aircraft, returns
`no-store` and has no outbound I/O. A preview never supplies launch authorization.
Changing file or session discards old frontend reads/results.

`edge.boundary.DisabledFlightAdapter` continues to reject connection and send
attempts. No socket, UDP listener, serial transport, message encoder, arm/mode
change or waypoint upload is implemented. An eventual controller adapter needs
separate, pinned and isolated SITL qualification, device identity/message validation,
explicit command acknowledgement and the independent safety supervisor. Hardware
qualification and physical-flight authorization remain outside this product.

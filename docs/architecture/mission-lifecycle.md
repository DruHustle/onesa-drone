# Mission contract and persistence

The independent `POST /api/v1/flight-plans/preview` operation reads a bounded
QGroundControl file for format/geometry inspection. It does not enter this lifecycle,
create an event, reserve an aircraft or confer authorization. A parsed controller
plan is not accepted as a field of a mission command. The normal deterministic
planner, preflight and separate safety supervisor remain authoritative for every
simulation launch. See [the supported file profile](../../integrations/mavlink/README.md).

```mermaid
stateDiagram-v2
    [*] --> requested
    requested --> planned: deterministic plan / reserve aircraft
    planned --> validated: explicit preflight rules
    validated --> authorized: authenticated operator / five-minute expiry
    authorized --> taking_off: safety supervisor rechecks
    taking_off --> outbound
    outbound --> delivering
    delivering --> returning: simulated parcel confirmation
    returning --> landing
    landing --> completed
    outbound --> paused: injected GPS / obstruction / fault
    paused --> returning: operator recovery
    outbound --> returning: cancellation / simulated failsafe
    landing --> aborted: recovery / failsafe outcome
    landing --> cancelled: cancellation outcome
```

The full transition graph in `autonomy/decision_engine/states.py` is authoritative.
Prelaunch cancellation terminates and releases the reservation. Reschedule/replan
invalidates prior authorization. Cancellation during a flight requests virtual return;
it does not teleport an aircraft or claim an immediate delivery.

The independent supervisor rejects nonfinite or untyped numeric launch data before
performing route, payload or energy comparisons. An unavailable endurance or invalid
battery observation holds the simulation in `paused`, including during return and
landing. Recovery requires a valid replacement observation and explicit operator
action; repairing the observation alone never resumes simulation. A held return or
descent retains its completed phase ticks, position and safe path. Recovery and
cancellation continue that checkpoint instead of replaying an earlier route segment.
Physical aircraft interfaces remain disabled. These checks do not qualify a hardware
safety system or turn reference simulation limits into aircraft specifications.

Operations and SSE encode invalid aircraft battery/capacity/endurance observations
as JSON `null`; an invalid battery also has `battery_quality: "unavailable"`. Planning
and dispatch refuse those aircraft until valid observations are available. Held
telemetry retains its last valid numeric sample for historical provenance, adds the
unavailable battery quality marker, and never presents that retained value as a fresh
battery observation. The console shows "Unavailable" and gaps in battery history.
An unavailable endurance estimate has `endurance_quality: "unavailable"` and the
console identifies that estimate as unavailable. Launch revalidates battery,
capacity and endurance after authorization, as well as the planned route inputs.

All mutations authenticate a current user and server role, enforce the user's tenant,
lock the tenant record and check object revision. `Idempotency-Key` commands persist
actor, request digest and response in the same transaction as state/event/audit changes.
Same key/body returns the prior receipt; a different actor/body conflicts. Every mission
transition has a persisted actor, correlation ID, UTC epoch time and reason. UUIDs
identify objects but never authorize access. Simulation worker commands use a distinct
internal actor and deterministic per-tick correlation identity.

Telemetry samples are mode-labelled, ordered per mission and bounded to 600 records.
The worker resumes the persisted phase/tick after restart. SSE holds one bounded
snapshot at a time, yields to network backpressure and renews authorization checks.
A separate read-only capability endpoint exposes state, completion and progress only;
tracking links expire after seven days and are not included in reports or logs.

Route planning uses a local visibility graph and deterministic Dijkstra search. It
minimizes route distance around illustrative restricted circles, selects the feasible
available aircraft with the lowest estimated energy and budgets return plus reserve.
Up to three deterministic waypoint alternatives must satisfy the same geofence,
restriction, payload and energy constraints. Route preference is part of the initial
plan command and its idempotency receipt. A different preference requires release
and replan; previous preflight and authorization are invalidated. Duration includes
both quantized legs and all three 15-second takeoff/delivery/landing phases.

`GET /api/v1/dispatch/preview` sequences up to 25 requested deliveries over up to
50 currently available aircraft; truncation is explicit. The deterministic heuristic
chooses the earliest eligible start, then shortest completion, with stable identifiers
as tie breakers. It budgets each complete round trip, subtracts illustrative energy,
preserves reserve, and adds a 60-second turnaround. Aircraft cannot change depots
within a sequence. Recharge, depot transfers and deadlines are not invented.
The authenticated tenant-scoped preview is read-only and rate-limited to six per
user per minute. It reserves nothing; every chosen assignment is rechecked by the
normal transactional plan and launch commands. This sequences separate round trips;
multi-stop flights and globally optimal vehicle routing remain separate development.
Fixed-wing dispatch is refused pending a runway/release model.

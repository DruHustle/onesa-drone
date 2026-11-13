# Onesa Drone

Canonical source: [DruHustle/onesa-drone](https://github.com/DruHustle/onesa-drone).
Run product commands from this repository root. Drone retains independent builds,
releases, authentication and data. Root workflows execute application, browser and
native compile checks. Latest work from the former consolidated checkout is retained
here. Historical release records preserve their original source identities; source
restoration alone does not qualify a hosted release. See [standalone source](docs/engineering/standalone-source.md).

**Intelligent Delivery Beyond Roads**

An independent, simulation-only aerial logistics platform under development. No
physical aircraft commands, flight certification or operational delivery service.

The first simulation release is available at [drone.onesa.eu](https://drone.onesa.eu).
Its accepted application revision is `ff493035cbc11a31312f6fae9364825c761b992a`.
The frontend runs on Vercel and the API and independent PostgreSQL databases run
on existing Oracle capacity. Staging remains protected. Later source changes are
not deployed merely because their repository checks pass.

The frontend is organized as [web](frontend/drone/web/) and [iOS/Android mobile](frontend/drone/mobile/). The CHUBORY A77 mobile prototype supports offline mission drafts, route geometry, simulated position, encrypted operator notes, a shareable non-flying bench record and a link to the CHUBORY FLY store listing; no device commands, verified GPS or remote live video are available. The existing Vercel release path remains compatible. See [frontend setup](frontend/README.md) and [mobile instructions](frontend/drone/mobile/README.md).

The architecture combines a React/Three.js console, FastAPI, SQLAlchemy operational
records, deterministic mission planning and an isolated safety supervisor. Local
SQLite supports offline development; deployment uses independently provisioned
PostgreSQL. See docs/architecture/decisions.md and docs/engineering/local-development.md.

## Working product

- Fleet registration/editing, inspections, decommissioning and illustrative charging.
- Delivery requests, deterministic assignment/routing, preflight, expiring simulation
  authorization, launch, cancellation, reschedule, failure recovery and reporting.
- Feasible alternative routes and bounded dispatch sequencing with battery budgets,
  scheduled releases, depot consistency and round-trip turnaround estimates.
- Durable tenant-scoped mission/event/audit/telemetry records; private recipient tracking.
- Procedural Three.js campus, animated aircraft, cameras, day/night/weather visuals,
  low-power rendering and command-free recorded replay.
- Automatically loaded NVIDIA conveyor, cart and warehouse-rack reference models,
  with an inspection camera, static previews, source attribution and graphics recovery.
  The local derivatives add visual detail only; they do not validate flight physics.
- Read-only operational assistant, analytics, incidents and service health observations.
- Offline QGroundControl flight-plan inspection with an explicit PX4/ArduPilot
  navigation subset, local geometry and virtual-policy findings. No device commands.

[Run locally and demonstrate](docs/engineering/local-development.md) ·
[Architecture and decisions](docs/architecture/decisions.md) ·
[Mission contract](docs/architecture/mission-lifecycle.md) ·
[Verification](docs/engineering/verification.md) ·
[Deployment and costs](infrastructure/deployment.md) ·
[Shared Onesa account](docs/engineering/shared-account.md) ·
[Regulatory intake matrix](docs/regulatory-requirements.md)

The local assistant is a deterministic summary until the existing Onesa AI adapter
has an approved dedicated identity. Maps, weather and aircraft performance are
synthetic. PX4/Gazebo, authoritative airspace, fixed-wing dispatch, multi-stop routing,
full console localisation, real-data privacy approval and hardware qualification
remain outstanding. Physical flight is unavailable by construction.

Private vulnerability reporting: info@onesa.eu. Do not put secrets, private operational
records or customer data in GitHub issues. No project license is assigned.

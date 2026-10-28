# Architecture decisions

## ADR 001 — Independent simulation product

Inspected Onesa Company Portal, AI Platform, AI Robot, Smart Factory frontend,
backend and edge on 28 October 2026. Ownership is DruHustle. Reuse independent
frontend/backend releases, scoped sessions, explicit object ownership, hosted
credential-free checks, private monitoring and dev → staging → main. Existing
Vercel UI / Oracle Free backend patterns are candidates, not provisioned capacity.
No sibling imports, shared databases, copied production credentials or new Site host.

## ADR 002 — Small operational core

React/Vite and lazy Three.js render an aircraft and procedural campus without external
asset downloads. FastAPI owns authentication, tenant-scoped APIs and bounded SSE.
SQLAlchemy supports SQLite development and PostgreSQL deployment with a small pool.
All state transitions, aircraft reservations, idempotency receipts, audit records
and simulation checkpoints commit atomically. Tenant locks serialize mutations;
a single worker advances persisted deterministic ticks. Scale-out is deliberately
unsupported until a qualified distributed lease is implemented.

## ADR 003 — Three boundaries

The planner and safety supervisor are deterministic Python modules under autonomy.
Simulation is kinematic, illustrative and not aerodynamically validated. PX4 SITL /
Gazebo are evaluated separately; no PX4 binary is downloaded or executed. Physical
adapters always reject execution. AI can explain tenant-filtered data, never mutate
missions. The current AI Platform uses user-owned sessions and conversations; a
service identity is not assumed. Optional integration uses a separately approved
server-side delegated session and the existing conversation/completion contract.

## ADR 004 — Defensive operation

Opaque hashed sessions, versioned scrypt passwords (N=16384, r=8, p=5), Origin/CSRF enforcement and server role
checks. No public privileged registration. Admin bootstrap is an offline CLI.
Tracking uses high-entropy expiring read capabilities and returns no customer address,
aircraft ID, route or precise location. Tenant audit chains are transactional and
append-only through the app, not a claim of tamper-proof database administration.
SSE sends bounded snapshots, revalidates authorization and holds no event queue.
Retention limits telemetry to recent per-mission samples; full events remain durable.

## ADR 005 — Design provenance

Onesa Design System 1.0.0 foundation copied by pinned hash from the Portal. Product
layout is task-oriented; system appearance is CSS-only. Procedural models are original
illustrations with editable illustrative performance, never manufacturer specifications.

The selected scrypt profile balances the 256 MiB runtime budget against the current
[OWASP password-storage configurations](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
Unknown accounts use one precomputed dummy-hash verification. Peer and account
limits bound expensive login work; prior local hashes upgrade on successful login.
Python module directories use underscores to preserve standard import semantics.

## ADR 006 — Bounded deterministic dispatch

Route alternatives use the same visibility graph with excluded internal waypoints;
additional lateral candidates support clear direct routes. Every option is rechecked
against radius, circular restrictions and battery reserve. This is a bounded corridor
choice, not an exhaustive search for every possible trajectory.

Dispatch sequencing is an advisory earliest-release/shortest-completion heuristic
over independently validated round trips. Limit input size and recomputation frequency
instead of introducing an unbounded vehicle-routing service. The UI binds preview
state to the signed-in account and rechecks actual aircraft availability when planning.
No new schema, launch state, background job, external solver or AI tool is required.

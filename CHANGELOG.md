# Changelog

## Unreleased — 0.1 simulation implementation

- A logout whose session is concurrently revoked still clears the cookie and
  acknowledges success; it no longer reports a misleading storage failure.
- Release-unit fixtures isolate their commissioning registry even under root test
  execution. No real release record or production authority is created.

- Adds independent authenticated tenant workspaces, fleet CRUD and inspection records.
- Implements transactional, idempotent delivery planning, authorization and simulation.
- Adds deterministic safety failure scenarios, persisted telemetry, private tracking,
  replay, procedural 3D, operational summaries, incidents and infrastructure observations.
- Adds a read-only existing Onesa AI contract adapter, disabled until an approved
  tenant-bound delegated identity is commissioned. Local summaries are labelled.
- Prepares pinned container, restricted database role, CI and security headers.
- No hosted staging/production release or physical operation is claimed.

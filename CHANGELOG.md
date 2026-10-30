# Changelog

## Accepted simulation release — 29 October 2026

- Application revision `ff493035cbc11a31312f6fae9364825c761b992a` is accepted at
  [drone.onesa.eu](https://drone.onesa.eu), with Vercel frontend and Oracle API.
  Source followed PRs #15 and #16 and passed its own first-attempt Main checks.
- Genuine staging and production observations verified simulation delivery,
  authentication, tenant isolation, telemetry, persistence, verified database TLS,
  isolated encrypted restore and responsive WebGL views. The temporary project
  testing credential was revoked after verification.
- This is a simulation release. Live AI identity, physical-device performance,
  commercial hosting eligibility, production backup scheduling and any physical
  aircraft operation remain unqualified. The company product page is pending its
  separate Portal release. Later Dev changes are not part of the accepted runtime.

## Unreleased — 0.1 simulation implementation

- Ignore pending API responses after a sign-in, sign-out or expiry changes the
  session. Clear account-specific drafts, reports, tracking and dispatch state at
  that boundary, and ignore queued expiry events from a closed previous stream.
- An older operation cannot overwrite a newer operation's busy/error state.
  Existing server authorization, idempotency and simulation supervision still apply.
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
- The implementation entries above do not qualify later source changes or any
  physical operation; the accepted runtime is identified separately above.

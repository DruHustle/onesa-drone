# Changelog

- Add an iPhone Simulator UI check for saving a route, reopening it after relaunch,
  and reading the locked aircraft and video status screens.

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

- Refuse nonfinite launch data in the independent supervisor. Invalid battery/endurance
  observations pause every simulated flight phase and remain visibly unavailable
  in fleet, telemetry and replay until repaired and explicitly recovered. Operations
  and SSE remain readable; unavailable aircraft observations cannot enter planning.
  Recovery and cancellation preserve held return/descent progress.
  Physical interfaces remain disabled; this is not hardware qualification.

- Add optional shared Onesa sign-in and central administrator access. Users keep
  one account across AI Platform, Company Portal, Drone and Robot; Drone receives
  current permissions through the registered issuer and retains tenant boundaries.
- Add explicit workspace selection, fresh MFA for administrator changes, central
  account-management links and sign-out across applications. No local Drone
  password is created for a shared account and no email-based linking occurs.
- Add the opt-in, additive identity migration without rewriting existing users,
  data or the original schema fingerprint. Deployment remains gated on issuer
  registration, migration, exact-source acceptance and the owner execution path.
- Prepare an explicit owner release profile for shared identity with matched private
  configuration and genuine browser PKCE/MFA sign-in. Keep existing delivery, tenant,
  viewer, persistence, restore and responsive WebGL checks; source tests do not
  establish hosted qualification or deployment.
- Add three locally hosted NVIDIA SimReady environment references from pinned
  revision `4763fbfaa4f8e97658e68b57d01b4c86659e08b5`, retaining CC BY 4.0 attribution,
  original provenance and rendered previews. Bounded downloads verify size and
  SHA-256 before a static-only GLTF parse. A dedicated environment camera, keyboard
  pan, retry, no-WebGL previews and graphics-context recovery preserve mission use.
  These scene props have no connection to flight planning, telemetry or actuation.
- Dispose replaced route-zone geometry and reference resources when scenes close.
- Add a read-only QGroundControl plan preview for a bounded PX4/ArduPilot multirotor
  subset. Preserve source identity and navigation parameters, report virtual-policy
  conflicts, and reject unsupported frames, commands, fences and malformed files.
  The console previews geometry without creating missions or enabling transports.
- Reject excessively nested provider JSON in portable and legacy advisory responses.
  Decoder exhaustion returns the labelled local summary without leaking provider data.
- Retry only downloading the immutable CI scanner, at most three bounded attempts.
  An unavailable scanner or a failed vulnerability scan still fails verification.
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

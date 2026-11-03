# Shared Onesa account

The optional shared sign-in uses the existing Company Portal as the account
authority for AI Platform, Company Portal, Drone and Robot. A person registers
once. The central administrator assigns application access and Drone workspace
memberships; Drone never creates another password or matches an existing local
account by email. A centrally granted Onesa administrator can administer Drone
and explicitly select an existing workspace. Simulation and safety checks remain
in force for every role.

This implementation is source preparation. Enabling it requires coordinated
issuer/client registration, the additive database migration, runtime grants,
deployment and hosted acceptance. A passing local test or merged PR does not
establish that shared sign-in is active on staging or production.

## Sign-in experience

With shared identity enabled, the login screen offers **Continue with Onesa**.
Registration, password recovery and MFA take place on the central account site.
An existing central browser session can return the person directly to Drone.
No credentials or bearer tokens pass through frontend JavaScript or local storage.

A normal account with one authorized Drone membership opens that workspace. A
person with several memberships chooses a workspace. An Onesa administrator
always makes an explicit workspace choice, even if only one is present. An
account without a membership sees an access-request explanation rather than a
second signup form. Changing workspace rotates CSRF state, clears previous
workspace data/drafts, closes the prior telemetry stream and records the change
in the selected tenant's audit chain.

The administration page links to central account and membership management. It
does not provision a second Drone password. **Sign out of Onesa** revokes all
grants and central sessions for the current account; each product rejects its
old session on its next authenticated request. Existing Drone streams revalidate
centrally every ten seconds and also check local expiry/selected workspace for
every frame. Local logout clears the Drone session and private interface even
if the account service cannot be reached; the interface explicitly says when
sign-out from other applications could not be confirmed. A service failure is
never converted to an offline administrator session.

## Protocol and authorization

The independent `backend/app/onesa_identity.py` module implements the common
Onesa protocol v1. Authorization uses confidential OAuth authorization codes,
S256 PKCE, random state, a browser-bound HttpOnly transaction cookie and a
single-use, five-minute server transaction. Codes are exchanged server to
server with the registered client's Basic credentials. The callback is exactly
`APP_ORIGIN/api/v1/auth/identity/callback`; no caller-supplied return URL is used.
The browser receives only a random, host-only, HttpOnly Drone session cookie.

Current identity and permissions come from the configured issuer's authenticated
`POST /session` response, with exact issuer/audience/subject, verified email,
bounded expiry, real authentication time, MFA methods and explicit entitlement
checks. This is a custom authenticated session assertion; an unverified ID token
is never treated as OIDC identity evidence. Requests have a five-second timeout,
a 64 KiB response limit, no redirects, no permission cache and no fallback to
legacy credentials when shared identity is enabled.

The stable identity key is `(issuer, sub)`. Drone records the actor as
`identity:<sub>` in its own audits and idempotency receipts. Existing tenant-owned
records, local users, password hashes and the original schema fingerprint are
unchanged. Email is display/profile data, never an account-linking key.
Opaque central grants and temporary PKCE verifiers are encrypted at rest with
Fernet and a dedicated owner-held key; the database stores only a hash of the
local browser token. Tampered ciphertext is rejected. After each central
validation, Drone rechecks its local session to reject a concurrent logout,
expiry or workspace change before returning authorization.

Normal users need an explicit central `onesa_memberships` entry naming the Drone
tenant UUID and viewer/operator/admin role. Their effective workspace role is
the lower of the application role and that membership role: application access
sets the maximum permission, and membership can narrow it for each tenant.
A central application-role downgrade takes effect on the next request.
No customer tenant is selected from an environment default or inferred from an
email domain. Global administrators need the central `global_admin` role and MFA
evidence. Product administrator sessions also require MFA. Administrator writes and
global administrator workspace switching require an actual authentication within
five minutes; selecting **Confirm administrator sign-in** requests a new login
and MFA and preserves the previously chosen workspace for the same account.
Confirmation is also bound to the original live local session and its CSRF and
workspace state. A concurrent logout, expiry or workspace switch cancels the
confirmation instead of restoring an older session.
Ordinary sign-in also records the previous local session at the start and
retires it on successful account replacement, even when a cross-site callback
does not include the application's Strict session cookie.
All operational queries, object lookup, transaction locks and audit chains still
apply the selected tenant predicate. No role enables physical flight.

## Configuration and migration

Use separate clients, credentials and exact callbacks for staging and production.
Keep client secrets in the existing owner-controlled runtime secret mechanism.
Do not add secrets to Git, frontend variables, artifacts or logs.

| Variable | Purpose |
| --- | --- |
| `ONESA_IDENTITY_ENABLED` | Defaults to `false`; enable only for the coordinated cutover. |
| `ONESA_IDENTITY_ISSUER` | Exact HTTPS `${PORTAL_ORIGIN}/api/v1/identity`, without a trailing slash. |
| `ONESA_IDENTITY_CLIENT_ID` | Centrally registered confidential Drone client. |
| `ONESA_IDENTITY_CLIENT_SECRET` | Dedicated server-only secret of at least 32 characters. |
| `ONESA_IDENTITY_CALLBACK` | Exactly `${APP_ORIGIN}/api/v1/auth/identity/callback`. |
| `ONESA_IDENTITY_ENCRYPTION_KEY` | Dedicated server-held Fernet key, generated separately for each environment; never stored in the database. |

Loopback HTTP is permitted only when both the application and identity server
are local development origins. Hosted HTTPS, secure cookies and verified
PostgreSQL TLS remain mandatory.
Rotating the encryption key invalidates existing Drone shared sessions and
pending login flows; users sign in again. Preserve the existing runtime secret
custody and perform a coordinated key rotation instead of trying to decrypt with
an unqualified fallback key.

The existing migrator command, `python -m scripts.migrate`, with the intended
identity configuration applies the additive `0002-identity` migration. It adds
`identity_transactions` and `identity_sessions` only after verifying the existing
`0001` fingerprint. It does not alter or rewrite existing users, sessions or
operational tables. Grant the existing restricted runtime role
`SELECT, INSERT, UPDATE, DELETE` on those two new tables, as documented in
`infrastructure/postgres-roles.sql`. Hosted runtime startup verifies both schema
fingerprints and never runs DDL.

Before cutover, register the exact client/callback, grant the owner's central
administrator role through the supported owner process, enroll MFA, and assign
any ordinary test-user memberships. Deploy with existing Oracle capacity and
Vercel ingress. Verify actual source bindings and complete browser acceptance
against the exact protected staging frontend before using its stable alias.
No new hosting resource, paid provider, automatic account promotion or hardware
commissioning is part of this change.

For rollback, retain the prior runtime and frontend and preserve all tables.
Disabling shared identity returns to the prior explicitly provisioned local
authentication model. It does not convert central accounts into local passwords
or import their privileges. Central identities remain in Portal and can be used
again on a later qualified cutover. Do not drop the additive tables to roll back.

## Verification

`tests/test_shared_identity.py` exercises browser-bound single-use callbacks,
no-email/no-password projections, tenant selection and CSRF rotation, ordinary
membership isolation, live role downgrade, concurrent workspace changes,
reauthentication and account-switch session retirement, encrypted custody,
partial central logout and additive migration compatibility. The copied protocol tests
exercise issuer/audience/MFA/expiry/response/transport rejection without live
credentials. Browser tests use local synthetic identity responses for shared
sign-in, pending access, workspace selection, administrator confirmation and
honest partial-logout recovery. They do not constitute hosted
SSO acceptance or physical-flight qualification.

## Owner qualification integration

The source includes the explicit `shared-identity-v1` qualification profile for
the existing independent backend and frontend components. A plan binds exact
source, client and encryption-key hashes, matched probe helpers, isolated existing
synthetic subjects/workspaces and the private fixture lifetime. Only the six
identity settings may differ from the retained runtime and migrator configurations.
The existing owner custody, signed context, exact-source image/security checks,
one-request provider budget and simulation restrictions remain required.

For this profile only, the fixture file's configuration pin hashes its canonical
credential payload, excluding exactly `created_at` and `expires_at`. Every actor,
password, MFA seed, scope, source and preview credential stays pinned. All other
configuration files retain their byte hashes. After verification of a reserved
owner staging context or recorded deployment intent, the runner can refresh that
environment's time envelope once, for at most one hour and no later than the
earliest expiry in its complete signed ancestry. The owner decision, exact source,
commissioned runner and durable reservation are verified again before replacement.
It durably records private intent and completion, preserves concurrent changes
and refuses an uncertain replay. Actual browser/API acquisition always
requires a current lease. A renewal changes neither runtime configuration nor
release authority, and it cannot extend an already running browser's expiry.

Backend qualification starts a real browser-bound PKCE transaction at the exact
application origin and completes Portal password/MFA and the actual callback. It
verifies the returned subject, workspace and role before using the product cookie
on that same host. It never transfers a browser cookie to the separate API host or
creates a replacement password user. The ordinary API scenario still completes a
simulation delivery, checks foreign-tenant denial and viewer command denial, and
verifies monitoring, history and private tracking. The existing identity migration
adds only its two session tables and their restricted runtime grants.

Frontend qualification uses **Continue with Onesa** and retains the existing live
telemetry, complete delivery, replay, tracking, WebGL, responsive and accessibility
journeys. Protected previews use isolated no-redirect handshakes and host-only
automation cookies; credentials are never global browser headers. Source tests
exercise refusal and private-session boundaries. They do not establish deployed
identity, hosted acceptance or production authority.

### Retained-image rollback qualification

The shared profile requires `retained-identity-disabled-v1` in the existing
configuration-pinned rollback file. Its `environments.staging` and
`environments.production` entries name the retained `source_commit`, immutable
`image_id`, `runtime_sha256` and `migrator_sha256`. These hashes refer to the
plan's retained configuration files, so later frontend qualification does not
depend on a mutable currently serving runtime file. Both retained configurations
must leave shared identity absent or disabled. The existing native profile keeps
its `first-release-disable-only` policy.

Before staging changes any hosted schema or service, the commissioned runner
executes `oracle_drone_rollback.py` and its matched container-custody helper. The
candidate image initializes the real additive schema in a disposable PostgreSQL
database and creates new synthetic users with fixed local UUIDs, tenants and
roles. A separate owner connection applies the existing restricted runtime
grants. The application itself runs as its image's nonroot user and connects as
the restricted database role. It creates a real delivery checkpoint, dumps and
restores the database, and runs each pinned prior image against that restored
schema. The native application verifies password authentication, immutable user
and tenant identities, viewer and foreign-tenant refusal, CSRF, continued
simulation delivery, telemetry, audit chains, private tracking and scoped logout.

The sandbox has no network, published ports, hosted database URL, real account
credentials or external AI credentials. Only a private Unix socket is shared
between bounded containers; database files remain in temporary memory storage.
Loopback HTTP and synthetic database settings are explicit proof overrides.
The prior runtime and migrator bytes remain pinned, and the proof neither changes
them nor rewrites any hosted schema. The actual retained image's source label,
immutable identity and runtime user must agree with the plan.

Successful qualification binds both environments' results to the current signed
context, candidate source, image identities, configuration hashes and actual
schema fingerprints. This is a newly observed compatibility result under that
qualification; it does not assert a previously accepted deployment. Operations
and production reuse the same private receipt, and the later signed qualification
must contain its exact digest. They cannot rerun or substitute a production proof.
No PASS receipt is written until every operation-owned container is positively
observed absent and the private socket directory is removed. A timed-out create,
ambiguous daemon result, changed ownership or uncertain removal retains the
diagnostics and fails without retrying the operation or touching unrelated
containers.

`tests/test_retained_identity_rollback.py` exercises the same real API programs
with local SQLite copies and, when `DRONE_TEST_DATABASE_URL` is present, actual
PostgreSQL restricted-role grants in newly created test databases. SQLite
explicitly reports the grant check as `NOT_RUN`, which the owner gate rejects.
Native source tests do not replace the required retained-image Docker dump and
restore proof or authenticated hosted acceptance.

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

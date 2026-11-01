# Verification scope and release gates

## Built release package audit — 31 October 2026

The follow-up review of dev d66f0af exercised the actual built frontend through
the controlled Vercel packager. Its original suffix policy rejected the seven
new JSON/GLB files; the emitted JavaScript also lacked the complete Three.js MIT
notice. Earlier packager fixtures contained only HTML and JavaScript.

The correction requires the trusted catalogue's thirteen NVIDIA files and the
exact renderer notice, validates pinned source bytes before output creation, and
rechecks copied target bytes before producing the release manifest. Only the exact
reviewed NVIDIA JSON/GLB paths are eligible. Existing hidden-file, symlink, source/
environment identity, per-file and aggregate size restrictions remain enforced.
The production build verifies the notice against the pinned installed package.

Local verification passed all 28 packaging/transport cases, 47 release/custody
cases and 12 frontend session/asset cases, plus the TypeScript production build
and notice check. The new actual-build regression packaged 19 files totalling
5,640,218 bytes, compared every delivered byte/hash with the build, and verified
all thirteen NVIDIA files and the full installed Three.js notice. Missing and
same-length corrupted references, arbitrary JSON/GLB files, unknown NVIDIA files
and oversized JavaScript are explicitly refused.

The actual-build packaging regression is now a mandatory named CI release step.
This working-source result requires fresh exact-source CI and the existing hosted
staging/release gates before main or production promotion. Synthetic package
metadata grants no provider authority or hosted acceptance.

## NVIDIA reference environment — 31 October 2026

The development change based on `340d14e` adds three independently packaged NVIDIA
SimReady browser derivatives with complete source/license records. The runtime
checks exact byte size, SHA-256 and the static embedded-resource GLB profile before
loading. Scene references never enter mission APIs, flight planning, simulation
supervision, telemetry or physical transports. There are no backend schema or
dependency changes. [Asset details](nvidia-reference-assets.md) describe the source
revision and the deliberate visual-only boundary.

Executed local verification:

- 149 backend cases passed on SQLite and again against a new isolated PostgreSQL
  16 database; 47 release/custody and 24 packaging/transport cases passed.
- Five existing frontend session units plus seven asset/catalogue cases passed.
  Asset checks parse all three real GLBs, check finite geometry and exact triangle
  counts, validate every model/preview/license/provenance file hash, and reject
  oversized, truncated, corrupt, cancelled and unsupported resource inputs.
- All 21 Chromium browser journeys passed, including eight reference-environment
  cases. They exercise automatic loading, environment framing, actual 503 and
  integrity failures/retry, unavailable WebGL, lost/restored graphics context,
  leaving a scene during downloads, desktop/mobile views, both OS color schemes,
  reduced motion, forced colors, keyboard provenance and axe accessibility. The
  original delivery, tracking, replay, flight-plan and session-isolation journeys
  also passed. Opening the reference views sent no mission/control writes.
- TypeScript, production build, Ruff, diff checks and repository-history hygiene
  passed. The pinned npm dependency audit reported zero known vulnerabilities.
  The existing Three.js bundle-size advisory remains a build warning.
- An independent source review found no blocking defect; its finite-bounds and
  keyboard-pan suggestions were incorporated. The final focused browser check
  also verifies that arrow-key input actually changes the rendered canvas.

The requested Playwright Chromium 156 download repeatedly returned an invalid empty
archive in this workspace. Local browser evidence therefore used available Chrome
for Testing 145.0.7632.6 through an ignored temporary configuration; the committed
Playwright/browser versions and mandatory CI checks are unchanged. Python advisory
lookup was blocked by the execution proxy's HTTP 426 response. Exact-source CI must
still complete its pinned Chromium, PostgreSQL 17, Python advisory and runtime
container checks before source promotion. An initial sandboxed backend run stalled
at local socket use and was terminated; the permitted local-socket rerun passed.

These are local development results, not staging or production acceptance. The
existing hosted release identity is unchanged until the independent release path
qualifies and accepts this source. No hardware, live model service or physical
flight capability was commissioned or claimed.

## Hardware-free readiness audit — 31 October 2026

The audit based on development revision `88b59a4d559ea0491b0b65520c487850405e4394`
corrected two simulation record/display defects:

- A GPS, obstruction or aircraft-fault hold now saves its zero-speed, correctly
  timed telemetry checkpoint in the same transaction as the hold event, subject
  to the same retention bound as ordinary samples. Live state and replay agree;
  recovery continues at the next sequence without losing the held observation.
- Mission history is bound to the selected mission. Switching missions immediately
  stops replay and hides the previous mission's events/samples while the new
  history loads. An obsolete history error also cannot replace the current notice.

The resulting source passed 147 backend cases with SQLite and again with a new
disposable PostgreSQL 16 database, 47 release-unit tests, 24 package/transport tests,
five frontend-unit tests and all 13 Chromium browser cases. The additional browser
case holds the next mission's history response while checking that previous replay
and events cannot appear against that mission. Existing browser journeys exercised
real local delivery, tracking, assistant fallback, six responsive light/dark views,
WebGL, navigation and accessibility. Ruff, TypeScript, production build, diff and
history hygiene checks passed. The locked npm and Python dependency audits reported
no known vulnerabilities. Tests used Python 3.11.17, Node 24.22.1 and the pinned
Chromium 156.0.8078.4. The Three.js chunk-size advisory remains a build warning.

The first PR verification run passed backend, PostgreSQL 17, build and dependency
checks, then exposed a timing-dependent browser fixture defect: the seventh sign-in
to its shared synthetic account hit the real six-attempt/minute limit. A local
browser reproduction returned six HTTP 200 responses followed by HTTP 429 and the
visible retry message. Browser scenarios now use separate seeded accounts; their
helpers assert the login response before waiting for authenticated content. Two
deterministic fixture regressions hold the limiter clock in one minute: the suite's
ten sign-ins succeed, while seven attempts on one account still end in HTTP 429.
Production authentication limits and browser timeouts are unchanged. The complete
13-case Chromium matrix and all 149 SQLite backend/fixture cases passed on the
follow-up source. CI container scanning
and provenance publication were skipped after the original browser failure and
still require a successful follow-up run.

Bounded unauthenticated hosted checks observed HTTP 200 for the production console,
health and readiness; health/readiness identify simulation mode. Session/operations
reads correctly returned 401, including a direct operations request to the API.
Staging redirected to Vercel sign-in. These checks did not sign in, mutate hosted
records, prove live inference or establish source-bound hosted acceptance.

The changes do not add physical interfaces, change the schema or commission an AI
identity. PX4/Gazebo SITL, validated dynamics, live-model acceptance, complete CI,
container scanning and exact-source staging/production promotion remain separate
gates. This audit does not label the new fixes as deployed or qualify physical flight.

## Offline controller-plan inspection

`tests/test_flight_plans.py` exercises the actual QGroundControl parser and authenticated
API: bounded bytes/items, duplicate fields, excessive nesting, strict command order,
coordinate frames, explicit altitude semantics, preserved navigation parameters,
unsupported fence/rally refusal, virtual radius/zone findings and tenant policy
isolation. Record counts and reservations remain unchanged, and imported previews
cannot bypass the existing launch/command schemas or disabled physical adapter.
The synthetic file is `tests/fixtures/controller-preview.plan`.

`frontend/tests/flight-plans.spec.ts` exercises a real API preview, mobile light/dark
accessibility and overflow, unsupported/oversize files, and a delayed response across
sign-out. The existing navigation matrix includes Flight plans. File reads use strict
UTF-8 and preserve source bytes; file/session changes invalidate older results.
These checks do not establish live controller compatibility, validated flight physics,
SITL qualification, hosted acceptance or physical flight.

The resumed local review on 31 October 2026 passed all 144 backend cases on SQLite
and again on a dedicated disposable PostgreSQL 16.15 database, 47 release tests,
24 transport/package tests, five frontend unit tests and all 12 Chromium browser
cases. Ruff, frontend typecheck/build, history hygiene and both locked dependency
audits passed. Application checks used Python 3.11.17 and Node 24.22.1. The unchanged
Python lock was audited with the pinned `pip-audit` 2.10.0 in a separate Python 3.12
tool environment because the local Python 3.11 HTTP client could not traverse its
proxy. Neither audit reported a known vulnerability.

The browser suite used the exact pinned Chromium 156.0.8078.4 build, obtained from
Google's official Chrome for Testing distribution after the Playwright CDN returned
HTML instead of the archive. The first full browser run exposed an incorrect test
helper assumption about navigation after signing back in. The corrected test keeps
the same page, releases the old response and waits for its delivery before checking
session isolation; the full rerun passed. These local results do not replace the
required source-bound PostgreSQL 17 CI, container scans or hosted release gates.

The runtime security gate downloads its digest-pinned scanner with at most three
120-second attempts and two five-second pauses. These retries cover the image
download only. Exhaustion fails CI, and a vulnerability scan failure is never
retried, suppressed or accepted from an older run.

Session response regressions run with `npm --prefix frontend run test:unit` on
Node24. The actual API client rejects both a delayed fetch and delayed JSON body
after a session change, preserves current-session errors and sends no retry.
Browser cases in `session-isolation.spec.ts` use synthetic, loopback-only sessions
to check late advice after an account switch, expiry with an open draft and a
queued expiry from a previous stream. Existing real-API delivery/browser cases
remain required. These fixtures do not establish hosted release acceptance.

## Accepted hosted simulation — 29 October 2026

Application revision `ff493035cbc11a31312f6fae9364825c761b992a` (tree
`8f31f4889678a9868bacfbc2a942f4d04749e704`) completed normal PR #15/#16
promotion. Its first-attempt [Main verification](https://github.com/DruHustle/onesa-drone/actions/runs/40787397135)
and [history hygiene](https://github.com/DruHustle/onesa-drone/actions/runs/40787397304)
passed. The executed scope includes 65 backend cases with SQLite and PostgreSQL,
47 release Python cases, 24 Node cases and seven local Chromium journeys.
The three ARM64 images had zero HIGH/CRITICAL findings without ignored findings.

Separately commissioned, source-bound owner observations qualified both hosted
components and accepted the actual production API and frontend. Staging exercised
a complete simulated delivery, tenant/RBAC denial, wrong-CA rejection, restricted
runtime grants, audit integrity, restart preservation, encrypted isolated restore,
SSE, replay, private tracking and four responsive light/dark WebGL/axe views.
Production verified the actual source/artifacts/configuration, HTTPS and access
boundaries, authenticated UI/SSE/WebGL and preserved independent workloads.
Private signed receipts remain outside Git; a local fixture is never their substitute.

The production console is [drone.onesa.eu](https://drone.onesa.eu); the separate
staging hostname remains protected. Backend acceptance is
`fb9b3877-12e5-4b6e-9852-9a4df0dd43d8`; frontend acceptance is
`0a79ae55-665f-43e0-92bf-55773a009027`. The approved temporary Vercel credential
was revoked, its absence read back, and its rejection verified without changing
deployment protection. Eight encrypted synthetic staging backups were verified
off-host with authenticated decryption in memory and no saved plaintext.

These receipts apply to that exact application source. Later Dev changes,
the independent Portal publication, live AI identity/model quality, physical GPUs,
production backup scheduling/RPO/RTO, real-data privacy approval, commercial hosting
eligibility and physical aircraft remain separate unqualified scopes. The historical
preparation and failed attempts below remain as observed; their pending statuses
describe those earlier sources rather than the accepted revision.

## Local verification and subsequent development

Provider portability regressions live in `tests/test_ai_portability.py` and the
existing `tests/test_ai_contract.py`. They run the same tenant-scoped advisory
against Onesa and compatible HTTP fixtures with identical business inputs, check
credential/context separation and model provenance, reject partial/failed/cancelled
legacy streams and keep local summaries explicit. They do not activate an external
identity/provider, change a mission or prove hosted model quality. The locally
vendored transport's current provenance/hash is recorded in the integration README.

Release-unit fixtures use a disposable commissioning registry with temporary keys,
policy and database. When run as root, they use a private home-directory parent
and never read the host's production trust registry. These synthetic records confer
no hosted or production authority; the actual verifier's trust checks are unchanged.

Run from the root:

```sh
.venv311/bin/python -m ruff check backend autonomy simulation integrations scripts tests
.venv311/bin/python -m pytest -q
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run test:e2e
npm --prefix frontend audit --audit-level=high
.venv311/bin/python -m pip_audit -r backend/requirements.lock --no-deps --disable-pip
.venv311/bin/python scripts/repository_hygiene.py --history
```

PostgreSQL repeats the backend suite against an explicitly disposable `drone_test`
database using `DRONE_TEST_DATABASE_URL`. Fixtures use unique tenants and never
truncate another database. Browser tests launch their own temporary SQLite backend,
individual synthetic account and loopback Vite server. They refuse an already running
server. Browser artifacts are ignored and must not be uploaded with live records.

The suite covers complete delivery, duplicate commands, idempotency conflict,
reservation contention, invalid transitions, expired session/authorization, CSRF,
roles, tenant object denial, audit integrity, tracking expiry, database failure,
rollback of a partial command, restart checkpoints, bounded telemetry, SSE expiry
and disconnect, deterministic detours and physical-adapter denial. A mock validates
the inspected Onesa AI session/Origin/CSRF and completion contract without inference.

Browser evidence covers Chromium real API journeys, 390/768/1440 CSS pixels, light
and dark system appearance, reduced motion, all navigation, replay, private tracking,
WebGL rendering, horizontal overflow and axe WCAG checks. It does not prove physical
handset GPU performance, full screen-reader usability or validated flight physics.

Before release, bind results to the exact source SHA. Required external gates:
private hosted staging, authenticated acceptance on the approved origin, DB/runtime
least privilege and backup restore, current dependency/container scans, owner/editorial
and privacy approval, rollback receipt, and a qualified production promotion path.
No merge, local PASS or screenshot substitutes for these hosted gates.

## Local review — 31 October 2026

The clean development checkout was fast-forwarded from `5d2c31d` to fetched
`5951704` before final qualification. With the local advisory decoder correction,
92 backend tests, 47 release tests (38 additional subtests), five frontend unit
tests and 24 transport/package tests pass. Ruff, the TypeScript/production build,
history hygiene and both locked dependency advisory scans pass; no known dependency
vulnerability was reported. Node 24.22.1 and Python 3.11 were used for final checks.

All ten Chromium acceptance cases pass: a complete simulation delivery, telemetry,
replay, private tracking, advisory, six light/dark mobile/tablet/desktop navigation,
accessibility and WebGL checks, and three account/session-race cases. The old-source
browser run was deliberately interrupted to test the updated source; it is not
counted as a pass. Three new provider-nesting regressions failed before the fix and
pass afterward, including the legacy stream path. Temporary browser artifacts and
fixture services are removed after review at the owner's request.

The same 92 backend cases also pass against an isolated local PostgreSQL database.
An in-memory `pg_dump`/`pg_restore` round trip validates the schema, six table counts
and all 88 synthetic tenant audit chains. The source and restored test databases,
temporary restore script and fixture files are removed after validation.

This is local SQLite/PostgreSQL and synthetic-provider evidence. It does not
requalify hosted production, live model identity, hosted backup recovery, physical
hardware, flight physics or jurisdiction-specific operating permission. Physical
transports remain disabled. Existing accepted production and its source-bound
receipts are unchanged.

Logout regression coverage also removes the authenticated fixture's session between
authorization and its deletion transaction, as a simultaneous logout or administrator
revocation can do. Logout must still acknowledge success, expire the browser cookie
and deny subsequent protected reads. Other session, Origin and CSRF checks remain
required; this does not authorize an already revoked request.

## Executed evidence — 28 October 2026

- Backend source `68fc93a`: 54 tests pass natively on Python 3.11.14. The same
  54 cases pass with SQLite and real disposable PostgreSQL inside the final
  Linux/musl container, read-only, UID 10001, 256 MiB, 1 CPU and 64 PIDs.
- PostgreSQL `pg_dump`/`pg_restore` into a new isolated database verifies schema,
  six operational table counts and every tenant audit chain. No production data.
- Node 24.22.1 typecheck/build pass. Seven Chromium cases pass in 84 seconds,
  including an actual end-to-end virtual delivery, WebGL assertions, replay,
  private tracking, assistant and all navigation at three widths in both appearances.
- Axe finds no WCAG A/AA violations in those tested console views. Portal's eight
  EN/DE views, 23 domain/identity tests, homepage regressions, build, lint,
  appearance checks and repository hygiene pass. Portal PR #245 also passes all
  hosted checks and is merged into staging at `3a3e021d517f8668d1f3425b81db383b38bca635`.
  This is source integration, not a receipt for production publication.
- npm and Python advisory scans find no known dependency vulnerabilities. The
  final Alpine runtime scan finds zero HIGH/CRITICAL vulnerabilities without
  ignores. This is not proof that no vulnerability exists.
- Final scene instrumentation: 31–37 ms initialization after module load,
  33.5–45.2 MiB reported JS heap. One active headless flight sample measured
  14 FPS; idle/reduced-motion scenes render on demand. This does not establish
  a physical-device frame-rate target or total GPU/process memory.
- Production chunks: about 81 kB gzip for the application, 5.2 kB CSS and
  143 kB lazy 3D code. No external model, terrain or texture downloads.
- 100 deterministic planner runs: local median 0.050 ms, p95 0.056 ms. These
  timings establish neither flight dynamics fidelity nor hosted performance.

The initial Debian image failed its vulnerability gate and was replaced. Earlier
browser runs included timeouts; the tablet accessibility case repeatedly stalled
while the idle renderer drew continuously. On-demand idle/reduced-motion rendering
was implemented, followed by a passing full seven-case run. The failed and passing
local JSON reports remain ignored artifacts; they are not silently relabelled.

A nonblocking Starlette/httpx test-transport deprecation remains. Vite reports the
large uncompressed Three.js chunk; it is lazy and approximately 139 kB gzip.
Hardware GPU benchmarking, cross-browser/device qualification, maximum-capacity
load tests, delta telemetry, full localisation and advanced multi-stop dispatch
remain further qualification/development work.

The planning extension passes 64 backend cases natively and in the read-only Linux
container with both SQLite and disposable PostgreSQL. The added cases cover route
alternatives, reserve exhaustion, stable parallel sequencing, scheduled starts,
depot boundaries, tenant-scoped read-only previews, stale assignment conflicts,
bounded recomputation and the published OpenAPI contract. A new fixture initially
omitted a required package category; it was corrected. The PostgreSQL run exposed
a rate-limit test crossing a minute boundary; that test now freezes its clock, and
the full 64-case PostgreSQL rerun passes. These failures were not release passes.

The seven Chromium cases pass with a real alternative-route delivery and populated
dispatch preview. A focused follow-up also passes mobile preview overflow/axe checks
and the full delivery. The rebuilt runtime image
`sha256:174e30a386780e210f7dfe3dfcea07eb7fd8f11d872568701a110c26319e6796`
has zero HIGH/CRITICAL findings without exclusions. Latest local route benchmark:
median 0.171 ms, p95 0.183 ms; five full 25-request/50-aircraft dispatch previews:
median 100.787 ms, maximum 109.509 ms. Run `.venv311/bin/python -m scripts.benchmark`.
These are local observations, not hosted capacity guarantees.

Drone hosted CI was initially skipped pending verified included allowance/spend
controls. On 28 October the owner explicitly confirmed included-only CI and blocked
paid overages; `ONESA_PRIVATE_HOSTED_VALIDATION_ENABLED=true` was set and read back.
Both exact-source hosted workflows pass for `530ef50c0b7bba935f6ed05b70a413eea0d1f3e8`:
[push verification](https://github.com/DruHustle/onesa-drone/actions/runs/40727633449)
and [PR verification](https://github.com/DruHustle/onesa-drone/actions/runs/40727622187).
These include SQLite/PostgreSQL tests, browser acceptance, dependency/history checks
and the runtime image gate. The earlier skipped runs remain skipped.

The owner-selected `local-tools/onesa-drone` contains a running loopback-only stage
at `http://127.0.0.1:3470`, bound to that source and the recorded frontend/image
hashes. Actual acceptance passes authentication, a complete alternative-route
delivery, live SSE, persistent telemetry/replay, private tracking, deterministic
assistance and private monitoring. Four staged Chromium views (390/1440 pixels,
light/dark) pass WebGL, overflow and axe checks. Runtime permission readback denies
schema creation, audit update/delete and event deletion. A real in-memory dump is
restored into a new isolated database: six operational counts and all tenant audit
chains match, including two complete deliveries after a service restart.

Initial local bundle startup exposed Compose temporary-filesystem quoting, Python
module-path and proxy temporary-directory/network settings. Those were corrected
before acceptance. Scanning cached infrastructure images then found eight proxy
package and 26 database helper findings. The proxy packages were upgraded; PostgreSQL
now starts as UID 70 without the unnecessary vulnerable gosu helper. All three final
local runtime images have zero HIGH/CRITICAL findings without exclusions; original
failed reports and the preceding manifest remain in private local evidence.

The local API (UID 10001), database (UID 70) and proxy (UID 101) run read-only with
dropped capabilities and memory caps of 256/256/64 MiB. Only the proxy publishes a
loopback port. The database volume survives stop/start. Bundle credentials, SQL,
source archive and acceptance receipts remain outside Git in the owner-selected
private directory; no credential values or live records were uploaded to CI.

Portal canonical naming/legacy redirects are also merged into staging in
[#247](https://github.com/DruHustle/onesa-company-portal/pull/247) at
`d2acbd1fa9e281cfbe73f4dfc872a673c97ea330` after exact-source hosted checks passed.
Production publication is not claimed.

Private-plan native branch protection remains unavailable. Local HTTP staging does
not qualify public HTTPS, remote database TLS, a live Onesa AI identity, a production
release verifier, hosted backups/rollback or partial-provider-failure acceptance.
These remain open release gates. No physical flight or certification is claimed.

## Oracle/Vercel release preparation — 28 October 2026

The hosting change reran all 64 backend tests, seven browser acceptance cases and
the production frontend build successfully. The owner bridge has 29 passing custody
tests; the Drone runner adds ten refusal/privacy tests. All 17 transport guard and
four prebuilt packager tests pass. The first transport test attempt was blocked by
the local sandbox's socket restriction; the authorized rerun executed all cases.

A disposable local instance of the Oracle Compose configuration executed real
PostgreSQL TLS migration, wrong-CA rejection, restricted runtime grants, schema
verification and an isolated restore. The dump remained in memory until CMS
encryption. This proves the local configuration, not hosted acceptance. The initial
browser-probe scan failed on the unused npm runtime; removing it produced zero
HIGH/CRITICAL findings without ignored vulnerabilities. The initial Linux probe
also exposed missing SwiftShader support; Mesa EGL is the selected software backend.
The corrected Linux image then completed a real virtual delivery, live SSE, replay,
private tracking and four 390/1440-pixel light/dark axe checks with WebGL and zero
violations. The smaller probe budget crashed a browser target during axe; the passing
run used a bounded 1 GiB, 0.5 CPU, 256 processes and two Mesa threads. An earlier
combined local forwarding harness stalled and was replaced by a separate disposable
forwarder; this was not hosted qualification. Private failed reports are retained.
The final runner also reads back the custom-domain alias and rejects a stale deployment,
foreign project or crossed environment; the release Python suite now has 40 passing tests.

Vercel project and domain registration are preparation only. Public HTTPS, hosted
workflow/restore checks, source-pinned commissioning, provider deployment receipts
and production acceptance must be observed separately before a release is claimed.

Oracle-side unauthenticated ingress preflight found Cloudflare returning 403 for
Python's default user-agent and the expected inactive-origin 502 for the explicit
`OnesaDroneOwnerQualification/1` identity. The client now identifies itself, with a
request-header regression; all 41 release Python tests pass. No hosted qualification
context was issued or consumed during this diagnosis. This transport correction
requires fresh normal source promotion and main checks before installation.

Inactive Oracle import then exposed a Docker store difference: configuration digest
`f14f27a...` was scanned, while the imported runtime uses OCI index `4e72f707...`.
All three archives loaded; inspection refused the wrong identifier before plan
creation, commissioning, qualification or service activation. The corrected native
mapping accepts classic/configuration and containerd/index identities and rejects
foreign references; all 42 release Python tests pass. Off-host and Oracle index IDs
were read back and match. Original failed installation diagnostics remain private.

Main `f3e01c1` passed native CI and was independently commissioned. Backend hosted
qualification `943e6765-8d03-4b91-875e-e103e9c699ea` passed actual delivery, tenant/RBAC,
restart persistence, TLS/grants/audit and isolated restore checks. Frontend staging
deployment `dpl_G9oBphM8uG2uH3V4sCSzKNQ64PrA` was created and aliased once; its
qualification stopped at Chromium launch (`crashpad --database is required`) before
browser interaction. That reserved context is retained and revoked, not retried.

A network-disabled, fixture-free Oracle browser test confirmed that writable XDG
configuration/cache directories under the bounded tmpfs fix launch and WebGL.
The runner now supplies those directories. A source-bound initialization policy
distinguishes fresh provisioning from preservation updates; existing roles/accounts
are never reset or reseeded, and record counts/audit chains must survive replacement.
The existing viewer must retain its original authority. All 45 release Python tests
pass, including these preservation and browser-launch configuration regressions.
Fresh promotion and hosted qualification are still required for this correction.

Main `e2b357f7` passed its native checks and a separately commissioned backend
qualification: delivery, RBAC/tenant isolation, TLS/grants, audit chains, preserved
records, restart and isolated restore. The frontend preview was created and aliased
once, but its browser qualification reached Vercel sign-in instead of the Drone
application. No application fixture credentials were entered there. Both superseded
contexts were explicitly revoked; the failed attempt is retained without retry.

The owner approved a temporary project automation credential for testing, followed
by revocation. A read-only provider preflight confirmed a same-origin 307 and the
provider's `_vercel_jwt` cookie. The corrected probe requests that cookie without
following redirects, then narrows it to the exact Drone host. A real localhost
redirect regression proves that the credential-bearing request does not reach a
foreign origin. Global browser headers are deliberately absent because Playwright
carries those across redirect hops. This correction requires new checked source,
commissioning and hosted qualification; it does not confer release authority.

The correction passed 65 backend tests, 46 release Python tests, 24 Node tests
(including three automation policy regressions), the frontend build, all seven
local Chromium journeys and history hygiene with zero findings. A fixture-free
Oracle browser diagnostic observed HTTP 200 and the actual Drone sign-in page
using the exact-host cookie; no application credentials were entered. Production
acceptance remains pending until the corrected source follows the release gates.

A subsequent actual provider readback found that Vercel had classified the first
`f3e01c1` staging deployment as production and auto-assigned the production custom
domain. This was unqualified publication of a simulation frontend connected to the
staging API, not an accepted release. Its exact production alias was withdrawn;
the deployment, project, DNS, protected staging and all data were preserved. The
runner now specifies preview explicitly, creates production with automatic domain
assignment disabled, and rejects crossed targets, non-READY state or foreign
operation metadata before assigning an alias. The new refusal regression joins the
release suite. No production backend had been activated at this observation.

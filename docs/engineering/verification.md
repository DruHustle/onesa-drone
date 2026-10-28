# Verification scope and release gates

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

# Verification scope and release gates

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

Drone hosted CI remains gated off pending verified included allowance/spend controls:
the GitHub billing API lacks its required user scope and no accessible browser
session is available. Private-plan native branch protection is unavailable. No
passing hosted Drone CI, commissioned staging origin, live AI identity, production
release, hosted backup/rollback or partial-provider-failure test is claimed.

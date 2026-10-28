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

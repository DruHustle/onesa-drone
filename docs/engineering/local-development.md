# Local development and demo

Use Python 3.11 and Node 24.22.1. No production credentials are required.
Commands are run from the standalone `DruHustle/onesa-drone` repository root. The product
retains independent frontend/backend builds and does not import sibling products.

```sh
python3.11 -m venv .venv311
.venv311/bin/python -m pip install -r backend/requirements.lock
npm --prefix frontend ci --ignore-scripts
.venv311/bin/python -m backend.app.cli bootstrap --email operator@example.test
.venv311/bin/python -m backend.app.cli seed --email operator@example.test
.venv311/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8400 --workers 1 --no-access-log
```

In another terminal run `npm --prefix frontend run dev` and open
`http://127.0.0.1:3400`. Bootstrap prompts for a new password; no default account
exists. Seed explicitly creates illustrative aircraft only when the fleet is empty.
SQLite is an offline development adapter, not the hosted deployment database.

To use a separately provisioned PostgreSQL development database, privately supply
`DATABASE_URL=postgresql+psycopg://...` with verified TLS for remote connections.
Run `.venv311/bin/python -m scripts.migrate` with the migrator identity, then start
with the restricted runtime identity. Never point tests or seeds at company data.

## Demonstration

1. Sign in. Inspect the simulation-only notice and register an aircraft if needed.
2. Create a delivery using the illustrative coordinates or an arbitrary local campus.
3. Preserve the expiring private tracking link, then open Mission control.
4. Open Route planning and build a dispatch preview. Inspect suggested aircraft,
   start/return times, reserve and any unassigned requests. Choose the shortest route
   or an alternative, then plan & assign, validate preflight, authorize simulation
   and launch simulation. Unavailable alternatives are rejected without reservation.
5. Inspect the 3D route, telemetry and event history as the parcel is delivered and
   the aircraft returns. One real second advances five simulated seconds.
6. Replay recorded telemetry. Replay never dispatches a command.
7. Create a GPS degradation scenario. Observe the hold; request operator recovery.
8. Review the incident and audit journal, export an operational report, and ask
   the assistant for a summary. The unconfigured provider is labelled explicitly.

Use only synthetic data. Package categories do not establish medical-chain,
temperature-control, dangerous-goods or commercial transport suitability.

## Local Portal and Drone acceptance

Use the paired Portal and Drone revisions under review, Python 3.11, Node 24,
and a local PostgreSQL installation with SSL support. Run as a regular
user. The harness creates a new, password-protected PostgreSQL cluster with
two disposable databases, generates its own TLS certificate, creates two
approved synthetic Portal identities and seeds two Drone organizations. The
Portal app, its account component and the production Next API proxy run from
the specified checkout. The test mounts the account component in a minimal
browser shell. The Drone web build and the two independent APIs are real.
Email delivery and native OS handling of custom-scheme links are separate checks.

After cloning both repositories next to each other, run the following in Drone.
Use `PG_BIN` to point to the directory containing both `initdb` and `postgres`
when `pg_config` is unavailable.

```sh
python3.11 -m venv .venv311
.venv311/bin/python -m pip install -r backend/requirements.lock
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run build
npm --prefix ../onesa-company-portal/onesa-company-portal-backend ci --ignore-scripts
npm --prefix ../onesa-company-portal/onesa-company-portal-backend run build
npm --prefix ../onesa-company-portal/onesa-company-portal-frontend ci --ignore-scripts
(cd frontend && npx playwright install chromium)
.venv311/bin/python scripts/acceptance/run_local.py \
  --portal ../onesa-company-portal --pg-bin "${PG_BIN:-$(pg_config --bindir)}"
```

The loopback ports are 54843 (Portal HTTPS), 54844 (Drone HTTPS), 58300
(Portal API), 58400 (Drone API) and 56882 (PostgreSQL). Test output records
the result of each check. `--protocol-only` repeats real issuer, callback,
role, tenant and sign-out checks without running a browser. `--chromium`
accepts a local Chromium executable for constrained headless environments.

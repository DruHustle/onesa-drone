# Local development and demo

Use Python 3.11 and Node 24.22.1. No production credentials are required.
Commands are run from the independent repository root.

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
4. Plan & assign, validate preflight, authorize simulation, launch simulation.
5. Inspect the 3D route, telemetry and event history as the parcel is delivered and
   the aircraft returns. One real second advances five simulated seconds.
6. Replay recorded telemetry. Replay never dispatches a command.
7. Create a GPS degradation scenario. Observe the hold; request operator recovery.
8. Review the incident and audit journal, export an operational report, and ask
   the assistant for a summary. The unconfigured provider is labelled explicitly.

Use only synthetic data. Package categories do not establish medical-chain,
temperature-control, dangerous-goods or commercial transport suitability.

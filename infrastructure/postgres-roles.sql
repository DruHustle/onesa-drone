-- Apply only to a new, explicitly selected Drone database as the owner.
-- Provision LOGIN credentials separately in the secret manager.
CREATE ROLE drone_runtime NOLOGIN;
GRANT USAGE ON SCHEMA public TO drone_runtime;
GRANT SELECT ON tenants, users, sessions, aircraft, missions, mission_events,
  audits, receipts, telemetry, incidents, schema_revision TO drone_runtime;
GRANT INSERT, UPDATE ON tenants, users, aircraft, missions, incidents TO drone_runtime;
GRANT INSERT ON mission_events, audits, receipts TO drone_runtime;
GRANT INSERT, UPDATE, DELETE ON sessions, telemetry TO drone_runtime;
-- No runtime schema ownership, DDL, audit rewrite or audit deletion privileges.

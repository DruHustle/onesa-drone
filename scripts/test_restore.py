"""Actual pg_dump/pg_restore round trip, restricted to the owned local test container."""

import subprocess
import secrets
import json
from backend.app.db import Store
from sqlalchemy import text
from backend.app.models import Tenant, Audit
from backend.app.service import j
from backend.app.security import digest

container = "onesa-drone-postgres-test"
info = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
assert info["Config"]["Env"] and "POSTGRES_DB=drone_test" in info["Config"]["Env"]
name = "drone_restore_test_" + secrets.token_hex(4)
backup = subprocess.check_output(
    ["docker", "exec", container, "pg_dump", "-U", "drone_test", "-d", "drone_test", "-Fc", "--no-owner"]
)
subprocess.run(["docker", "exec", container, "createdb", "-U", "drone_test", name], check=True)
subprocess.run(
    [
        "docker",
        "exec",
        "-i",
        container,
        "pg_restore",
        "-U",
        "drone_test",
        "-d",
        name,
        "--no-owner",
        "--exit-on-error",
    ],
    input=backup,
    check=True,
)
source = Store("postgresql+psycopg://drone_test:synthetic-drone-test-only@127.0.0.1:55438/drone_test")
restored = Store("postgresql+psycopg://drone_test:synthetic-drone-test-only@127.0.0.1:55438/" + name)
source.verify()
restored.verify()
with source.session() as a, restored.session() as b:
    for table in ["tenants", "users", "missions", "mission_events", "audits", "telemetry"]:
        assert a.scalar(text("SELECT count(*) FROM " + table)) == b.scalar(
            text("SELECT count(*) FROM " + table)
        )
    for tenant in b.query(Tenant):
        previous = ""
        for row in b.query(Audit).filter(Audit.tenant_id == tenant.id).order_by(Audit.at):
            assert row.previous == previous
            assert (
                digest(
                    j(
                        [
                            row.id,
                            row.tenant_id,
                            row.at,
                            row.actor,
                            row.action,
                            row.detail,
                            row.correlation_id,
                            row.previous,
                        ]
                    )
                )
                == row.digest
            )
            previous = row.digest
        assert previous == tenant.audit_head
source.engine.dispose()
restored.engine.dispose()
print(
    json.dumps(
        {
            "scope": "LOCAL_SYNTHETIC_NOT_HOSTED",
            "backup_bytes": len(backup),
            "restored_tables": 6,
            "schema_and_audit_chain": "verified",
            "production_data_accessed": False,
        }
    )
)

import re
from pathlib import Path


def test_runtime_can_read_but_cannot_mutate_managed_memberships():
    sql = Path("infrastructure/postgres-roles.sql").read_text(encoding="utf-8")
    sql = re.sub(r"(?m)--.*$", "", sql)
    statements = re.sub(r"\s+", " ", sql).upper()
    assert "GRANT SELECT ON MANAGED_IDENTITY_MEMBERSHIPS TO DRONE_RUNTIME;" in statements
    assert not re.search(
        r"GRANT (?:INSERT|UPDATE|DELETE|ALL|SELECT\s*,)[^;]* ON MANAGED_IDENTITY_MEMBERSHIPS ",
        statements,
    )

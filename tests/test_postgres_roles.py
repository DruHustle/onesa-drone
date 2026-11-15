import re
from pathlib import Path


def test_optional_runtime_membership_grant_is_read_only_and_explicit():
    sql = Path("infrastructure/postgres-roles.sql").read_text(encoding="utf-8")
    assert "-- GRANT SELECT ON managed_identity_memberships TO drone_runtime;" in sql
    active = re.sub(r"(?m)--.*$", "", sql)
    assert not re.search(r"GRANT .* ON managed_identity_memberships TO drone_runtime", active, re.I)

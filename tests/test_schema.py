import pytest
from backend.app.models import SchemaRevision


def test_migration_fingerprint_is_checked_on_restart(stack):
    stack["store"].verify()
    with stack["store"].transaction() as db:
        db.get(SchemaRevision, "0001").checksum = "invalid-test-checksum"
    try:
        with pytest.raises(RuntimeError):
            stack["store"].verify()
    finally:
        with stack["store"].transaction() as db:
            db.get(SchemaRevision, "0001").checksum = stack["store"].checksum()

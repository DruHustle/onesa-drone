import pytest
import json
from pathlib import Path
from backend.app.models import SchemaRevision


def test_published_api_contract_matches_application(stack):
    assert json.loads(Path("docs/api.openapi.json").read_text()) == stack["app"].openapi()


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


def test_identity_migration_fingerprint_includes_managed_memberships():
    import hashlib
    from sqlalchemy.schema import CreateTable
    from backend.app.db import Store
    from backend.app.identity import IdentityBase, ManagedMembershipBase

    store = Store("sqlite://", identity_enabled=True)
    try:
        store.initialize()
        tables = [
            *IdentityBase.metadata.tables.values(),
            *ManagedMembershipBase.metadata.tables.values(),
        ]
        ddl = "\n".join(
            str(CreateTable(table).compile(dialect=store.engine.dialect))
            for table in sorted(tables, key=lambda item: item.name)
        )
        assert store.identity_checksum() == hashlib.sha256(ddl.encode()).hexdigest()
        store.verify()
    finally:
        store.engine.dispose()

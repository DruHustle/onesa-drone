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

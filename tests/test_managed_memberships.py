import hashlib
import json
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.app.db import Store
from backend.app.identity import IdentityService, ManagedMembership
from backend.app import managed_memberships as importer
from backend.app.managed_memberships import (
    MAX_SNAPSHOT_BYTES,
    import_memberships,
    load_authoritative_snapshot,
    reconcile_memberships,
)
from backend.app.models import Tenant


@pytest.fixture
def database(tmp_path):
    store = Store(f"sqlite:///{tmp_path}/managed-memberships.db", identity_enabled=True)
    store.initialize()
    with store.transaction() as db:
        first = Tenant(name="First synthetic workspace")
        second = Tenant(name="Second synthetic workspace")
        db.add_all([first, second])
        db.flush()
        ids = first.id, second.id
    yield store, ids
    store.engine.dispose()


def record(user_id, tenant_id, role):
    return {"user_id": user_id, "tenant_id": tenant_id, "role": role}


def saved(store):
    with store.session() as db:
        return {
            (row.subject, row.tenant_id): row.role
            for row in db.scalars(select(ManagedMembership))
        }


def test_additive_import_is_idempotent_and_never_changes_or_revokes(database):
    store, (first, _) = database
    subject = str(uuid4())
    rows = [record(subject, first, "operator")]

    assert import_memberships(store, rows) == 1
    assert import_memberships(store, rows) == 0
    assert saved(store) == {(subject, first): "operator"}

    with pytest.raises(ValueError, match="permission changed"):
        import_memberships(store, [record(subject, first, "viewer")])
    assert saved(store) == {(subject, first): "operator"}


def test_complete_reconciliation_applies_grants_role_changes_and_revocations(database):
    store, (first, second) = database
    retained, revoked, added = (str(uuid4()) for _ in range(3))
    import_memberships(
        store,
        [
            record(retained, first, "admin"),
            record(retained, second, "operator"),
            record(revoked, first, "viewer"),
        ],
    )

    result = reconcile_memberships(
        store,
        [record(retained, first, "viewer"), record(added, second, "operator")],
        complete_snapshot=True,
    )

    assert result == {
        "inserted": 1,
        "updated": 1,
        "deleted": 2,
        "unchanged": 0,
        "dry_run": False,
    }
    assert saved(store) == {
        (retained, first): "viewer",
        (added, second): "operator",
    }

    service = object.__new__(IdentityService)
    service.config = SimpleNamespace(audience="drone")
    service.store = store
    identity = SimpleNamespace(
        subject=retained, product_roles={"drone": "admin"}, memberships=()
    )
    assert service.membership_roles(identity) == {first: "viewer"}
    revoked_identity = SimpleNamespace(
        subject=revoked, product_roles={"drone": "admin"}, memberships=()
    )
    assert service.membership_roles(revoked_identity) == {}


def test_reconciliation_rejects_incomplete_or_invalid_snapshot_without_mutation(database):
    store, (first, second) = database
    subject = str(uuid4())
    initial = [record(subject, first, "operator")]
    import_memberships(store, initial)
    before = saved(store)

    with pytest.raises(ValueError, match="complete authoritative"):
        reconcile_memberships(store, [], complete_snapshot=False)
    with pytest.raises(ValueError, match="duplicate"):
        reconcile_memberships(
            store,
            [record(subject, first, "viewer"), record(subject, first, "viewer")],
            complete_snapshot=True,
        )
    with pytest.raises(ValueError, match="unrecognized local tenant"):
        reconcile_memberships(
            store,
            [record(str(uuid4()), str(uuid4()), "admin")],
            complete_snapshot=True,
        )
    assert saved(store) == before


def test_empty_snapshot_requires_explicit_confirmation(database):
    store, (first, _) = database
    import_memberships(store, [record(str(uuid4()), first, "viewer")])

    with pytest.raises(ValueError, match="empty snapshot requires explicit confirmation"):
        reconcile_memberships(store, [], complete_snapshot=True)
    result = reconcile_memberships(
        store, [], complete_snapshot=True, allow_empty=True
    )
    assert result["deleted"] == 1
    assert saved(store) == {}


def test_dry_run_reports_reconciliation_without_mutating(database):
    store, (first, second) = database
    subject = str(uuid4())
    import_memberships(store, [record(subject, first, "admin")])
    before = saved(store)

    result = reconcile_memberships(
        store,
        [record(subject, second, "viewer")],
        complete_snapshot=True,
        dry_run=True,
    )

    assert result == {
        "inserted": 1,
        "updated": 0,
        "deleted": 1,
        "unchanged": 0,
        "dry_run": True,
    }
    assert saved(store) == before


def snapshot_payload(issuer, records, **changes):
    payload = {
        "schema_version": 1,
        "product": "drone",
        "mapping_issuer": issuer,
        "snapshot_id": str(uuid4()),
        "complete": True,
        "issued_at": 900,
        "expires_at": 1800,
        "drone_memberships": records,
    }
    payload.update(changes)
    return payload


def test_authoritative_snapshot_requires_matching_digest_issuer_and_fresh_complete_envelope():
    issuer = "https://portal.onesa.eu/api/v1/identity"
    rows = [record(str(uuid4()), str(uuid4()), "viewer")]
    raw = json.dumps(snapshot_payload(issuer, rows), sort_keys=True).encode()
    snapshot_id, records = load_authoritative_snapshot(
        raw, hashlib.sha256(raw).hexdigest(), issuer, now=1000
    )
    assert snapshot_id
    assert records == rows

    with pytest.raises(ValueError, match="SHA-256"):
        load_authoritative_snapshot(raw, "0" * 64, issuer, now=1000)
    with pytest.raises(ValueError, match="identity or completeness"):
        load_authoritative_snapshot(
            raw, hashlib.sha256(raw).hexdigest(), "https://other.example", now=1000
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"complete": False},
        {"schema_version": True},
        {"issued_at": -3000},
        {"issued_at": 1031},
        {"expires_at": 1000},
        {"expires_at": 5000},
        {"snapshot_id": ""},
    ],
)
def test_authoritative_snapshot_rejects_incomplete_stale_or_ambiguous_envelopes(changes):
    issuer = "https://portal.onesa.eu/api/v1/identity"
    raw = json.dumps(snapshot_payload(issuer, [], **changes), sort_keys=True).encode()
    with pytest.raises(ValueError):
        load_authoritative_snapshot(
            raw, hashlib.sha256(raw).hexdigest(), issuer, now=1000
        )



def test_cli_additive_import_requires_out_of_band_digest_before_database(monkeypatch, tmp_path):
    issuer = "https://portal.onesa.eu/api/v1/identity"
    path = tmp_path / "snapshot.json"
    raw = json.dumps(snapshot_payload(issuer, []), sort_keys=True).encode()
    path.write_bytes(raw)
    monkeypatch.setenv("ONESA_IDENTITY_MAPPING_ISSUER", issuer)

    def database_must_not_open(*_args, **_kwargs):
        pytest.fail("Unverified membership input must be rejected before opening the database")

    monkeypatch.setattr(importer, "Store", database_must_not_open)
    monkeypatch.setattr(sys, "argv", ["managed_memberships", str(path)])
    with pytest.raises(SystemExit) as missing:
        importer.main()
    assert missing.value.code == 2

    monkeypatch.setattr(
        sys, "argv",
        ["managed_memberships", str(path), "--expected-sha256", "0" * 64],
    )
    with pytest.raises(SystemExit) as mismatched:
        importer.main()
    assert mismatched.value.code == 2


def test_cli_additive_import_accepts_only_hash_verified_complete_snapshot(database, monkeypatch, tmp_path):
    store, (first, _) = database
    issuer = "https://portal.onesa.eu/api/v1/identity"
    subject = str(uuid4())
    issued_at = int(time.time())
    raw = json.dumps(
        snapshot_payload(
            issuer, [record(subject, first, "operator")],
            issued_at=issued_at, expires_at=issued_at + 1800,
        ),
        sort_keys=True,
    ).encode()
    path = tmp_path / "snapshot.json"
    path.write_bytes(raw)

    monkeypatch.setenv("ONESA_IDENTITY_MAPPING_ISSUER", issuer)
    monkeypatch.setenv("DATABASE_URL", str(store.engine.url))
    monkeypatch.setattr(
        sys, "argv",
        [
            "managed_memberships", str(path), "--expected-sha256",
            hashlib.sha256(raw).hexdigest(),
        ],
    )
    importer.main()
    assert saved(store) == {(subject, first): "operator"}


def test_authoritative_snapshot_is_size_bounded_before_json_parsing():
    with pytest.raises(ValueError, match="16 MiB"):
        load_authoritative_snapshot(
            b"x" * (MAX_SNAPSHOT_BYTES + 1), "0" * 64,
            "https://portal.onesa.eu/api/v1/identity", now=1000
        )

"""Import or atomically reconcile a verified identity-migration membership snapshot."""

import argparse
import hashlib
import hmac
import json
import os
import re
import time
from uuid import UUID

from sqlalchemy import select, text

from .db import Store
from .identity import ManagedMembership
from .models import Tenant

MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024


def _records(records):
    if not isinstance(records, list):
        raise ValueError("Membership snapshot must contain a list")
    expected = {}
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("Invalid membership record")
        user_id, tenant_id, role = row.get("user_id"), row.get("tenant_id"), row.get("role")
        if not isinstance(user_id, str) or not isinstance(tenant_id, str):
            raise ValueError("Invalid membership identity")
        try:
            subject, tenant = str(UUID(user_id)), str(UUID(tenant_id))
        except (ValueError, AttributeError, TypeError):
            raise ValueError("Invalid membership identity") from None
        if not isinstance(role, str) or role not in {"viewer", "operator", "admin"} or (subject, tenant) in expected:
            raise ValueError("Invalid or duplicate membership")
        expected[subject, tenant] = role
    return expected


def load_authoritative_snapshot(raw, expected_sha256, mapping_issuer, *, now=None):
    """Validate a complete, fresh snapshot before any destructive reconciliation."""
    if not isinstance(raw, bytes):
        raise ValueError("Authoritative snapshot bytes are required")
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Authoritative snapshot exceeds the 16 MiB limit")
    if (
        not isinstance(expected_sha256, str)
        or not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256)
        or not isinstance(mapping_issuer, str)
        or not mapping_issuer
    ):
        raise ValueError("Authoritative snapshot verification inputs are required")
    actual = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual, expected_sha256.lower()):
        raise ValueError("Authoritative snapshot SHA-256 does not match")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise ValueError("Authoritative snapshot is not valid JSON") from None
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema_version")) is not int
        or payload["schema_version"] != 1
        or payload.get("product") != "drone"
        or payload.get("mapping_issuer") != mapping_issuer
        or payload.get("complete") is not True
        or not isinstance(payload.get("snapshot_id"), str)
        or not payload["snapshot_id"].strip()
        or len(payload["snapshot_id"]) > 128
    ):
        raise ValueError("Authoritative snapshot identity or completeness is invalid")
    issued_at, expires_at = payload.get("issued_at"), payload.get("expires_at")
    now = int(time.time()) if now is None else now
    if (
        type(issued_at) is not int
        or type(expires_at) is not int
        or type(now) is not int
        or issued_at > now + 30
        or now - issued_at > 3600
        or expires_at <= now
        or expires_at <= issued_at
        or expires_at - issued_at > 3600
    ):
        raise ValueError("Authoritative snapshot is expired, stale or outside its time envelope")
    records = payload.get("drone_memberships")
    _records(records)
    return payload["snapshot_id"], records


def import_memberships(store, records):
    """Add missing memberships only; never silently change or revoke a grant."""
    expected = _records(records)
    with store.transaction() as db:
        tenants = set(db.scalars(select(Tenant.id)))
        if any(tenant not in tenants for _, tenant in expected):
            raise ValueError("Resolve unrecognized local tenant before importing")
        inserted = 0
        for key, role in expected.items():
            saved = db.get(ManagedMembership, key)
            if saved and saved.role != role:
                raise ValueError("A local permission changed; reconcile it explicitly")
            if not saved:
                db.add(ManagedMembership(subject=key[0], tenant_id=key[1], role=role))
                inserted += 1
    return inserted


def reconcile_memberships(
    store, records, *, complete_snapshot=False, allow_empty=False, dry_run=False
):
    """Apply an explicitly complete snapshot atomically, including role changes and revocations."""
    if complete_snapshot is not True:
        raise ValueError("A complete authoritative snapshot is required for reconciliation")
    expected = _records(records)
    if not expected and allow_empty is not True:
        raise ValueError("An empty snapshot requires explicit confirmation")
    with store.transaction() as db:
        if store.engine.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(92841032)"))
        tenants = set(db.scalars(select(Tenant.id)))
        if any(tenant not in tenants for _, tenant in expected):
            raise ValueError("Resolve unrecognized local tenant before reconciliation")
        existing_rows = list(db.scalars(select(ManagedMembership)))
        existing = {(row.subject, row.tenant_id): row for row in existing_rows}
        inserted = updated = deleted = unchanged = 0
        for key, saved in existing.items():
            if key not in expected:
                deleted += 1
                if not dry_run:
                    db.delete(saved)
            elif saved.role != expected[key]:
                updated += 1
                if not dry_run:
                    saved.role = expected[key]
            else:
                unchanged += 1
        for key, role in expected.items():
            if key not in existing:
                inserted += 1
                if not dry_run:
                    db.add(ManagedMembership(subject=key[0], tenant_id=key[1], role=role))
    return {
        "inserted": inserted,
        "updated": updated,
        "deleted": deleted,
        "unchanged": unchanged,
        "dry_run": bool(dry_run),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_file")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="apply a complete, fresh, independently hash-verified Drone membership snapshot",
    )
    parser.add_argument("--expected-sha256")
    parser.add_argument("--confirm-empty", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.replace and (args.expected_sha256 or args.confirm_empty or args.dry_run):
        parser.error("--expected-sha256, --confirm-empty and --dry-run require --replace")
    if args.replace and not args.expected_sha256:
        parser.error("--replace requires an out-of-band --expected-sha256")
    store = Store(os.environ["DATABASE_URL"], identity_enabled=True)
    store.verify()
    with open(args.snapshot_file, "rb") as source:
        raw = source.read(MAX_SNAPSHOT_BYTES + 1)
    if len(raw) > MAX_SNAPSHOT_BYTES:
        parser.error("Membership snapshot exceeds the 16 MiB limit")
    if args.replace:
        mapping_issuer = os.environ.get("ONESA_IDENTITY_MAPPING_ISSUER", "")
        try:
            snapshot_id, records = load_authoritative_snapshot(
                raw, args.expected_sha256, mapping_issuer
            )
            result = reconcile_memberships(
                store,
                records,
                complete_snapshot=True,
                allow_empty=args.confirm_empty,
                dry_run=args.dry_run,
            )
        except ValueError as error:
            parser.error(str(error))
        action = "Would reconcile" if args.dry_run else "Reconciled"
        print(
            f"{action} snapshot {snapshot_id}: inserted={result['inserted']} "
            f"updated={result['updated']} deleted={result['deleted']} "
            f"unchanged={result['unchanged']}"
        )
    else:
        try:
            payload = json.loads(raw)
            records = payload["drone_memberships"]
            inserted = import_memberships(store, records)
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
            parser.error(f"Invalid additive membership snapshot: {error}")
        print(f"Inserted {inserted} verified workspace memberships")


if __name__ == "__main__":
    main()

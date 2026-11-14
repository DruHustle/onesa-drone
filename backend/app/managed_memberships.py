"""Import a verified identity-migration membership snapshot into this product's store."""

import argparse
import json
from uuid import UUID

from sqlalchemy import select

from .db import Store
from .identity import ManagedMembership
from .models import Tenant


def import_memberships(store, records):
    expected = {}
    for row in records:
        sub, tenant, role = str(UUID(row["user_id"])), str(UUID(row["tenant_id"])), row["role"]
        if role not in {"viewer", "operator", "admin"} or (sub, tenant) in expected:
            raise ValueError("Invalid or duplicate membership")
        expected[sub, tenant] = role
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


def main():
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_file")
    args = parser.parse_args()
    store = Store(os.environ["DATABASE_URL"], identity_enabled=True)
    store.verify()
    with open(args.snapshot_file, encoding="utf-8") as source:
        rows = json.load(source)["drone_memberships"]
    print(f"Inserted {import_memberships(store, rows)} verified workspace memberships")


if __name__ == "__main__":
    main()

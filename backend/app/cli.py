"""Offline bootstrap; never creates default passwords or public accounts."""

import argparse
import getpass
from sqlalchemy import select
from .config import Settings
from .db import Store
from .models import Tenant, User, Aircraft
from .security import password_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["bootstrap", "seed"])
    parser.add_argument("--email", required=True)
    parser.add_argument("--tenant", default="Onesa Simulation Lab")
    args = parser.parse_args()
    cfg = Settings()
    cfg.validate()
    store = Store(cfg.database_url)
    store.initialize()
    with store.transaction() as db:
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if args.action == "bootstrap":
            if user:
                raise SystemExit("Account already exists; no credentials changed")
            password = getpass.getpass("New administrator password (14+ characters): ")
            if len(password) < 14:
                raise SystemExit("Password must contain at least 14 characters")
            if password != getpass.getpass("Confirm password: "):
                raise SystemExit("Passwords differ")
            tenant = Tenant(name=args.tenant)
            db.add(tenant)
            db.flush()
            db.add(
                User(
                    tenant_id=tenant.id,
                    email=args.email.lower(),
                    password=password_hash(password),
                    role="admin",
                )
            )
            print("Created private tenant and administrator; physical interfaces disabled.")
        else:
            if not user:
                raise SystemExit("Bootstrap an account first")
            if db.scalar(select(Aircraft).where(Aircraft.tenant_id == user.tenant_id)):
                raise SystemExit("Fleet already exists; seed refused")
            for name, category, capacity, endurance in [
                ("SIM-001", "multirotor", 4, 35),
                ("SIM-002", "vtol", 8, 55),
                ("SIM-003", "fixed-wing", 5, 60),
            ]:
                db.add(
                    Aircraft(
                        tenant_id=user.tenant_id,
                        name=name,
                        category=category,
                        capacity=capacity,
                        endurance=endurance,
                        model="Illustrative " + category,
                        manufacturer="Onesa simulation reference",
                    )
                )
            print("Created three illustrative aircraft; no real performance claim.")


if __name__ == "__main__":
    main()

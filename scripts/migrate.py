"""Apply the initial versioned schema with a dedicated migrator identity."""

from backend.app.config import Settings
from backend.app.db import Store

if __name__ == "__main__":
    cfg = Settings()
    cfg.validate()
    store = Store(cfg.database_url, identity_enabled=cfg.identity_enabled)
    store.initialize()
    store.verify()
    print("Operational and enabled identity schemas verified. No hardware capability enabled.")

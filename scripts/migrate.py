"""Apply the initial versioned schema with a dedicated migrator identity."""

from backend.app.config import Settings
from backend.app.db import Store

if __name__ == "__main__":
    cfg = Settings()
    cfg.validate()
    store = Store(cfg.database_url)
    store.initialize()
    store.verify()
    print("Schema 0001 verified. No hardware capability enabled.")

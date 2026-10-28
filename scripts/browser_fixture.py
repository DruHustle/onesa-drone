"""Disposable synthetic browser backend; never reads a production environment."""

import os
import sys
import tempfile
import subprocess
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.db import Store
from backend.app.models import Tenant, User
from backend.app.security import password_hash

with tempfile.TemporaryDirectory(prefix="onesa-drone-browser-") as folder:
    url = "sqlite:///" + str(Path(folder) / "browser.db")
    store = Store(url)
    store.initialize()
    with store.transaction() as db:
        t = Tenant(name="Browser acceptance fixture")
        db.add(t)
        db.flush()
        db.add(
            User(
                tenant_id=t.id,
                email="browser@example.test",
                password=password_hash("Synthetic-browser-password-42!"),
                role="admin",
            )
        )
    store.engine.dispose()
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "APP_ORIGIN": "http://127.0.0.1:3400",
        "SIMULATION_WORKER": "true",
        "COOKIE_SECURE": "false",
        "ONESA_AI_URL": "",
        "ONESA_AI_DELEGATED_SESSION": "",
    }
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8400",
            "--no-access-log",
        ],
        env=env,
        cwd=Path(__file__).resolve().parents[1],
    )

    def stop(*_):
        child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        child.wait()
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)

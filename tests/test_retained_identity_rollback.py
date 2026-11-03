"""Actual native API workflows used by the isolated retained-image rehearsal.

SQLite checks HTTP/workflow behavior locally. The ordinary PostgreSQL CI run
additionally exercises real restricted runtime grants in new disposable databases.
Neither run qualifies a different historical Docker image.
"""

import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
from dataclasses import asdict
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url

from backend.app.config import Settings
from backend.app.db import Store
from backend.app.models import SchemaRevision


@pytest.fixture
def proof(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/release/oracle_drone_rollback.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("drone_rollback_native_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    namespace = {}
    exec(compile(module.SCHEMA_WORK + "\n" + module.WORKFLOWS, str(path), "exec"), namespace)
    return namespace


def settings(url):
    return Settings(
        database_url=url,
        origin="http://localhost:3400",
        secure=False,
        worker=True,
        identity_enabled=False,
        ai_url="",
        ai_session="",
    )


def workflow(config, request, *, runtime_role="drone_login", require_runtime_grants=True):
    """Use the same exiting-process boundary as each real image invocation.

    The native worker can dispose an idle engine while another thread holds a
    connection from its previous pool. The owner runner ends that application
    process before restoring or removing its database. A long-lived pytest
    process must not substitute garbage-collection timing for that boundary.
    """
    path = Path(__file__).resolve().parents[1] / "scripts/release/oracle_drone_rollback.py"
    program = """
import importlib.util,json,sys
from pathlib import Path
from backend.app.config import Settings
path=Path(sys.argv[1])
sys.path.insert(0,str(path.parent))
spec=importlib.util.spec_from_file_location('drone_rollback_native_child',path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
namespace={}
exec(compile(module.WORKFLOWS,str(path),'exec'),namespace)
value=json.load(sys.stdin)
result=namespace['exercise'](Settings(**value['settings']),value['request'],runtime_role=value['runtime_role'],require_runtime_grants=value['require_runtime_grants'])
json.dump(result,sys.stdout)
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(path)],
        input=json.dumps(
            {
                "settings": asdict(config),
                "request": request,
                "runtime_role": runtime_role,
                "require_runtime_grants": require_runtime_grants,
            }
        ),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=path.parents[2],
    )
    assert result.returncode == 0, result.stderr[-8000:]
    assert len(result.stdout) <= 65536
    return json.loads(result.stdout)


def test_schema_preflight_failure_closes_real_database_connections(proof, tmp_path, monkeypatch):
    from backend.app import main

    url = "sqlite:///" + str(tmp_path / "preflight.db")
    store = Store(url, identity_enabled=True)
    try:
        store.initialize()
        with store.session() as db:
            schema = {row.version: row.checksum for row in db.scalars(select(SchemaRevision))}
    finally:
        store.engine.dispose()
    accounts = proof["seed_principals"](url)
    create_app = main.create_app
    closed = []

    def tracked_app(config):
        app = create_app(config)
        event.listen(app.state.store.engine, "close", lambda connection, record: closed.append(record))
        return app

    monkeypatch.setattr(main, "create_app", tracked_app)
    with pytest.raises(AssertionError):
        proof["exercise"](
            settings(url),
            {
                "phase": "seed",
                "schema": {**schema, "0002-identity": "wrong"},
                "fixture": {"accounts": accounts},
            },
            require_runtime_grants=False,
        )
    # Failure occurs before TestClient enters its lifespan. Its real SQLAlchemy
    # connection must still close so a PostgreSQL test can drop its owned DB.
    assert closed


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_retained_workflow_survives_an_actual_sqlite_copy(proof, tmp_path, environment):
    source = tmp_path / (environment + "-source.db")
    restored = tmp_path / (environment + "-restored.db")
    url = "sqlite:///" + str(source)
    store = Store(url, identity_enabled=True)
    store.initialize()
    with store.session() as db:
        schema = {row.version: row.checksum for row in db.scalars(select(SchemaRevision))}
    store.engine.dispose()
    accounts = proof["seed_principals"](url)
    seeded = workflow(
        settings(url),
        {"phase": "seed", "schema": schema, "fixture": {"accounts": accounts}},
        require_runtime_grants=False,
    )
    assert seeded["checks"]["native_delivery"] == "CHECKPOINT_ONLY"
    assert seeded["checks"]["restricted_runtime"] == "NOT_RUN"
    assert seeded["fixture"]["checkpoint"] >= 0
    # SQLite's own backup API copies a consistent closed-worker database; no
    # response interception or fabricated authentication/session is involved.
    with sqlite3.connect(source) as original, sqlite3.connect(restored) as copy:
        original.backup(copy)
    observed = workflow(
        settings("sqlite:///" + str(restored)),
        {"phase": "verify", "schema": schema, "fixture": seeded["fixture"]},
        require_runtime_grants=False,
    )
    assert observed["checks"]["restricted_runtime"] == "NOT_RUN"
    assert all(value == "PASS" for key, value in observed["checks"].items() if key != "restricted_runtime")
    assert observed["fixture"]["accounts"] == accounts


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_retained_workflow_uses_real_restricted_postgresql_role(proof, environment):
    configured = os.getenv("DRONE_TEST_DATABASE_URL")
    if not configured:
        pytest.skip("DRONE_TEST_DATABASE_URL is required for the real PostgreSQL grant proof")
    original = make_url(configured)
    assert original.host in {"localhost", "127.0.0.1"}
    assert (original.database or "").startswith("drone_test")
    name = "drone_test_rollback_" + uuid4().hex
    role, group = "drone_test_login_" + uuid4().hex, "drone_test_group_" + uuid4().hex
    owner = create_engine(original)
    url = original.set(database=name)
    created, role_names_reserved = False, False
    try:
        with owner.connect() as db:
            assert (
                db.scalar(
                    text("SELECT count(*) FROM pg_roles WHERE rolname IN (:login,:group)"),
                    {"login": role, "group": group},
                )
                == 0
            )
        role_names_reserved = True
        with owner.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
            db.execute(text('CREATE DATABASE "' + name + '" TEMPLATE template0'))
        created = True
        schema = proof["initialize_schema"](
            url.render_as_string(hide_password=False), runtime_role=role, group_role=group
        )
        password = secrets.token_hex(24)
        isolated = create_engine(url)
        try:
            with isolated.begin() as db:
                db.execute(text('ALTER ROLE "' + role + "\" PASSWORD '" + password + "'"))
        finally:
            isolated.dispose()
        accounts = proof["seed_principals"](url.render_as_string(hide_password=False))
        runtime = url.set(username=role, password=password).render_as_string(hide_password=False)
        seeded = workflow(
            settings(runtime),
            {"phase": "seed", "schema": schema, "fixture": {"accounts": accounts}},
            runtime_role=role,
        )
        observed = workflow(
            settings(runtime),
            {"phase": "verify", "schema": schema, "fixture": seeded["fixture"]},
            runtime_role=role,
        )
        assert all(value == "PASS" for value in observed["checks"].values())
        assert observed["fixture"]["accounts"] == accounts
        assert environment in {"staging", "production"}
    finally:
        try:
            with owner.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
                if created:
                    # Only the database created by this test is removed; never force
                    # another connection to terminate or mutate the suite database.
                    db.execute(text('DROP DATABASE "' + name + '"'))
                if role_names_reserved:
                    # Schema verification may fail after the role transaction has
                    # committed. Observe only these fresh, previously absent names.
                    for selected in [role, group]:
                        if db.scalar(
                            text("SELECT count(*) FROM pg_roles WHERE rolname=:name"), {"name": selected}
                        ):
                            db.execute(text('DROP ROLE "' + selected + '"'))
        finally:
            owner.dispose()

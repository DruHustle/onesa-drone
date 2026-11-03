"""Current-operation compatibility proof for the exact retained Drone images.

Only the explicit shared-identity profile uses this gate. It initializes new
synthetic databases in an isolated PostgreSQL container, restores a real dump,
and runs the actual retained application with local authentication. It does not
read a hosted database or establish historical deployment acceptance.
"""

import copy
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import time
from datetime import datetime, timezone
from uuid import UUID

import oracle_drone as d
import oracle_drone_identity as identity
import oracle_drone_rollback_containers as custody

PROFILE = "retained-identity-disabled-v1"
DATABASES = {"drone_rollback_seed_test", "drone_rollback_restored_test"}
TABLES = {
    "tenants",
    "users",
    "sessions",
    "aircraft",
    "missions",
    "mission_events",
    "audits",
    "receipts",
    "telemetry",
    "incidents",
    "schema_revision",
    "identity_transactions",
    "identity_sessions",
}
CHECKS = {
    "schema_compatibility",
    "restricted_runtime",
    "legacy_authentication",
    "immutable_local_principals",
    "tenant_and_role_isolation",
    "origin_and_csrf",
    "mission_persistence",
    "native_delivery",
    "telemetry_and_audit",
    "physical_commands_disabled",
    "scoped_logout",
}

# Executed inside the exact candidate image, against the newly created owner-only
# database. The runtime grants mirror infrastructure/postgres-roles.sql. No live
# runtime URL, password, environment file or central credential is passed here.
SCHEMA_WORK = r"""
def initialize_schema(url, runtime_role="drone_login", group_role="drone_runtime"):
    import re
    from sqlalchemy import select, text
    from backend.app.db import Store
    from backend.app.models import SchemaRevision
    assert re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", runtime_role)
    assert re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", group_role)
    store = Store(url, identity_enabled=True)
    try:
        store.initialize()
        store.verify()
        with store.engine.begin() as db:
            db.execute(text('CREATE ROLE "' + group_role + '" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'))
            db.execute(text('CREATE ROLE "' + runtime_role + '" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'))
            db.execute(text('GRANT "' + group_role + '" TO "' + runtime_role + '"'))
            db.execute(text('REVOKE CREATE ON SCHEMA public FROM PUBLIC'))
            db.execute(text('GRANT USAGE ON SCHEMA public TO "' + group_role + '"'))
            for permissions, tables in [
                ('SELECT', 'tenants,users,sessions,aircraft,missions,mission_events,audits,receipts,telemetry,incidents,schema_revision'),
                ('INSERT,UPDATE', 'tenants,users,aircraft,missions,incidents'),
                ('INSERT', 'mission_events,audits,receipts'),
                ('INSERT,UPDATE,DELETE', 'sessions,telemetry'),
                ('SELECT,INSERT,UPDATE,DELETE', 'identity_transactions,identity_sessions'),
            ]:
                db.execute(text('GRANT ' + permissions + ' ON ' + tables + ' TO "' + group_role + '"'))
        with store.session() as db:
            result = {row.version: row.checksum for row in db.scalars(select(SchemaRevision))}
            assert set(result) == {'0001', '0002-identity'}
            assert result['0001'] == store.checksum() and result['0002-identity'] == store.identity_checksum()
            return result
    finally:
        store.engine.dispose()

def seed_principals(url):
    import secrets
    from backend.app.db import Store
    from backend.app.models import Tenant, User
    from backend.app.security import password_hash
    store = Store(url)
    try:
        store.verify()
        with store.transaction() as db:
            primary, foreign = Tenant(name='Isolated rollback primary'), Tenant(name='Isolated rollback foreign')
            db.add_all([primary, foreign])
            db.flush()
            result = {}
            for actor, tenant, role in [('operator', primary.id, 'admin'), ('foreign', foreign.id, 'admin'), ('viewer', primary.id, 'viewer')]:
                password = secrets.token_urlsafe(32)
                user = User(tenant_id=tenant, email='rollback-' + secrets.token_hex(16) + '@example.test', password=password_hash(password), role=role)
                db.add(user)
                db.flush()
                result[actor] = {'id': user.id, 'tenant_id': tenant, 'email': user.email, 'role': role, 'password': password, 'password_hash': user.password}
            return result
    finally:
        store.engine.dispose()
"""

WORKFLOWS = r"""
def exercise(settings, request, *, runtime_role="drone_login", require_runtime_grants=True):
    import hashlib, json, secrets
    from uuid import UUID
    from fastapi.testclient import TestClient
    from sqlalchemy import select, text
    from backend.app.main import create_app
    from backend.app.models import User, Tenant, Mission, Audit, SchemaRevision
    from backend.app.service import advance, j
    from autonomy.safety_supervisor.supervisor import physical_command
    assert request['phase'] in {'seed', 'verify'}
    assert not getattr(settings, 'identity_enabled', False) and settings.worker is True
    assert not settings.ai_url and not settings.ai_session
    fixture = request['fixture']
    assert set(fixture['accounts']) == {'operator', 'foreign', 'viewer'}
    assert set(request['schema']) == {'0001', '0002-identity'}
    app = create_app(settings)
    store = app.state.store
    try:
        store.verify()
        with store.session() as db:
            assert {row.version: row.checksum for row in db.scalars(select(SchemaRevision))} == request['schema']
            if require_runtime_grants:
                assert db.scalar(text('SELECT current_user')) == runtime_role
                assert db.scalar(text("SELECT NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls) FROM pg_roles WHERE rolname=current_user")) is True
                assert db.scalar(text("SELECT has_schema_privilege(current_user,'public','CREATE')")) is False
                for table, privilege in [('audits','UPDATE'), ('audits','DELETE'), ('mission_events','DELETE'), ('schema_revision','INSERT'), ('schema_revision','UPDATE'), ('schema_revision','DELETE')]:
                    assert db.scalar(text('SELECT has_table_privilege(current_user,:table,:privilege)'), {'table':table,'privilege':privilege}) is False
            for actor, expected in fixture['accounts'].items():
                for key in ['id','tenant_id']:
                    assert str(UUID(expected[key])) == expected[key]
                assert expected['email'].startswith('rollback-') and expected['email'].endswith('@example.test')
                assert expected['role'] == ('viewer' if actor == 'viewer' else 'admin')
                actual = db.get(User, expected['id'])
                assert actual and actual.active and actual.tenant_id == expected['tenant_id'] and actual.email == expected['email'] and actual.role == expected['role'] and actual.password == expected['password_hash']
            assert fixture['accounts']['operator']['tenant_id'] == fixture['accounts']['viewer']['tenant_id'] != fixture['accounts']['foreign']['tenant_id']
            if request['phase'] == 'verify':
                mission = db.get(Mission, fixture['mission'])
                assert mission and mission.tenant_id == fixture['accounts']['operator']['tenant_id'] and mission.tick == fixture['checkpoint'] and mission.state not in {'completed','cancelled','aborted'}
        try:
            physical_command('arm')
        except PermissionError:
            pass
        else:
            raise AssertionError('Physical command accepted')
        sessions = {}
        with TestClient(app, base_url=settings.origin) as client:
            assert client.get('/api/v1/ready').status_code == 200
            for actor, expected in fixture['accounts'].items():
                client.cookies.clear()
                response = client.post('/api/v1/auth/login', json={'email':expected['email'],'password':expected['password']}, headers={'Origin':settings.origin})
                assert response.status_code == 200
                value = response.json()
                assert all(value[key] == expected[key] for key in ['id','tenant_id','email','role'])
                token = client.cookies.get('drone_session')
                assert isinstance(token, str) and len(token) >= 32 and len(value['csrf']) >= 24
                sessions[actor] = {'Cookie':'drone_session=' + token,'Origin':settings.origin,'X-CSRF-Token':value['csrf']}
            client.cookies.clear()
            def call(actor, method, path, *, body=None, status=200, override=None):
                headers = {**sessions[actor], **(override or {})}
                if method == 'POST':
                    headers['Idempotency-Key'] = secrets.token_hex(16)
                response = client.request(method, path, json=body, headers=headers)
                client.cookies.clear()
                assert response.status_code == status, (method, path, response.status_code)
                return response.json() if response.content else None
            for actor, expected in fixture['accounts'].items():
                me = call(actor, 'GET', '/api/v1/auth/me')
                assert all(me[key] == expected[key] for key in ['id','tenant_id','email','role'])
            aircraft = {'name':'Synthetic rollback aircraft','model':'Reference quad','manufacturer':'Illustrative','category':'multirotor','capacity':4,'endurance':35}
            call('operator','POST','/api/v1/aircraft',body=aircraft,status=403,override={'X-CSRF-Token':''})
            call('operator','POST','/api/v1/aircraft',body=aircraft,status=403,override={'Origin':'http://localhost:3401'})
            call('viewer','POST','/api/v1/aircraft',body=aircraft,status=403)
            if request['phase'] == 'seed':
                fixture['aircraft'] = call('operator','POST','/api/v1/aircraft',body=aircraft,status=201)['id']
                delivery = call('operator','POST','/api/v1/missions',body={'label':'Isolated retained-image delivery','package_weight':1.2,'package_kind':'standard','origin':{'lat':52.52,'lon':13.405},'destination':{'lat':52.523,'lon':13.411},'scenario':'nominal'},status=201)
                mission, fixture['tracking_token'] = delivery['mission'], delivery['tracking_token']
                fixture['mission'] = mission['id']
                for action in ['plan','validate','authorize','launch']:
                    mission = call('operator','POST','/api/v1/missions/' + fixture['mission'] + '/commands',body={'action':action,'revision':mission['revision']})
            def current_mission(actor):
                snapshot = call(actor, 'GET', '/api/v1/operations')
                matches = [row for row in snapshot['missions'] if row['id'] == fixture['mission']]
                assert len(matches) == 1
                return matches[0]
            foreign_snapshot = call('foreign','GET','/api/v1/operations')
            assert not any(row['id'] == fixture['mission'] for row in foreign_snapshot['missions'])
            call('foreign','GET','/api/v1/missions/' + fixture['mission'] + '/history',status=404)
            mission = current_mission('viewer')
            assert call('viewer','GET','/api/v1/missions/' + fixture['mission'] + '/history')['events']
            call('viewer','POST','/api/v1/missions/' + fixture['mission'] + '/commands',body={'action':'cancel','revision':mission['revision']},status=403)
            if request['phase'] == 'verify':
                for _ in range(180):
                    with store.transaction(fixture['accounts']['operator']['tenant_id']) as db:
                        mission = db.get(Mission, fixture['mission'])
                        if mission.state == 'completed':
                            break
                        advance(db, mission, settings.telemetry_limit)
                observed = current_mission('operator')
                assert observed['state'] == 'completed' and observed['delivered'] is True
                history = call('operator','GET','/api/v1/missions/' + fixture['mission'] + '/history')
                assert len(history['telemetry']) > 15 and history['events'][-1]['state'] == 'completed'
                tracking = client.get('/api/v1/tracking/' + fixture['tracking_token']).json()
                assert tracking['delivered'] and tracking['progress_percent'] == 100
                assert not {'aircraft_id','destination','origin','position','label'} & tracking.keys()
            for actor in sessions:
                call(actor,'POST','/api/v1/auth/logout')
                call(actor,'GET','/api/v1/auth/me',status=401)
        # Lifespan has now stopped the real simulation worker. Capture the checkpoint
        # only after shutdown; no background writer races the subsequent dump.
        with store.session() as db:
            mission = db.get(Mission, fixture['mission'])
            if request['phase'] == 'seed':
                assert mission.state not in {'completed','cancelled','aborted'}
                fixture['checkpoint'] = mission.tick
            for expected in fixture['accounts'].values():
                actual = db.get(User, expected['id'])
                assert actual.password == expected['password_hash'] and actual.role == expected['role'] and actual.tenant_id == expected['tenant_id']
            for tenant in db.scalars(select(Tenant)):
                rows = list(db.scalars(select(Audit).where(Audit.tenant_id == tenant.id)))
                remaining = {row.previous:row for row in rows}
                assert len(remaining) == len(rows)
                previous = ''
                while previous in remaining:
                    row = remaining.pop(previous)
                    assert hashlib.sha256(j([row.id,row.tenant_id,row.at,row.actor,row.action,row.detail,row.correlation_id,row.previous]).encode()).hexdigest() == row.digest
                    previous = row.digest
                assert not remaining and previous == tenant.audit_head
        checks = {name:'PASS' for name in ['schema_compatibility','restricted_runtime','legacy_authentication','immutable_local_principals','tenant_and_role_isolation','origin_and_csrf','mission_persistence','native_delivery','telemetry_and_audit','physical_commands_disabled','scoped_logout']}
        if request['phase'] == 'seed':
            checks['native_delivery'] = 'CHECKPOINT_ONLY'
        if not require_runtime_grants:
            checks['restricted_runtime'] = 'NOT_RUN'
        return {'fixture':fixture,'schema':request['schema'],'checks':checks}
    finally:
        store.engine.dispose()

"""

PROGRAM = (
    r"""
import json,os,sys
from sqlalchemy.engine import make_url
from backend.app.config import Settings
raw=sys.stdin.buffer.read(65537)
assert len(raw)<=65536
request=json.loads(raw)
assert set(request)=={'phase','fixture','schema'}
url=make_url(os.environ['DATABASE_URL'])
assert url.username=='drone_login' and url.host is None and url.database in {'drone_rollback_seed_test','drone_rollback_restored_test'} and url.query=={'host':'/var/run/postgresql'}
settings=Settings()
settings.validate()
assert settings.origin=='http://localhost:3400' and settings.secure is False and settings.worker is True and not getattr(settings,'identity_enabled',False)
"""
    + WORKFLOWS
    + "\nprint(json.dumps(exercise(settings,request),separators=(',',':')))\n"
)

SCHEMA_PROGRAM = (
    r"""
import json,os
from sqlalchemy.engine import make_url
url=make_url(os.environ['DATABASE_URL'])
assert url.username=='drone_owner' and url.host is None and url.database=='drone_rollback_seed_test' and url.query=={'host':'/var/run/postgresql'}
"""
    + SCHEMA_WORK
    + "\nprint(json.dumps({'schema':initialize_schema(os.environ['DATABASE_URL']),'accounts':seed_principals(os.environ['DATABASE_URL'])},separators=(',',':')))\n"
)


def read(path):
    path = d.private(path)
    d.require(
        path.stat().st_nlink == 1 and path.stat().st_size <= 1024 * 1024,
        "DRONE_ROLLBACK_PRIVATE_RECORD_BOUND",
    )
    return json.loads(path.read_bytes(), object_pairs_hook=identity.unique)


def profile(plan, binding):
    d.require(plan.get("qualification_profile") == identity.PROFILE, "DRONE_SHARED_ROLLBACK_PROFILE_REQUIRED")
    path = plan["rollback_file"]
    recovery = read(path)
    d.require(
        set(recovery)
        == {"strategy", "source_commit", "preserve_database", "physical_interfaces_disabled", "environments"}
        and recovery["strategy"] == PROFILE
        and recovery["source_commit"] == binding["candidate_commit"]
        and recovery["preserve_database"] is True
        and recovery["physical_interfaces_disabled"] is True
        and set(recovery["environments"]) == {"staging", "production"},
        "DRONE_SOURCE_BOUND_RETAINED_ROLLBACK_REQUIRED",
    )
    for environment, retained in recovery["environments"].items():
        slot, entry = plan["slots"][environment], plan["identity"]["environments"][environment]
        hashes = slot["configuration_sha256"]
        d.require(
            path in hashes and hashes[path] == d.digest(d.private(path)),
            "DRONE_ROLLBACK_PLAN_NOT_CONFIGURATION_BOUND",
        )
        d.require(
            set(retained) == {"source_commit", "image_id", "runtime_sha256", "migrator_sha256"}
            and re.fullmatch(r"[a-f0-9]{40}", retained["source_commit"])
            and re.fullmatch(r"sha256:[a-f0-9]{64}", retained["image_id"])
            and retained["image_id"] == slot["previous_image"]
            and slot["provision_database"] is False,
            "DRONE_RETAINED_SOURCE_IMAGE_SCOPE",
        )
        for kind in ["runtime", "migrator"]:
            baseline = entry["baseline_" + kind + "_file"]
            d.require(
                hashes.get(baseline) == retained[kind + "_sha256"] == d.digest(d.private(baseline)),
                "DRONE_RETAINED_CONFIGURATION_CHANGED",
            )
            values = identity.values(baseline)
            d.require(
                values.get("ONESA_IDENTITY_ENABLED", "false") == "false",
                "DRONE_RETAINED_IDENTITY_MUST_BE_DISABLED",
            )
        values = identity.values(entry["baseline_runtime_file"])
        d.require(
            values.get("APP_ORIGIN") == slot["origin"]
            and values.get("COOKIE_SECURE") == "true"
            and values.get("SIMULATION_WORKER", "true") == "true"
            and not values.get("ONESA_AI_URL")
            and not values.get("ONESA_AI_DELEGATED_SESSION"),
            "DRONE_RETAINED_SIMULATION_CONFIGURATION_REQUIRED",
        )
    return recovery


def context(runner):
    runner.check_context()
    rows = [row for row in runner.context_records if row["kind"] == "context"]
    d.require(
        len(rows) == 1 and rows[0]["binding"] == runner.binding, "DRONE_ROLLBACK_SIGNED_CONTEXT_REQUIRED"
    )
    return copy.deepcopy(rows[0])


def proof_folder(runner, original):
    identifier = original["id"]
    d.require(
        str(UUID(identifier)) == identifier and runner.component in {"backend", "frontend"},
        "DRONE_ROLLBACK_CONTEXT_SCOPE",
    )
    return d.private(runner.folder, directory=True) / (
        identifier + "-" + runner.component + "-identity-rollback"
    )


def images(plan, binding, recovery):
    native = read(plan["build_manifests"]["backend"])["runtime_image_ids"]
    expected = {
        "candidate": (
            plan["runtime_images"][plan["api_image"]],
            native[plan["api_image"]],
            binding["candidate_commit"],
            "10001:10001",
        ),
        "database": (
            plan["runtime_images"][plan["database_image"]],
            native[plan["database_image"]],
            None,
            "70:70",
        ),
        **{
            env: (value["image_id"], value["image_id"], value["source_commit"], "10001:10001")
            for env, value in recovery["environments"].items()
        },
    }
    observed = {}
    for name, (reference, image_id, source, user) in expected.items():
        rows = json.loads(custody.docker("image", "inspect", reference, timeout=15))
        d.require(isinstance(rows, list) and len(rows) == 1, "DRONE_ROLLBACK_IMAGE_MISSING")
        row = rows[0]
        d.require(
            row["Id"] == image_id
            and row["Architecture"] == "arm64"
            and row["Os"] == "linux"
            and row["Config"]["User"] == user
            and (
                set(row["Config"].get("Volumes") or {}) <= {"/var/lib/postgresql/data"}
                if name == "database"
                else not row["Config"].get("Volumes")
            )
            and (source is None or row["Config"].get("Labels", {}).get("org.onesa.source-commit") == source),
            "DRONE_ROLLBACK_IMMUTABLE_IMAGE_OR_SOURCE_CHANGED",
        )
        observed[name] = {"image_id": image_id, "source_commit": source, "user": user}
    return observed


def native_environment(plan, environment, database):
    d.require(database in DATABASES, "DRONE_ROLLBACK_DATABASE_SCOPE")
    entry = plan["identity"]["environments"][environment]
    previous = identity.values(entry["baseline_runtime_file"])
    # Preserve nonsecret native behavior; no live database or provider credential
    # enters the isolated application. Its only writable data is the new fixture.
    values = {
        key: previous[key]
        for key in ["ONESA_AI_PROVIDER", "ONESA_AI_MODEL", "ONESA_AI_COOKIE_NAME"]
        if key in previous
    }
    values.update(
        DATABASE_URL="postgresql+psycopg://drone_login@/" + database + "?host=/var/run/postgresql",
        APP_ORIGIN="http://localhost:3400",
        COOKIE_SECURE="false",
        SIMULATION_WORKER="true",
        ONESA_IDENTITY_ENABLED="false",
        ONESA_AI_URL="",
        ONESA_AI_API_KEY="",
        ONESA_AI_DELEGATED_SESSION="",
        HOME="/tmp",
    )
    return [key + "=" + value for key, value in sorted(values.items())]


def application(container, plan, environment, database, schema, fixture, phase):
    request = {"phase": phase, "schema": schema, "fixture": fixture}
    raw = d.canonical(request)
    d.require(len(raw) <= 65536, "DRONE_ROLLBACK_FIXTURE_BOUND")
    response = container.run(
        "python",
        ["-c", PROGRAM],
        environment=native_environment(plan, environment, database),
        data=raw,
        timeout=120,
    )
    d.require(len(response) <= 65536, "DRONE_ROLLBACK_RESULT_BOUND")
    observed = json.loads(response, object_pairs_hook=identity.unique)
    d.require(
        set(observed) == {"fixture", "schema", "checks"}
        and observed["schema"] == schema
        and observed["checks"]
        == {
            key: ("CHECKPOINT_ONLY" if key == "native_delivery" and phase == "seed" else "PASS")
            for key in CHECKS
        },
        "DRONE_RETAINED_IMAGE_COMPATIBILITY_FAILED",
    )
    return observed


def qualify(runner, recovery, original, image_ids):
    d.require(
        runner.phase == "staging" and runner.context == {"context_id": original["id"]},
        "DRONE_ROLLBACK_STAGING_ONLY",
    )
    folder = proof_folder(runner, original)
    folder.mkdir(mode=0o700, exist_ok=False)
    custody.sync_directory(folder.parent)
    operation = original["id"]
    socket = folder / "socket"
    database = custody.OwnedContainer(
        folder,
        operation,
        "database",
        image_ids["database"]["image_id"],
        binds=[(socket, "/var/run/postgresql", True)],
        tmpfs={
            "/tmp": "rw,mode=1777,size=64m",
            "/var/lib/postgresql/data": "rw,mode=700,uid=70,gid=70,size=512m",
        },
        memory=256,
        pids=64,
        user="70:70",
    )
    schema_container = custody.OwnedContainer(
        folder,
        operation,
        "schema",
        image_ids["candidate"]["image_id"],
        binds=[(socket, "/var/run/postgresql", False)],
    )
    applications = {
        (environment, phase): custody.OwnedContainer(
            folder,
            operation,
            environment + "-" + phase,
            image_ids["candidate" if phase == "seed" else environment]["image_id"],
            binds=[(socket, "/var/run/postgresql", False)],
        )
        for environment in ["staging", "production"]
        for phase in ["seed", "verify"]
    }
    containers = [database, schema_container, *applications.values()]
    d.require(
        not custody.inventory("label=" + custody.LABEL + "=" + operation)
        and all(not custody.inventory("name=^/" + item.name + "$") for item in containers),
        "DRONE_ROLLBACK_NAMESPACE_EXISTS_INSPECT_ONLY",
    )
    custody.write(
        folder / "intent.json",
        {
            "binding": runner.binding,
            "context": original,
            "images": image_ids,
            "recovery": recovery,
            "containers": [item.descriptor() for item in containers],
            "automatic_retry": False,
            "production_writes": 0,
        },
    )
    socket_identity, result = None, None

    def query(target, statement):
        d.require(target in DATABASES and database.cid is not None, "DRONE_ROLLBACK_DATABASE_UNCONFIRMED")
        return (
            custody.docker(
                "exec",
                "-i",
                database.cid,
                "psql",
                "-XqAt",
                "-U",
                "drone_owner",
                "-d",
                target,
                "-v",
                "ON_ERROR_STOP=1",
                data=statement.encode(),
                timeout=60,
            )
            .decode()
            .strip()
        )

    def manifest(target):
        return {
            table: query(
                target,
                "SELECT encode(sha256(convert_to(coalesce(string_agg(to_jsonb(t)::text,E'\\n' ORDER BY to_jsonb(t)::text),''),'UTF8')),'hex') FROM public."
                + table
                + " t;",
            )
            for table in sorted(TABLES)
        }

    try:
        socket.mkdir(mode=0o700)
        observed = socket.stat()
        socket_identity = (observed.st_dev, observed.st_ino, observed.st_uid, observed.st_gid)
        os.chown(socket, 70, 70)
        observed = socket.stat()
        socket_identity = (observed.st_dev, observed.st_ino, observed.st_uid, observed.st_gid)
        custody.sync_directory(folder)
        database.run(
            "docker-entrypoint.sh",
            ["postgres", "-c", "listen_addresses=", "-c", "unix_socket_permissions=0777"],
            environment=[
                "POSTGRES_USER=drone_owner",
                "POSTGRES_DB=drone_rollback_seed_test",
                "POSTGRES_PASSWORD=" + secrets.token_urlsafe(32),
                "PGDATA=/var/lib/postgresql/data",
            ],
            detached=True,
            timeout=30,
        )
        deadline = time.monotonic() + 60
        while True:
            try:
                d.require(
                    query("drone_rollback_seed_test", "SELECT 1;") == "1", "DRONE_ROLLBACK_DATABASE_STARTUP"
                )
                break
            except (ValueError, TimeoutError):
                d.require(time.monotonic() < deadline, "DRONE_ROLLBACK_DATABASE_STARTUP")
                time.sleep(0.25)
        prepared = json.loads(
            schema_container.run(
                "python",
                ["-c", SCHEMA_PROGRAM],
                environment=[
                    "HOME=/tmp",
                    "DATABASE_URL=postgresql+psycopg://drone_owner@/drone_rollback_seed_test?host=/var/run/postgresql",
                ],
                timeout=90,
            ),
            object_pairs_hook=identity.unique,
        )
        schema = prepared["schema"]
        d.require(
            set(schema) == {"0001", "0002-identity"}
            and all(re.fullmatch(r"[a-f0-9]{64}", value) for value in schema.values()),
            "DRONE_ROLLBACK_ADDITIVE_SCHEMA_REQUIRED",
        )
        original_manifest = manifest("drone_rollback_seed_test")
        original_dump = custody.docker(
            "exec",
            database.cid,
            "pg_dump",
            "-U",
            "drone_owner",
            "-d",
            "drone_rollback_seed_test",
            "-Fc",
            "--no-owner",
            "--no-acl",
            timeout=60,
        )
        d.require(
            original_dump.startswith(b"PGDMP") and len(original_dump) <= 32 * 1024 * 1024,
            "DRONE_ROLLBACK_SYNTHETIC_DUMP_BOUND",
        )
        grants = query(
            "drone_rollback_seed_test",
            "SELECT string_agg('GRANT ' || privilege_type || ' ON public.' || quote_ident(table_name) || ' TO ' || quote_ident(grantee) || ';', E'\\n' ORDER BY table_name,privilege_type) FROM information_schema.role_table_grants WHERE table_schema='public' AND grantee='drone_runtime';",
        )
        d.require(grants and len(grants) <= 32768, "DRONE_ROLLBACK_RUNTIME_GRANTS_REQUIRED")

        def restore(target, archive):
            d.require(target in DATABASES, "DRONE_ROLLBACK_DATABASE_SCOPE")
            custody.docker("exec", database.cid, "createdb", "-U", "drone_owner", target, timeout=20)
            custody.docker(
                "exec",
                "-i",
                database.cid,
                "pg_restore",
                "-U",
                "drone_owner",
                "-d",
                target,
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
                data=archive,
                timeout=60,
            )
            # Reapply only the current source's bounded runtime grants.
            query(
                target,
                "REVOKE CREATE ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO drone_runtime; "
                + grants,
            )

        environments = {}
        for environment in ["staging", "production"]:
            # Each native configuration gets its own new operational fixture. The
            # same immutable principals can authenticate both retained images.
            fixture = {"accounts": copy.deepcopy(prepared["accounts"])}
            seeded = application(
                applications[(environment, "seed")],
                runner.plan,
                environment,
                "drone_rollback_seed_test",
                schema,
                fixture,
                "seed",
            )
            before = manifest("drone_rollback_seed_test")
            dump = custody.docker(
                "exec",
                database.cid,
                "pg_dump",
                "-U",
                "drone_owner",
                "-d",
                "drone_rollback_seed_test",
                "-Fc",
                "--no-owner",
                "--no-acl",
                timeout=60,
            )
            d.require(
                dump.startswith(b"PGDMP") and len(dump) <= 32 * 1024 * 1024,
                "DRONE_ROLLBACK_SYNTHETIC_DUMP_BOUND",
            )
            restore("drone_rollback_restored_test", dump)
            d.require(
                manifest("drone_rollback_restored_test") == before, "DRONE_ROLLBACK_RESTORE_CONTENT_CHANGED"
            )
            verified = application(
                applications[(environment, "verify")],
                runner.plan,
                environment,
                "drone_rollback_restored_test",
                schema,
                seeded["fixture"],
                "verify",
            )
            environments[environment] = {
                **recovery["environments"][environment],
                "checks": verified["checks"],
                "restored_manifest_sha256": hashlib.sha256(d.canonical(before)).hexdigest(),
                "runtime_role": "drone_login",
                "native_worker": True,
            }
            custody.docker(
                "exec",
                database.cid,
                "dropdb",
                "-U",
                "drone_owner",
                "drone_rollback_restored_test",
                timeout=20,
            )
            if environment == "staging":
                # Recreate only this new synthetic database from its pristine
                # dump, so the next real worker never advances a prior fixture.
                custody.docker(
                    "exec",
                    database.cid,
                    "dropdb",
                    "-U",
                    "drone_owner",
                    "drone_rollback_seed_test",
                    timeout=20,
                )
                restore("drone_rollback_seed_test", original_dump)
                d.require(
                    manifest("drone_rollback_seed_test") == original_manifest,
                    "DRONE_ROLLBACK_PRISTINE_RESTORE_CHANGED",
                )
        result = {
            "schema_version": 1,
            "profile": PROFILE,
            "binding": runner.binding,
            "operation_id": operation,
            "context_sha256": hashlib.sha256(d.canonical(original)).hexdigest(),
            "images": image_ids,
            "recovery": recovery,
            "schema": schema,
            "environments": environments,
            "synthetic_database_restore": "PASS",
            "production_writes": 0,
            "hosted_database_connections": 0,
            "network": "none",
            "isolated_overrides": [
                "synthetic_database_url",
                "loopback_origin",
                "insecure_loopback_cookie",
                "excluded_external_credentials",
            ],
            "status": "PASS",
        }
    finally:
        cleaned = False
        try:
            custody.cleanup_owned(containers, operation)
            if socket_identity is not None:
                d.private(folder, directory=True)
                observed = socket.lstat()
                d.require(
                    (observed.st_dev, observed.st_ino, observed.st_uid, observed.st_gid) == socket_identity
                    and stat.S_ISDIR(observed.st_mode)
                    and stat.S_IMODE(observed.st_mode) in {0o700, 0o3775},
                    "DRONE_ROLLBACK_SOCKET_CHANGED",
                )
                shutil.rmtree(socket)
                custody.sync_directory(folder)
            d.require(
                not socket.exists() and not socket.is_symlink(), "DRONE_ROLLBACK_SOCKET_REMOVAL_UNCONFIRMED"
            )
            cleaned = True
        finally:
            custody.write(
                folder / "cleanup.json",
                {
                    "operation_id": operation,
                    "isolated_containers_removed": cleaned,
                    "private_inputs_retained": not cleaned,
                    "containers": {item.name: item.cid for item in containers if item.attempted},
                    "release_authority": False,
                },
            )
    d.require(
        result is not None and context(runner) == original, "DRONE_ROLLBACK_AUTHORITY_OR_RESULT_CHANGED"
    )
    d.require(
        profile(runner.plan, runner.binding) == recovery
        and images(runner.plan, runner.binding, recovery) == image_ids,
        "DRONE_ROLLBACK_PINS_CHANGED",
    )
    result.update(
        isolated_containers_removed=True,
        cleanup_sha256=d.digest(folder / "cleanup.json"),
        observed_at=datetime.now(timezone.utc).isoformat(),
    )
    custody.write(folder / "receipt.json", result)
    return result


def gate(runner):
    d.require(os.geteuid() == 0 and not os.getenv("GITHUB_ACTIONS"), "DRONE_ROLLBACK_OWNER_ONLY")
    original = context(runner)
    recovery = profile(runner.plan, runner.binding)
    image_ids = images(runner.plan, runner.binding, recovery)
    folder = proof_folder(runner, original)
    if runner.phase == "staging":
        qualify(runner, recovery, original, image_ids)
    proof = read(folder / "receipt.json")
    cleanup = read(folder / "cleanup.json")
    d.require(
        proof.get("profile") == PROFILE
        and proof.get("binding") == runner.binding
        and proof.get("operation_id") == original["id"]
        and proof.get("context_sha256") == hashlib.sha256(d.canonical(original)).hexdigest()
        and proof.get("images") == image_ids
        and proof.get("recovery") == recovery
        and proof.get("status") == proof.get("synthetic_database_restore") == "PASS"
        and type(proof.get("production_writes")) is int
        and proof["production_writes"] == 0
        and type(proof.get("hosted_database_connections")) is int
        and proof["hosted_database_connections"] == 0
        and proof.get("network") == "none"
        and proof.get("isolated_containers_removed") is True
        and proof.get("cleanup_sha256") == d.digest(folder / "cleanup.json")
        and cleanup.get("operation_id") == original["id"]
        and cleanup.get("isolated_containers_removed") is True
        and cleanup.get("private_inputs_retained") is False
        and set(proof.get("schema", {})) == {"0001", "0002-identity"}
        and set(proof.get("environments", {})) == {"staging", "production"},
        "DRONE_EXACT_STAGING_ROLLBACK_PROOF_REQUIRED",
    )
    for environment, observed in proof["environments"].items():
        d.require(
            all(observed.get(key) == value for key, value in recovery["environments"][environment].items())
            and observed.get("runtime_role") == "drone_login"
            and observed.get("native_worker") is True
            and set(observed.get("checks", {})) == CHECKS
            and all(value == "PASS" for value in observed["checks"].values()),
            "DRONE_RETAINED_WORKFLOW_PROOF_REQUIRED",
        )
    summary = {
        "profile": PROFILE,
        "qualification_context_id": original["id"],
        "receipt_sha256": d.digest(folder / "receipt.json"),
    }
    qualifications = [row for row in runner.context_records if row["kind"] == "qualification"]
    if qualifications:
        d.require(
            len(qualifications) == 1
            and qualifications[0]["details"]["staging"]["observations"].get("rollback_proof") == summary,
            "DRONE_SIGNED_ROLLBACK_PROOF_CHANGED",
        )
    d.require(context(runner) == original, "DRONE_ROLLBACK_AUTHORITY_CHANGED")
    return summary

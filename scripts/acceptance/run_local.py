import argparse
import os
import sys
import subprocess
import contextlib
import base64
import json
import time
import socket
import uuid
import secrets
import signal
import tempfile
import ssl
import urllib.error
import urllib.request
from pathlib import Path
import psycopg
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from loopback_tls import loopback_certificates
from expire_native_session import verify_native_audit

scripts = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(
    description="Run the actual Portal and Drone issuer, API and browser client with disposable loopback databases."
)
parser.add_argument(
    "--portal",
    required=True,
    type=Path,
    help="Portal checkout with installed locked dependencies and built backend",
)
parser.add_argument(
    "--pg-bin", required=True, type=Path, help="Directory containing PostgreSQL initdb and postgres"
)
parser.add_argument(
    "--chromium", type=Path, help="Use this Chromium binary instead of the Playwright Chromium installation"
)
mode = parser.add_mutually_exclusive_group()
mode.add_argument(
    "--native-ui", choices=["ios", "android"],
    help="Exercise installed debug builds against real loopback services and a disposable device trust store",
)
mode.add_argument(
    "--protocol-only",
    action="store_true",
    help="Skip Chromium; exercise both products over HTTPS including native callback transport",
)
args = parser.parse_args()
drone = scripts.parent.parent
portal = args.portal.resolve()
pg_bin = args.pg_bin.resolve()
portal_backend = portal / "onesa-company-portal-backend"
portal_frontend = portal / "onesa-company-portal-frontend"
if not (portal_backend / "dist/src/app.js").is_file():
    sys.exit("Build the selected Portal backend before running acceptance.")
if not args.protocol_only and not args.native_ui and not (drone / "frontend/dist/index.html").is_file():
    sys.exit("Build the selected Drone frontend before running browser acceptance.")
drone_origin = "https://127.0.0.1:54844"
portal_origin = "https://localhost:54843"

allowed = ["PATH", "HOME", "LANG", "TMPDIR", "LD_LIBRARY_PATH"]
env = {name: os.environ[name] for name in allowed if name in os.environ}
env.update(
    {
        "NO_PROXY": "localhost,127.0.0.1",
        "RAYON_NUM_THREADS": "2",
        "UV_THREADPOOL_SIZE": "2",
        "TZ": "UTC",
        "NEXT_TELEMETRY_DISABLED": "1",
    }
)
env["NODE_OPTIONS"] = "--max-old-space-size=700"


def execute(args, cwd, extra=None):
    # Dependency and database exceptions may include the connection URL.
    with (temp / "setup.log").open("ab") as log:
        result = subprocess.run(args, cwd=cwd, env=env | dict(extra or {}), stdout=log, stderr=log)
    if result.returncode:
        raise RuntimeError(f"Local setup failed in {Path(args[0]).name} (exit {result.returncode})")


def verify_fixture_control_denials(origin, key, ca, *, exhausted=False):
    context = ssl.create_default_context(cafile=str(ca))
    headers = {"x-onesa-fixture-control": key, "x-onesa-fixture-role": "member"}
    attempts = [("POST", {"x-onesa-fixture-control": key}, None)] if exhausted else [
        ("POST", {}, None),
        ("GET", headers, None),
        ("POST", headers | {"x-onesa-fixture-role": "admin"}, None),
        ("POST", headers, b"{}"),
    ]
    for method, request_headers, data in attempts:
        request = urllib.request.Request(origin + "/__onesa_fixture/expire-product-session", method=method,
                                         headers=request_headers, data=data)
        try:
            with urllib.request.urlopen(request, context=context, timeout=5) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        if status != 404:
            raise RuntimeError("Native fixture control scope guard failed")
    print("PASS native fixture control " + ("refuses third expiry" if exhausted else "rejects missing key, wrong role, GET and bodies"), flush=True)


def up(resources, label, args, cwd, extra=None):
    f = resources.enter_context(open(temp / (label + ".log"), "w"))
    p = subprocess.Popen(
        args, cwd=cwd, env=env | dict(extra or {}), stdout=f, stderr=f, start_new_session=True
    )

    def end():
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()

    resources.callback(end)
    return p


def ready(port, p):
    for i in range(200):
        if p.poll() is not None:
            raise RuntimeError(f"service {port} exited {p.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), 0.2):
                return
        except OSError:
            time.sleep(0.15)
    raise RuntimeError(f"service {port} timed out")


def random_secret():
    return secrets.token_hex(32)


def jwk_integer(i):
    return base64.urlsafe_b64encode(i.to_bytes((i.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()


def report(t):
    print(t, flush=True)


with contextlib.ExitStack() as resources:
    temp = Path(resources.enter_context(tempfile.TemporaryDirectory(prefix="onesa-drone-acceptance-")))
    ca, cert, key = loopback_certificates(temp)
    db_password = secrets.token_hex(32)
    password_file = temp / "pg-password"
    password_file.write_text(db_password + "\n")
    password_file.chmod(0o600)
    execute(["node", scripts / "build-account.mjs"], temp, {"PORTAL_ROOT": str(portal)})
    data = temp / "pg"
    execute(
        [
            pg_bin / "initdb",
            "-D",
            data,
            "-A",
            "scram-sha-256",
            "--pwfile",
            password_file,
            "-U",
            "fixture",
            "--locale=C",
            "--encoding=UTF8",
        ],
        temp,
    )
    p = up(
        resources,
        "postgres",
        [
            pg_bin / "postgres",
            "-D",
            data,
            "-c",
            "unix_socket_directories=",
            "-h",
            "127.0.0.1",
            "-p",
            "56882",
            "-c",
            "ssl=on",
            "-c",
            f"ssl_key_file={key}",
            "-c",
            f"ssl_cert_file={cert}",
        ],
        temp,
    )
    ready(56882, p)
    with psycopg.connect(
        f"postgresql://fixture:{db_password}@127.0.0.1:56882/postgres", autocommit=True
    ) as db:
        db.execute("create database drone_test")
        db.execute("create database portal_test")
    report("Isolated PostgreSQL databases ready")
    client = "test_onesa_drone_a77"
    secret = random_secret()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_numbers()
    jwk = {
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "kid": "synthetic_onesa_test",
        "n": jwk_integer(private_key.public_numbers.n),
        "e": jwk_integer(private_key.public_numbers.e),
        "d": jwk_integer(private_key.d),
        "p": jwk_integer(private_key.p),
        "q": jwk_integer(private_key.q),
        "dp": jwk_integer(private_key.dmp1),
        "dq": jwk_integer(private_key.dmq1),
        "qi": jwk_integer(private_key.iqmp),
    }
    cfg = {
        "issuer": portal_origin + "/api/v1/identity",
        "clients": [
            {
                "product": "drone",
                "clientId": client,
                "clientSecret": secret,
                "redirectUri": drone_origin + "/api/v1/auth/identity/callback",
                "applicationUrl": drone_origin + "/",
            }
        ],
        "cookieKeys": [random_secret()],
        "jwks": {"keys": [jwk]},
    }
    session = random_secret()
    proxy = random_secret()
    member = str(uuid.uuid4())
    admin = str(uuid.uuid4())
    tenant = str(uuid.uuid4())
    other = str(uuid.uuid4())
    password = random_secret()
    native_control_key = random_secret()
    portal_env = {
        "DATABASE_URL": f"postgresql://fixture:{db_password}@127.0.0.1:56882/portal_test",
        "SESSION_KEY": session,
        "PUBLIC_ORIGIN": portal_origin,
        "PROXY_SHARED_KEY": proxy,
        "ONESA_IDENTITY_ENABLED": "true",
        "ONESA_IDENTITY_CONFIG_B64": base64.b64encode(json.dumps(cfg).encode()).decode(),
        "AWS_EC2_METADATA_DISABLED": "true",
        "NODE_ENV": "test",
        "MAIL_PROVIDER": "smtp",
    }
    drone_env = {
        "DATABASE_URL": f"postgresql+psycopg://fixture:{db_password}@127.0.0.1:56882/drone_test?sslmode=verify-full&sslrootcert={ca}",
        "APP_ORIGIN": drone_origin,
        "COOKIE_SECURE": "true",
        "SIMULATION_WORKER": "true",
        "ONESA_IDENTITY_ENABLED": "true",
        "ONESA_IDENTITY_ISSUER": cfg["issuer"],
        "ONESA_IDENTITY_CLIENT_ID": client,
        "ONESA_IDENTITY_CLIENT_SECRET": secret,
        "ONESA_IDENTITY_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "ONESA_IDENTITY_CALLBACK": cfg["clients"][0]["redirectUri"],
        "SSL_CERT_FILE": str(ca),
        "ONESA_AI_PROVIDER": "disabled",
    }
    execute([sys.executable, "-m", "scripts.migrate"], drone, drone_env)
    execute(["node", "--import", "tsx", "src/services/migrate.ts"], portal_backend, portal_env)
    with psycopg.connect(
        f"postgresql://fixture:{db_password}@127.0.0.1:56882/drone_test", autocommit=True
    ) as db:
        for i, label in [(tenant, "Fixture workspace"), (other, "Other organization")]:
            db.execute(
                "INSERT INTO tenants(id,name,settings,audit_head) VALUES(%s,%s,%s,%s)",
                (i, label, '{"currency":"EUR","units":"metric","language":"en","region":"fixture"}', ""),
            )
    # Generate registered identities with the real Portal password/MFA encoder; never log fixture material.
    fixture = {
        "tenant": tenant,
        "other": other,
        "admin": admin,
        "member": member,
        "password": password,
        "codes": [random_secret() for _ in range(8)],
        "drone": drone_origin,
        "portal": portal_origin,
    }
    seed = """
 const {db}=await import('./src/services/db.ts');
 const {encrypt,passwordHash,hash}=await import('./src/auth/crypto.ts');
 const f=JSON.parse(process.env.LOCAL_FIXTURE);
 for (const role of ['member','admin']){
 const id=f[role]; await db.query('INSERT INTO users(id,email,password_hash,role,mfa_secret) VALUES($1,$2,$3,$4,$5)',[id,role+'@example.test',passwordHash(f.password),role==='admin'?'administrator':'member',role==='admin'?encrypt('JBSWY3DPEHPK3PXP'):null]);
 await db.query('INSERT INTO identity_profiles(user_id,display_name,email_verified_at) VALUES($1,$2,now())',[id,'Synthetic '+role]);
 }
 for (const code of f.codes) await db.query('INSERT INTO mfa_recovery(user_id,code_hash) VALUES($1,$2)',[f.admin,hash(code)]);
 await db.query("INSERT INTO identity_product_access(user_id,product,role,status) VALUES($1,'drone','operator','active')",[f.member]);
 await db.query("INSERT INTO identity_drone_memberships VALUES($1,$2,'operator','Fixture workspace')",[f.member,f.tenant]);await db.end();
 """
    execute(
        ["node", "--import", "tsx", "--input-type=module", "-e", seed],
        portal_backend,
        portal_env | {"LOCAL_FIXTURE": json.dumps(fixture)},
    )
    report("Synthetic approved identities and two isolated workspaces ready")
    p = up(
        resources,
        "portal-api",
        [
            "node",
            "--max-old-space-size=150",
            "--input-type=module",
            "-e",
            "const {buildApp}=await import('./dist/src/app.js');const app=await buildApp({logging:false});await app.listen({host:'127.0.0.1',port:58300});",
        ],
        portal_backend,
        portal_env,
    )
    ready(58300, p)
    p = up(
        resources,
        "drone-api",
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "58400",
            "--no-access-log",
        ],
        drone,
        drone_env,
    )
    ready(58400, p)
    p = up(
        resources,
        "frontend-tls",
        ["node", scripts / "tls.mjs"],
        temp,
        {
            "STATIC": str(drone / "frontend/dist"),
            "ONESA_NATIVE_AUDIT_PATH": str(temp / "native-route-audit.json") if args.native_ui else "",
            "ONESA_NATIVE_CONTROL_KEY": native_control_key if args.native_ui == "ios" else "",
            "FIXTURE_PYTHON": sys.executable,
            "FIXTURE_EXPIRY_SCRIPT": str(scripts / "expire_native_session.py"),
            "DRONE_FIXTURE_DATABASE_URL": f"postgresql://fixture:{db_password}@127.0.0.1:56882/drone_test",
            "PORTAL_FIXTURE_DATABASE_URL": portal_env["DATABASE_URL"],
            "FIXTURE_MEMBER_ID": member,
            "FIXTURE_ADMIN_ID": admin,
            "FIXTURE_EXPECTED_ISSUER": cfg["issuer"],
            "PROXY_SHARED_KEY": proxy,
            "PUBLIC_ORIGIN": portal_origin,
            "BACKEND_URL": "http://127.0.0.1:58300",
            "ONESA_IDENTITY_CALLBACKS_JSON": json.dumps([cfg["clients"][0]["redirectUri"]]),
        },
    )
    ready(54843, p)
    ready(54844, p)
    report(
        "Running the Portal account component and API proxy, Drone web build, and both independent APIs over loopback TLS."
    )
    test_env = env | {"LOCAL_FIXTURE": json.dumps(fixture), "FIXTURE_CA": str(ca), "NATIVE": "1"}
    if args.native_ui:
        device = "ios-simulator-ui" if args.native_ui == "ios" else "android-emulator-ui"
        native_env = os.environ | {
            "FIXTURE_CA": str(ca),
            "EXPO_PUBLIC_DRONE_DEV_ORIGIN": drone_origin,
            "ONESA_FIXTURE_PASSWORD": password,
            "ONESA_FIXTURE_CONTROL": native_control_key,
            "ONESA_FIXTURE_FACTOR": fixture["codes"][0],
            "ONESA_FIXTURE_SECOND_FACTOR": fixture["codes"][1],
        }
        if args.native_ui == "ios":
            verify_fixture_control_denials(drone_origin, native_control_key, ca)
        result = subprocess.run([drone / "scripts" / device / "run.sh", "auth"], cwd=drone, env=native_env)
        audit_path = temp / "native-route-audit.json"
        audit = json.loads(audit_path.read_text()) if audit_path.is_file() else {}
        print("ONESA_NATIVE_ROUTE_AUDIT " + json.dumps(audit), flush=True)
        if result.returncode == 0 and args.native_ui == "ios":
            try:
                verify_native_audit(audit)
                verify_fixture_control_denials(drone_origin, native_control_key, ca, exhausted=True)
            except ValueError:
                sys.exit("Native acceptance requires four real starts, credential-free warm flows, scoped expiry and stable subjects.")
        sys.exit(result.returncode)
    if not args.protocol_only:
        browser_fixture = fixture | {"codes": fixture["codes"][4:]}
        browser_env = test_env | {
            "LOCAL_FIXTURE": json.dumps(browser_fixture),
            "PW_ROOT": str(drone / "frontend/node_modules/@playwright/test"),
        }
        if args.chromium:
            browser_env["CHROMIUM_PATH"] = str(args.chromium.resolve())
        browser_command = ["node"]
        if args.chromium:
            browser_command.append("--max-old-space-size=150")
        browser_check = subprocess.run([*browser_command, scripts / "journey.cjs"], env=browser_env, cwd=temp)
        if browser_check.returncode:
            sys.exit(1)
    protocol = subprocess.run([sys.executable, scripts / "protocol.py"], env=test_env, cwd=temp)
    sys.exit(0 if protocol.returncode == 0 else 1)

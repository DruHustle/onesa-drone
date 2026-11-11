import asyncio
import json
import secrets
import time
import logging
import resource
import sys
from concurrent.futures import ThreadPoolExecutor
import anyio.to_thread
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, Request, Response, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from sqlalchemy import select, func, text
from sqlalchemy.exc import SQLAlchemyError
from .monitoring import Hysteresis
from .config import Settings
from .db import Store
from .models import Tenant, User, Session, Aircraft, Mission, MissionEvent, Audit, Telemetry, Incident
from .security import digest, password_hash, password_valid, Limiter, DUMMY_HASH, HASH_PREFIX
from . import onesa_identity as identity_protocol
from .identity import (
    IdentityService,
    IdentitySession,
    public_account,
    TRANSACTION_COOKIE,
    TRANSACTION_COOKIE_PATH,
    TRANSACTION_SECONDS,
)
from .schemas import (
    Login,
    AircraftIn,
    AircraftCommand,
    MissionIn,
    Command,
    AssistantIn,
    FlightPlanIn,
    SettingsIn,
    UserIn,
    IncidentIn,
    IncidentUpdate,
    IdentityStart,
    WorkspaceSelection,
)
from .service import (
    j,
    aircraft_out,
    mission_out,
    owned,
    audit,
    idempotent,
    create_mission,
    command,
    advance,
    policy,
)
from autonomy.decision_engine.states import ACTIVE
from autonomy.mission_planning.dispatch import sequence_deliveries, MAX_DELIVERIES, MAX_AIRCRAFT
from integrations.onesa_ai.adapter import configured as ai_configured
from integrations.mavlink.plan import PlanError, preview_plan

log = logging.getLogger("onesa.drone")
REQUEST_BODY_SECONDS = 5
REQUEST_BODY_BYTES = 16384


def create_app(settings=None):
    cfg = settings or Settings()
    cfg.validate()
    store = Store(cfg.database_url, identity_enabled=cfg.identity_enabled)
    identity_service = IdentityService(cfg, store) if cfg.identity_enabled else None
    limiter = Limiter()
    worker_monitor = Hysteresis()
    wake = asyncio.Event()
    health = {
        "worker_last_tick": None,
        "worker_failures": 0,
        "started": time.time(),
        "requests": 0,
        "streams": 0,
        "last_error": None,
        "worker_idle": False,
    }

    def checkpoint_pass():
        with store.session() as db:
            tenants = list(db.scalars(select(Tenant.id).limit(1000)))
        active_count = 0
        for tenant in tenants:
            with store.transaction(tenant) as db:
                missions = list(
                    db.scalars(
                        select(Mission)
                        .where(Mission.tenant_id == tenant, Mission.state.in_(ACTIVE))
                        .limit(32)
                    )
                )
                active_count += len(missions)
                for m in missions:
                    advance(db, m, cfg.telemetry_limit)
        return active_count

    async def worker():
        while True:
            wake.clear()
            try:
                active_count = await asyncio.to_thread(checkpoint_pass)
                health["worker_idle"] = active_count == 0
                health["worker_last_tick"] = time.time()
                health["worker_failures"] = 0
                worker_monitor.observe(True)
            except SQLAlchemyError:
                health["worker_failures"] += 1
                changed = worker_monitor.observe(False)
                if changed:
                    log.error(j({"event": "simulation_storage_degraded", "mode": "simulation"}))
            if not health["worker_failures"] and health["worker_idle"]:
                # No keepalive polling that would pin a scale-to-zero database awake.
                store.engine.dispose()
                await wake.wait()
            else:
                await asyncio.sleep(
                    1 if not health["worker_failures"] else min(30, 2 ** min(health["worker_failures"], 5))
                )

    @asynccontextmanager
    async def lifespan(app):
        app.state.loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="drone-io")
        app.state.loop.set_default_executor(executor)
        anyio.to_thread.current_default_thread_limiter().total_tokens = 8
        if cfg.database_url.startswith("sqlite:"):
            store.initialize()
        else:
            store.verify()
        task = asyncio.create_task(worker()) if cfg.worker else None
        yield
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        store.engine.dispose()
        executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(
        title="Onesa Drone — simulation-only API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.store = store
    app.state.settings = cfg
    app.state.health = health
    app.state.identity = identity_service

    @app.exception_handler(identity_protocol.IdentityError)
    async def identity_error(request, error):
        return JSONResponse({"detail": error.message, "code": error.code}, error.status)

    @app.middleware("http")
    async def boundary(request, call_next):
        correlation = str(uuid4())
        request.state.correlation = correlation
        start = time.monotonic()
        try:
            limiter.check(request.client.host if request.client else "unknown", 300)
            size = request.headers.get("content-length", "0")
            if (
                not size.isascii()
                or not size.isdecimal()
                or len(size) > 20
                or int(size) > REQUEST_BODY_BYTES
            ):
                raise HTTPException(413, "Request body too large")
            # A total deadline bounds both stalled and continuously trickled
            # uploads. The same byte limit applies without Content-Length.
            chunks = []
            total = 0
            try:
                async with asyncio.timeout(REQUEST_BODY_SECONDS):
                    async for chunk in request.stream():
                        total += len(chunk)
                        if total > REQUEST_BODY_BYTES:
                            raise HTTPException(413, "Request body too large")
                        chunks.append(chunk)
            except TimeoutError:
                raise HTTPException(408, "Timed out while receiving request body") from None
            request._body = b"".join(chunks)
            response = await call_next(request)
        except HTTPException as e:
            response = JSONResponse({"detail": e.detail}, e.status_code)
        except SQLAlchemyError:
            response = JSONResponse(
                {"detail": "Operational storage unavailable; command was not acknowledged"}, 503
            )
        response.headers.update(
            {
                "X-Correlation-ID": correlation,
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
            }
        )
        health["requests"] += 1
        log.info(
            j(
                {
                    "event": "http",
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - start) * 1000),
                    "correlation_id": correlation,
                }
            )
        )
        return response

    def origin(request):
        if request.headers.get("origin") != cfg.origin:
            raise HTTPException(403, "Untrusted request origin")

    def auth(request: Request):
        token = request.cookies.get("drone_session", "")
        if identity_service:
            account = identity_service.authenticate(token)
            if request.method not in {"GET", "HEAD"}:
                origin(request)
                if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), account["csrf"]):
                    raise HTTPException(403, "CSRF validation failed")
            return account
        with store.session() as db:
            s = db.get(Session, digest(token)) if token else None
            u = db.get(User, s.user_id) if s and s.expires > time.time() else None
            if not u or not u.active:
                raise HTTPException(401, "Sign in required")
            if request.method not in {"GET", "HEAD"}:
                origin(request)
                if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), s.csrf):
                    raise HTTPException(403, "CSRF validation failed")
            return {
                "id": u.id,
                "tenant_id": u.tenant_id,
                "email": u.email,
                "role": u.role,
                "csrf": s.csrf,
                "expires": s.expires,
            }

    def workspace(a=Depends(auth)):
        if not a["tenant_id"]:
            raise HTTPException(409, "Choose a workspace to continue")
        return a

    def operator(a=Depends(workspace)):
        if a["role"] not in {"operator", "admin"}:
            raise HTTPException(403, "Operator role required")
        return a

    def admin(request: Request, a=Depends(workspace)):
        if a["role"] != "admin":
            raise HTTPException(403, "Administrator role required")
        if identity_service and request.method not in {"GET", "HEAD"}:
            identity_service.require_fresh(a["_identity"])
        return a

    def key(value: str = Header(alias="Idempotency-Key")):
        if not 8 <= len(value) <= 100 or not value.isascii():
            raise HTTPException(422, "A bounded idempotency key is required")
        return value

    def snapshot(db, tenant):
        aircraft = list(
            db.scalars(
                select(Aircraft).where(Aircraft.tenant_id == tenant).order_by(Aircraft.name).limit(200)
            )
        )
        missions = list(
            db.scalars(
                select(Mission)
                .where(Mission.tenant_id == tenant)
                .order_by(Mission.created_at.desc())
                .limit(100)
            )
        )
        counts = dict(
            db.execute(
                select(Mission.state, func.count()).where(Mission.tenant_id == tenant).group_by(Mission.state)
            ).all()
        )
        return {
            "aircraft": [aircraft_out(a) for a in aircraft],
            "missions": [mission_out(m) for m in missions],
            "counts": counts,
            "mode": "simulation",
            "at": time.time(),
            "truncated": {"aircraft": len(aircraft) == 200, "missions": len(missions) == 100},
        }

    @app.get("/api/v1/health")
    async def live():
        return {"status": "ok", "mode": "simulation"}

    @app.get("/api/v1/ready")
    def ready():
        try:
            with store.session() as db:
                db.execute(text("SELECT 1"))
            return {"status": "ready", "mode": "simulation"}
        except SQLAlchemyError:
            raise HTTPException(503, "Storage unavailable")

    @app.post("/api/v1/auth/login")
    def login(data: Login, request: Request, response: Response):
        origin(request)
        if identity_service:
            raise HTTPException(409, "Use your shared Onesa account to sign in")
        limiter.check("login:" + ((request.client.host if request.client else "") + data.email.lower()), 6)
        limiter.check("login-peer:" + (request.client.host if request.client else "unknown"), 12)
        limiter.check("login-account:" + digest(data.email.strip().lower()), 6)
        with store.transaction() as db:
            u = db.scalar(select(User).where(User.email == data.email.strip().lower()))
            encoded = u.password if u else DUMMY_HASH
            valid = password_valid(data.password, encoded)
            if not u or not valid or not u.active:
                raise HTTPException(401, "Invalid credentials")
            if not u.password.startswith(HASH_PREFIX):
                u.password = password_hash(data.password)
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(24)
            # Revoke stale sessions; bound retained sessions per account.
            for old in db.scalars(
                select(Session).where(Session.user_id == u.id).order_by(Session.expires.desc()).offset(4)
            ):
                db.delete(old)
            db.add(
                Session(
                    token_hash=digest(token),
                    user_id=u.id,
                    csrf=csrf,
                    expires=time.time() + cfg.session_seconds,
                )
            )
            response.set_cookie(
                "drone_session",
                token,
                httponly=True,
                secure=cfg.secure,
                samesite="strict",
                max_age=cfg.session_seconds,
                path="/",
            )
            return {"id": u.id, "email": u.email, "role": u.role, "tenant_id": u.tenant_id, "csrf": csrf}

    @app.get("/api/v1/auth/me")
    def me(a=Depends(auth)):
        return public_account(a)

    @app.get("/api/v1/auth/config")
    def auth_config():
        return {"shared_account": bool(identity_service)}

    @app.post("/api/v1/auth/identity/start")
    def identity_start(data: IdentityStart, request: Request, response: Response):
        origin(request)
        if not identity_service:
            raise HTTPException(404, "Shared sign-in is not configured")
        limiter.check("identity-login:" + (request.client.host if request.client else "unknown"), 12)
        previous = auth(request) if data.reauthenticate else None
        pending = identity_service.begin(previous, request.cookies.get("drone_session", ""))
        response.set_cookie(
            TRANSACTION_COOKIE,
            pending.browser,
            httponly=True,
            secure=cfg.secure,
            samesite="lax",
            max_age=TRANSACTION_SECONDS,
            path=TRANSACTION_COOKIE_PATH,
        )
        return {
            "authorization_url": identity_protocol.authorization_url(
                identity_service.config,
                pending.state,
                pending.nonce,
                pending.verifier,
                reauthenticate=data.reauthenticate,
            )
        }

    @app.get("/api/v1/auth/identity/callback")
    def identity_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        if not identity_service:
            raise HTTPException(404, "Shared sign-in is not configured")
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(TRANSACTION_COOKIE, path=TRANSACTION_COOKIE_PATH)
        central_token = None
        try:
            keys = list(request.query_params.keys())
            if (
                set(keys) - {"code", "state", "error", "error_description", "iss"}
                or any(len(request.query_params.getlist(key)) != 1 for key in keys)
                or len(str(request.url.query)) > 8192
                or request.query_params.get("iss", identity_service.config.issuer)
                != identity_service.config.issuer
            ):
                raise identity_protocol.IdentityError(
                    "identity_callback_invalid", "Sign-in has expired. Please start again"
                )
            pending = identity_service.consume(state, request.cookies.get(TRANSACTION_COOKIE, ""))
            if error:
                raise identity_protocol.IdentityError("identity_cancelled", "Sign-in was cancelled")
            central_token = identity_protocol.exchange_code(
                identity_service.config, code, identity_service.decrypt(pending.encrypted_verifier)
            )
            account = identity_protocol.validate_session(identity_service.config, central_token)
            if pending.subject and account.subject != pending.subject:
                raise identity_protocol.IdentityError(
                    "identity_account_changed", "Confirm the same Onesa account"
                )
            if pending.subject:
                identity_service.require_fresh(account)
            token, lifetime = identity_service.create_session(account, central_token, pending)
            old = request.cookies.get("drone_session")
            if old:
                with store.transaction() as db:
                    previous = db.get(IdentitySession, digest(old))
                    if previous:
                        db.delete(previous)
            response.set_cookie(
                "drone_session",
                token,
                httponly=True,
                secure=cfg.secure,
                samesite="strict",
                max_age=lifetime,
                path="/",
            )
        except identity_protocol.IdentityError as failure:
            if central_token:
                try:
                    identity_protocol.revoke_session(identity_service.config, central_token)
                except identity_protocol.IdentityError:
                    pass
            # Only fixed local error codes enter the URL. Upstream text, codes,
            # tokens, state and email addresses never enter the frontend URL.
            response.headers["location"] = "/?account_error=" + failure.code
        return response

    @app.get("/api/v1/auth/workspaces")
    def identity_workspaces(a=Depends(auth)):
        if not identity_service:
            raise HTTPException(404, "Shared sign-in is not configured")
        return {"workspaces": identity_service.workspaces(a["_identity"])}

    @app.post("/api/v1/auth/workspace")
    def select_workspace(data: WorkspaceSelection, request: Request, a=Depends(auth)):
        if not identity_service:
            raise HTTPException(404, "Shared sign-in is not configured")
        choices = {row["id"]: row for row in identity_service.workspaces(a["_identity"])}
        if data.tenant_id not in choices:
            raise HTTPException(403, "Workspace access is required")
        if a["global_admin"]:
            identity_service.require_fresh(a["_identity"])
        with store.transaction(data.tenant_id) as db:
            row = db.scalar(
                select(IdentitySession)
                .where(IdentitySession.token_hash == digest(request.cookies.get("drone_session", "")))
                .with_for_update()
            )
            if not row or row.expires <= time.time():
                raise HTTPException(401, "Sign in with your Onesa account")
            if (
                row.issuer != identity_service.config.issuer
                or row.subject != a["identity_subject"]
                or row.csrf != a["csrf"]
                or row.tenant_id != a["tenant_id"]
            ):
                raise HTTPException(409, "Your workspace changed; refresh before choosing again")
            previous = row.tenant_id
            row.tenant_id = data.tenant_id
            row.csrf = secrets.token_urlsafe(24)
            audit(
                db,
                data.tenant_id,
                a["id"],
                "identity.workspace_selected",
                {"previous_tenant_id": previous, "global_admin": a["global_admin"]},
                request.state.correlation,
            )
        return public_account(
            {**a, "tenant_id": row.tenant_id, "csrf": row.csrf, "role": choices[row.tenant_id]["role"]}
        )

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, response: Response):
        if identity_service:
            # Local logout is authorized by the existing browser-bound session,
            # Origin and CSRF. It must not depend on the issuer being reachable.
            origin(request)
            with store.transaction() as db:
                row = db.get(IdentitySession, digest(request.cookies.get("drone_session", "")))
                encrypted_token = row.encrypted_token if row else None
                if row:
                    if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), row.csrf):
                        raise HTTPException(403, "CSRF validation failed")
                    db.delete(row)
            response.delete_cookie("drone_session", path="/")
            central_signed_out = False
            if encrypted_token:
                try:
                    central_signed_out = identity_protocol.revoke_session(
                        identity_service.config, identity_service.decrypt(encrypted_token), all_sessions=True
                    )
                except identity_protocol.IdentityError:
                    pass
            return {
                "ok": central_signed_out,
                "shared_account": True,
                "local_signed_out": True,
                "central_signed_out": central_signed_out,
            }
        auth(request)
        with store.transaction() as db:
            s = db.get(Session, digest(request.cookies["drone_session"]))
            # Another logout or an administrator can revoke this session after
            # authentication but before this transaction acquires its lock.
            if s is not None:
                db.delete(s)
        response.delete_cookie("drone_session", path="/")
        return {"ok": True}

    @app.get("/api/v1/operations")
    def operations(a=Depends(workspace)):
        with store.session() as db:
            return snapshot(db, a["tenant_id"])

    @app.get("/api/v1/stream")
    async def stream(request: Request, a=Depends(workspace)):
        limiter.check("stream:" + a["id"], 12)
        if health["streams"] >= 32:
            raise HTTPException(429, "Telemetry connection capacity reached")
        health["streams"] += 1
        token_hash = digest(request.cookies["drone_session"])

        async def events():
            try:
                for frame in range(300):
                    if await request.is_disconnected():
                        return

                    def read_frame():
                        if identity_service:
                            # Existing streams also stop after account/membership
                            # revocation; each new request always validates live.
                            if frame % 10 == 0:
                                current = identity_service.authenticate(request.cookies["drone_session"])
                                if current["tenant_id"] != a["tenant_id"]:
                                    return None
                            with store.session() as db:
                                session = db.get(IdentitySession, token_hash)
                                if (
                                    not session
                                    or session.expires <= time.time()
                                    or session.tenant_id != a["tenant_id"]
                                ):
                                    return None
                                return snapshot(db, a["tenant_id"])
                        with store.session() as db:
                            s = db.get(Session, token_hash)
                            u = db.get(User, a["id"])
                            if (
                                not s
                                or s.expires <= time.time()
                                or not u
                                or not u.active
                                or u.tenant_id != a["tenant_id"]
                            ):
                                return None
                            return snapshot(db, a["tenant_id"])

                    data = await asyncio.to_thread(read_frame)
                    if data is None:
                        yield "event: expired\ndata: {}\n\n"
                        return
                    yield "event: telemetry\ndata: " + j(data) + "\n\n"
                    await asyncio.sleep(1)
            except identity_protocol.IdentityError as error:
                if error.status >= 500:
                    yield 'event: unavailable\ndata: {"reason":"identity"}\n\n'
                else:
                    yield "event: expired\ndata: {}\n\n"
            except HTTPException:
                yield "event: expired\ndata: {}\n\n"
            except SQLAlchemyError:
                yield 'event: unavailable\ndata: {"reason":"storage"}\n\n'
            finally:
                health["streams"] -= 1

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    @app.get("/api/v1/dispatch/preview")
    def dispatch_preview(a=Depends(workspace)):
        limiter.check("dispatch:" + a["tenant_id"] + ":" + a["id"], 6)
        with store.session() as db:
            missions = list(
                db.scalars(
                    select(Mission)
                    .where(
                        Mission.tenant_id == a["tenant_id"],
                        Mission.state == "requested",
                    )
                    .order_by(func.coalesce(Mission.scheduled_at, 0), Mission.created_at, Mission.id)
                    .limit(MAX_DELIVERIES + 1)
                )
            )
            aircraft = list(
                db.scalars(
                    select(Aircraft)
                    .where(
                        Aircraft.tenant_id == a["tenant_id"],
                        Aircraft.status == "available",
                        Aircraft.active_mission_id.is_(None),
                    )
                    .order_by(Aircraft.id)
                    .limit(MAX_AIRCRAFT + 1)
                )
            )
            result = sequence_deliveries(
                [mission_out(m) for m in missions[:MAX_DELIVERIES]],
                [aircraft_out(row) for row in aircraft[:MAX_AIRCRAFT]],
                time.time(),
                policy(db, a["tenant_id"]),
            )
            result["truncated"] = {
                "missions": len(missions) > MAX_DELIVERIES,
                "aircraft": len(aircraft) > MAX_AIRCRAFT,
            }
            return result

    @app.post("/api/v1/flight-plans/preview")
    def flight_plan_preview(data: FlightPlanIn, a=Depends(workspace)):
        limiter.check("flight-plan:" + a["tenant_id"] + ":" + a["id"], 6)
        with store.session() as db:
            constraints = policy(db, a["tenant_id"])
        try:
            return preview_plan(data.source, constraints)
        except PlanError as error:
            raise HTTPException(422, str(error)) from None

    @app.post("/api/v1/aircraft", status_code=201)
    def create_aircraft(data: AircraftIn, request: Request, a=Depends(operator), k=Depends(key)):
        with store.transaction(a["tenant_id"]) as db:

            def run():
                if (
                    db.scalar(
                        select(func.count()).select_from(Aircraft).where(Aircraft.tenant_id == a["tenant_id"])
                    )
                    >= 200
                ):
                    raise HTTPException(409, "Fleet limit reached")
                if db.scalar(
                    select(Aircraft).where(Aircraft.tenant_id == a["tenant_id"], Aircraft.name == data.name)
                ):
                    raise HTTPException(409, "Aircraft identifier already exists")
                row = Aircraft(tenant_id=a["tenant_id"], **data.model_dump())
                db.add(row)
                db.flush()
                audit(
                    db,
                    a["tenant_id"],
                    a["id"],
                    "aircraft.registered",
                    {"aircraft_id": row.id},
                    request.state.correlation,
                )
                return aircraft_out(row)

            return idempotent(db, a["tenant_id"], a["id"], k, {"path": "aircraft", **data.model_dump()}, run)

    @app.put("/api/v1/aircraft/{identifier}")
    def edit_aircraft(
        identifier: str,
        data: AircraftIn,
        request: Request,
        revision: int,
        a=Depends(operator),
        k=Depends(key),
    ):
        with store.transaction(a["tenant_id"]) as db:

            def run():
                row = owned(db, Aircraft, identifier, a["tenant_id"])
                if row.revision != revision or row.active_mission_id:
                    raise HTTPException(409, "Aircraft changed or is reserved")
                duplicate = db.scalar(
                    select(Aircraft).where(
                        Aircraft.tenant_id == a["tenant_id"],
                        Aircraft.name == data.name,
                        Aircraft.id != identifier,
                    )
                )
                if duplicate:
                    raise HTTPException(409, "Aircraft identifier already exists")
                for field, value in data.model_dump().items():
                    setattr(row, field, value)
                row.revision += 1
                audit(
                    db,
                    a["tenant_id"],
                    a["id"],
                    "aircraft.edited",
                    {"aircraft_id": identifier},
                    request.state.correlation,
                )
                return aircraft_out(row)

            return idempotent(
                db,
                a["tenant_id"],
                a["id"],
                k,
                {"path": identifier, "revision": revision, **data.model_dump()},
                run,
            )

    @app.post("/api/v1/aircraft/{identifier}/commands")
    def aircraft_command(
        identifier: str, data: AircraftCommand, request: Request, a=Depends(operator), k=Depends(key)
    ):
        with store.transaction(a["tenant_id"]) as db:

            def run():
                row = owned(db, Aircraft, identifier, a["tenant_id"])
                if row.revision != data.revision or row.active_mission_id:
                    raise HTTPException(409, "Aircraft changed or is reserved")
                if data.action == "decommission":
                    row.status = "decommissioned"
                elif data.action == "restore":
                    row.status = "available"
                elif data.action == "charge":
                    if row.status == "decommissioned":
                        raise HTTPException(409, "Aircraft decommissioned")
                    row.battery = 100
                elif data.action in {"inspect", "maintenance"}:
                    records = json.loads(row.maintenance)
                    records.append(
                        {
                            "at": time.time(),
                            "actor": a["id"],
                            "action": data.action,
                            "note": data.note,
                            "mode": "simulation",
                        }
                    )
                    row.maintenance = j(records[-100:])
                row.revision += 1
                audit(
                    db,
                    a["tenant_id"],
                    a["id"],
                    "aircraft." + data.action,
                    {"aircraft_id": identifier, "note": data.note},
                    request.state.correlation,
                )
                return aircraft_out(row)

            return idempotent(db, a["tenant_id"], a["id"], k, {"path": identifier, **data.model_dump()}, run)

    @app.post("/api/v1/missions", status_code=201)
    def new_mission(data: MissionIn, request: Request, a=Depends(operator), k=Depends(key)):
        with store.transaction(a["tenant_id"]) as db:
            return idempotent(
                db,
                a["tenant_id"],
                a["id"],
                k,
                {"path": "missions", **data.model_dump()},
                lambda: create_mission(db, a["tenant_id"], a["id"], data, request.state.correlation),
            )

    @app.post("/api/v1/missions/{identifier}/commands")
    def mission_command(
        identifier: str, data: Command, request: Request, a=Depends(operator), k=Depends(key)
    ):
        with store.transaction(a["tenant_id"]) as db:
            result = idempotent(
                db,
                a["tenant_id"],
                a["id"],
                k,
                {"path": identifier, **data.model_dump()},
                lambda: command(db, a["tenant_id"], a["id"], identifier, data, request.state.correlation),
            )
        app.state.loop.call_soon_threadsafe(wake.set)
        return result

    @app.get("/api/v1/missions/{identifier}/history")
    def history(identifier: str, a=Depends(workspace)):
        with store.session() as db:
            owned(db, Mission, identifier, a["tenant_id"])
            events = list(
                db.scalars(
                    select(MissionEvent)
                    .where(MissionEvent.mission_id == identifier, MissionEvent.tenant_id == a["tenant_id"])
                    .order_by(MissionEvent.at.desc(), MissionEvent.id.desc())
                    .limit(1001)
                )
            )
            telemetry = list(
                db.scalars(
                    select(Telemetry)
                    .where(Telemetry.mission_id == identifier, Telemetry.tenant_id == a["tenant_id"])
                    .order_by(Telemetry.seq.desc())
                    .limit(cfg.telemetry_limit)
                )
            )
            return {
                "events": [
                    {
                        "id": e.id,
                        "at": e.at,
                        "state": e.state,
                        "detail": json.loads(e.detail),
                        "correlation_id": e.correlation_id,
                    }
                    for e in reversed(events[:1000])
                ],
                "events_truncated": len(events) > 1000,
                "telemetry": [json.loads(t.payload) for t in reversed(telemetry)],
                "mode": "simulation",
                "retention_samples": cfg.telemetry_limit,
            }

    @app.get("/api/v1/tracking/{token}")
    def tracking(token: str):
        if len(token) != 43:
            raise HTTPException(404, "Tracking link not found or expired")
        with store.session() as db:
            m = db.scalar(
                select(Mission).where(
                    Mission.track_hash == digest(token), Mission.track_expires > time.time()
                )
            )
            if not m:
                raise HTTPException(404, "Tracking link not found or expired")
            return {
                "state": m.state,
                "delivered": m.delivered,
                "mode": "simulation",
                "progress_percent": json.loads(m.last_telemetry).get("progress_percent", 0),
                "expires": m.track_expires,
            }

    @app.get("/api/v1/scenarios")
    def scenarios(a=Depends(workspace)):
        return json.loads(
            (Path(__file__).resolve().parents[2] / "simulation/scenarios/catalog.json").read_text()
        )

    @app.get("/api/v1/settings")
    def settings_get(a=Depends(workspace)):
        with store.session() as db:
            return SettingsIn(**json.loads(db.get(Tenant, a["tenant_id"]).settings)).model_dump()

    @app.put("/api/v1/settings")
    def settings_put(data: SettingsIn, request: Request, a=Depends(admin)):
        with store.transaction(a["tenant_id"]) as db:
            db.get(Tenant, a["tenant_id"]).settings = j(data.model_dump())
            audit(
                db, a["tenant_id"], a["id"], "tenant.settings", data.model_dump(), request.state.correlation
            )
            return data

    @app.get("/api/v1/users")
    def users(a=Depends(admin)):
        with store.session() as db:
            return [
                {"id": u.id, "email": u.email, "role": u.role, "active": u.active}
                for u in db.scalars(select(User).where(User.tenant_id == a["tenant_id"]).limit(100))
            ]

    @app.post("/api/v1/users", status_code=201)
    def new_user(data: UserIn, request: Request, a=Depends(admin)):
        if identity_service:
            raise HTTPException(409, "Manage shared accounts and workspace access in Onesa administration")
        with store.transaction(a["tenant_id"]) as db:
            if db.scalar(select(User).where(User.email == data.email.lower().strip())):
                raise HTTPException(409, "Account cannot be created")
            u = User(
                tenant_id=a["tenant_id"],
                email=data.email.strip().lower(),
                password=password_hash(data.password),
                role=data.role,
            )
            db.add(u)
            db.flush()
            audit(
                db,
                a["tenant_id"],
                a["id"],
                "user.created",
                {"user_id": u.id, "role": u.role},
                request.state.correlation,
            )
            return {"id": u.id, "email": u.email, "role": u.role}

    @app.post("/api/v1/users/{identifier}/disable")
    def disable_user(identifier: str, request: Request, a=Depends(admin)):
        if identity_service:
            raise HTTPException(409, "Manage shared accounts and workspace access in Onesa administration")
        with store.transaction(a["tenant_id"]) as db:
            u = owned(db, User, identifier, a["tenant_id"])
            if u.id == a["id"]:
                raise HTTPException(409, "Cannot disable your own active account")
            u.active = False
            for s in db.scalars(select(Session).where(Session.user_id == u.id)):
                db.delete(s)
            audit(db, a["tenant_id"], a["id"], "user.disabled", {"user_id": u.id}, request.state.correlation)
            return {"ok": True}

    @app.get("/api/v1/security")
    def security(a=Depends(workspace)):
        with store.session() as db:
            audits = list(
                db.scalars(
                    select(Audit)
                    .where(Audit.tenant_id == a["tenant_id"])
                    .order_by(Audit.at.desc())
                    .limit(100)
                )
            )
            incidents = list(
                db.scalars(
                    select(Incident)
                    .where(Incident.tenant_id == a["tenant_id"])
                    .order_by(Incident.at.desc())
                    .limit(100)
                )
            )
            return {
                "controls": {
                    "simulation_only": True,
                    "physical_adapter": "disabled",
                    "authentication": "opaque server sessions / scrypt",
                    "csrf": "Origin + session-bound token",
                    "tenant_isolation": "server-enforced tenant predicates",
                    "transport": "HTTPS required for hosted use",
                    "audit": "transactional hash chain",
                    "ai_tools": "read-only advisory",
                },
                "audit": [
                    {
                        "id": r.id,
                        "at": r.at,
                        "action": r.action,
                        "correlation_id": r.correlation_id,
                        "digest": r.digest,
                    }
                    for r in audits
                ],
                "incidents": [
                    {"id": r.id, "title": r.title, "detail": r.detail, "state": r.state, "at": r.at}
                    for r in incidents
                ],
            }

    @app.post("/api/v1/incidents", status_code=201)
    def incident(data: IncidentIn, request: Request, a=Depends(operator)):
        with store.transaction(a["tenant_id"]) as db:
            row = Incident(tenant_id=a["tenant_id"], **data.model_dump())
            db.add(row)
            db.flush()
            audit(
                db,
                a["tenant_id"],
                a["id"],
                "incident.created",
                {"incident_id": row.id},
                request.state.correlation,
            )
            return {"id": row.id}

    @app.put("/api/v1/incidents/{identifier}")
    def incident_update(identifier: str, data: IncidentUpdate, request: Request, a=Depends(operator)):
        with store.transaction(a["tenant_id"]) as db:
            row = owned(db, Incident, identifier, a["tenant_id"])
            row.state = data.state
            audit(
                db,
                a["tenant_id"],
                a["id"],
                "incident." + data.state,
                {"incident_id": row.id},
                request.state.correlation,
            )
            return {"id": row.id, "state": row.state}

    @app.get("/api/v1/infrastructure")
    def infra(a=Depends(workspace)):
        with store.session() as db:
            db.execute(text("SELECT 1"))
        age = time.time() - health["worker_last_tick"] if health["worker_last_tick"] else None
        return {
            "mode": "simulation",
            "services": [
                {
                    "name": "Frontend",
                    "status": "client-reported",
                    "detail": "Browser connection; hosting receipt is a separate release gate",
                },
                {
                    "name": "Backend",
                    "status": "healthy",
                    "detail": f"Uptime {int(time.time() - health['started'])} s",
                },
                {"name": "Database", "status": "healthy", "detail": "Operational query succeeded"},
                {
                    "name": "Telemetry",
                    "status": "healthy",
                    "detail": f"{health['streams']} / 32 bounded SSE streams",
                },
                {
                    "name": "Simulation",
                    "status": (
                        "idle"
                        if health["worker_idle"]
                        else worker_monitor.status
                        if age is not None and age < 60
                        else "degraded"
                    )
                    if cfg.worker
                    else "disabled",
                    "detail": "Persisted checkpoints; single worker",
                },
                {
                    "name": "AI advisory",
                    "status": "configured-unverified" if ai_configured(cfg) else "not-configured",
                    "detail": "Read-only adapter; no aircraft tools",
                },
            ],
            "metrics": {
                "requests": health["requests"],
                "uptime_seconds": int(time.time() - health["started"]),
                "worker_failures": health["worker_failures"],
                "peak_rss_bytes": int(
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    * (1 if sys.platform == "darwin" else 1024)
                ),
                "cpu_seconds": round(
                    resource.getrusage(resource.RUSAGE_SELF).ru_utime
                    + resource.getrusage(resource.RUSAGE_SELF).ru_stime,
                    3,
                ),
            },
            "policy": {
                "failure_threshold": 3,
                "recovery_samples": 3,
                "retention_samples_per_mission": cfg.telemetry_limit,
                "max_active_per_tenant": 32,
            },
        }

    @app.post("/api/v1/assistant")
    async def assistant(data: AssistantIn, request: Request, a=Depends(workspace)):
        limiter.check("assistant:" + a["id"], 10)

        def read_context():
            with store.transaction(a["tenant_id"]) as db:
                context = snapshot(db, a["tenant_id"])
                audit(
                    db,
                    a["tenant_id"],
                    a["id"],
                    "assistant.read_context",
                    {
                        "aircraft_count": len(context["aircraft"]),
                        "mission_count": len(context["missions"]),
                        "question_hash": digest(data.question),
                    },
                    request.state.correlation,
                )
            return context

        context = await asyncio.to_thread(read_context)
        # No endpoint can receive a mission command from this adapter.
        from integrations.onesa_ai.adapter import advise

        return await advise(data.question, context, cfg, a["tenant_id"])

    return app


app = create_app()

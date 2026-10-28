import json
import time
import secrets
from sqlalchemy import select, delete
from fastapi import HTTPException
from .models import Aircraft, Mission, MissionEvent, Audit, Tenant, Receipt, Telemetry, Incident, uid
from .security import digest
from autonomy.mission_planning.planner import plan_route
from autonomy.safety_supervisor.supervisor import validate_launch, supervision
from autonomy.decision_engine.states import check_transition, ACTIVE, TERMINAL
from simulation.physics.kinematic import sample


def j(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def policy(db, tenant):
    settings = json.loads(db.get(Tenant, tenant).settings)
    return {
        "radius_m": settings.get("virtual_radius_m", 3000),
        "wind_mps": settings.get("wind_mps", 5),
        "reserve_percent": settings.get("reserve_percent", 25),
        "altitude_m": settings.get("altitude_m", 60),
    }


def aircraft_out(a):
    return {
        k: getattr(a, k)
        for k in (
            "id",
            "name",
            "model",
            "manufacturer",
            "category",
            "status",
            "battery",
            "capacity",
            "endurance",
            "firmware",
            "connectivity",
            "active_mission_id",
            "revision",
        )
    } | {"maintenance": json.loads(a.maintenance), "mode": "simulation", "specifications": "illustrative"}


def mission_out(m):
    return (
        {
            k: getattr(m, k)
            for k in (
                "id",
                "label",
                "aircraft_id",
                "package_weight",
                "package_kind",
                "state",
                "scenario",
                "tick",
                "revision",
                "created_at",
                "scheduled_at",
                "delivered",
                "outcome",
                "authorized_until",
            )
        }
        | {k: json.loads(getattr(m, k)) for k in ("origin", "destination", "plan", "last_telemetry")}
        | {"mode": "simulation"}
    )


def owned(db, model, identifier, tenant):
    row = db.scalar(select(model).where(model.id == identifier, model.tenant_id == tenant))
    if not row:
        raise HTTPException(404, "Record not found")
    return row


def audit(db, tenant, actor, action, detail, correlation):
    t = db.get(Tenant, tenant)
    at = time.time()
    encoded = j(detail)
    identifier = uid()
    value = digest(j([identifier, tenant, at, actor, action, encoded, correlation, t.audit_head]))
    db.add(
        Audit(
            id=identifier,
            tenant_id=tenant,
            at=at,
            actor=actor,
            action=action,
            detail=encoded,
            correlation_id=correlation,
            previous=t.audit_head,
            digest=value,
        )
    )
    t.audit_head = value


def transition(db, m, target, actor, correlation, detail):
    check_transition(m.state, target)
    prior = m.state
    m.state = target
    m.phase_tick = 0
    m.revision += 1
    db.add(
        MissionEvent(
            tenant_id=m.tenant_id,
            mission_id=m.id,
            state=target,
            actor=actor,
            correlation_id=correlation,
            detail=j({"from": prior, "reason": detail}),
        )
    )
    audit(db, m.tenant_id, actor, "mission." + target, {"mission_id": m.id, "reason": detail}, correlation)


def idempotent(db, tenant, actor, key, body, fn):
    request_hash = digest(j(body))
    row = db.get(Receipt, (tenant, key))
    if row:
        if row.actor != actor or row.request_hash != request_hash:
            raise HTTPException(409, "Idempotency key already used for a different command")
        return json.loads(row.response)
    response = fn()
    db.add(Receipt(tenant_id=tenant, key=key, actor=actor, request_hash=request_hash, response=j(response)))
    return response


def create_mission(db, tenant, actor, data, correlation):
    token = secrets.token_urlsafe(32)
    m = Mission(
        tenant_id=tenant,
        label=data.label,
        package_weight=data.package_weight,
        package_kind=data.package_kind,
        destination=j(data.destination.model_dump()),
        origin=j(data.origin.model_dump()),
        scenario=data.scenario,
        scheduled_at=data.scheduled_at,
        track_hash=digest(token),
        track_expires=time.time() + 7 * 86400,
    )
    db.add(m)
    db.flush()
    db.add(
        MissionEvent(
            tenant_id=tenant,
            mission_id=m.id,
            state="requested",
            actor=actor,
            correlation_id=correlation,
            detail=j({"reason": "Delivery and package registered", "mode": "simulation"}),
        )
    )
    audit(db, tenant, actor, "delivery.created", {"mission_id": m.id}, correlation)
    return {"mission": mission_out(m), "tracking_token": token}


def command(db, tenant, actor, identifier, c, correlation):
    m = owned(db, Mission, identifier, tenant)
    if m.revision != c.revision:
        raise HTTPException(409, "Mission changed; reload before retrying")
    a = owned(db, Aircraft, m.aircraft_id, tenant) if m.aircraft_id else None
    try:
        if c.action == "plan":
            if m.state != "requested":
                raise ValueError("Planning requires a requested mission")
            available = list(
                db.scalars(
                    select(Aircraft)
                    .where(
                        Aircraft.tenant_id == tenant,
                        Aircraft.status == "available",
                        Aircraft.active_mission_id.is_(None),
                    )
                    .order_by(Aircraft.id)
                )
            )
            if c.aircraft_id:
                available = [x for x in available if x.id == c.aircraft_id]
            plans = []
            reasons = []
            for candidate in available:
                try:
                    p = plan_route(
                        json.loads(m.origin),
                        json.loads(m.destination),
                        aircraft_out(candidate),
                        m.package_weight,
                        constraints=policy(db, tenant),
                    )
                    plans.append((p["energy_percent"], candidate.id, candidate, p))
                except ValueError as e:
                    reasons.append(str(e))
            if not plans:
                raise ValueError("; ".join(sorted(set(reasons))) or "No compatible aircraft available")
            _, _, a, p = min(plans, key=lambda x: (x[0], x[1]))
            a.active_mission_id = m.id
            a.revision += 1
            m.aircraft_id = a.id
            m.plan = j(p)
            transition(
                db,
                m,
                "planned",
                actor,
                correlation,
                "Lowest feasible estimated energy assignment; aircraft reserved",
            )
        elif c.action == "validate":
            if m.state != "planned":
                raise ValueError("Preflight requires a planned mission")
            issues = validate_launch(mission_out(m), aircraft_out(a), time.time(), policy(db, tenant))
            if issues:
                raise ValueError("; ".join(issues))
            transition(
                db,
                m,
                "validated",
                actor,
                correlation,
                "Explicit payload, route, geofence, battery and simulated identity rules passed",
            )
        elif c.action == "authorize":
            if m.state != "validated":
                raise ValueError("Authorization requires a validated mission")
            m.authorized_until = time.time() + 300
            transition(
                db,
                m,
                "authorized",
                actor,
                correlation,
                "Authenticated operator authorized simulation only; expires in five minutes",
            )
        elif c.action == "launch":
            active_count = db.scalar(
                select(__import__("sqlalchemy").func.count())
                .select_from(Mission)
                .where(Mission.tenant_id == tenant, Mission.state.in_(ACTIVE | {"paused"}))
            )
            if active_count >= 32:
                raise ValueError("Simulation capacity reached; complete or recover an active mission")
            if m.state != "authorized" or not m.authorized_until or m.authorized_until < time.time():
                raise ValueError("Fresh simulation authorization required")
            if a.active_mission_id != m.id:
                raise ValueError("Aircraft reservation mismatch")
            issues = validate_launch(mission_out(m), aircraft_out(a), time.time(), policy(db, tenant))
            if issues:
                raise ValueError("; ".join(issues))
            a.status = "in_mission"
            a.revision += 1
            transition(db, m, "taking_off", actor, correlation, "Simulation launched")
        elif c.action == "cancel":
            if m.state in TERMINAL:
                raise ValueError("Mission is terminal")
            if m.state in ACTIVE or m.state == "paused":
                m.outcome = "cancelled"
                if m.state not in {"returning", "landing"}:
                    transition(
                        db, m, "returning", actor, correlation, "Operator cancellation; virtual return"
                    )
                else:
                    m.revision += 1
                    audit(db, tenant, actor, "mission.cancel_requested", {"mission_id": m.id}, correlation)
            else:
                transition(db, m, "cancelled", actor, correlation, "Cancelled before simulation launch")
                release(a)
        elif c.action == "recover":
            if m.state != "paused":
                raise ValueError("Recovery requires a held simulation")
            m.outcome = "aborted"
            transition(db, m, "returning", actor, correlation, "Operator recovery to virtual home")
        elif c.action in {"reschedule", "replan"}:
            if m.state not in {"planned", "validated", "authorized"}:
                raise ValueError("Reschedule/replan requires an unlaunched plan")
            release(a)
            m.aircraft_id = None
            m.plan = "{}"
            m.authorized_until = None
            if c.action == "reschedule":
                if c.scheduled_at is None or c.scheduled_at <= time.time():
                    raise ValueError("Future schedule required")
                m.scheduled_at = c.scheduled_at
            transition(db, m, "requested", actor, correlation, "Previous plan and authorization invalidated")
        return mission_out(m)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def release(a):
    if a:
        a.active_mission_id = None
        a.status = "available"
        a.revision += 1


def advance(db, m, limit=600):
    if m.state not in ACTIVE:
        return
    a = owned(db, Aircraft, m.aircraft_id, m.tenant_id)
    m.tick += 1
    m.phase_tick += 1
    previous = json.loads(m.last_telemetry)
    if m.scenario == "low_battery" and m.tick == 10:
        a.battery = 19
    decision = supervision(m.scenario, m.tick, a.battery)
    correlation = "sim-" + m.id + "-" + str(m.tick)
    if decision and m.state not in {"returning", "landing"}:
        m.outcome = "aborted"
        transition(db, m, decision[0], "simulation-supervisor", correlation, decision[1])
        db.add(
            Incident(
                tenant_id=m.tenant_id,
                title="Simulation: " + m.scenario,
                detail=f"Mission {m.id}: {decision[1]}",
            )
        )
        if m.state == "paused":
            m.last_telemetry = j(
                {
                    **previous,
                    "seq": m.tick,
                    "flight_mode": "paused",
                    "mode": "simulation",
                    "gps_quality": "simulated-degraded"
                    if m.scenario == "gps_degradation"
                    else "simulated-nominal",
                    "motor_health": "simulated-fault"
                    if m.scenario == "aircraft_fault"
                    else "illustrative-nominal",
                }
            )
            return
    telemetry = sample(m, a, previous)
    a.battery = telemetry["battery_percent"]
    m.last_telemetry = j(telemetry)
    observation = Telemetry(tenant_id=m.tenant_id, mission_id=m.id, seq=m.tick, payload=j(telemetry))
    db.add(observation)
    db.execute(delete(Telemetry).where(Telemetry.mission_id == m.id, Telemetry.seq <= m.tick - limit))
    target = None
    if m.state == "taking_off" and m.phase_tick >= 3:
        target = "outbound"
    elif m.state == "outbound" and m.phase_tick >= telemetry["leg_ticks"]:
        target = "delivering"
    elif m.state == "delivering" and m.phase_tick >= 3:
        m.delivered = True
        target = "returning"
    elif m.state == "returning" and m.phase_tick >= telemetry["leg_ticks"]:
        target = "landing"
    elif m.state == "landing" and m.phase_tick >= 3:
        target = m.outcome or "completed"
        release(a)
        telemetry.update(
            progress_percent=100,
            altitude_m=0,
            flight_mode=target,
            payload_state="delivered" if m.delivered else "returned",
        )
        m.last_telemetry = j(telemetry)
    observation.payload = j(telemetry)
    if target:
        transition(db, m, target, "simulation-engine", correlation, "Deterministic simulation checkpoint")

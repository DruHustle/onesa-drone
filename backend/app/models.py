from sqlalchemy import Column, String, Float, Integer, Text, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import declarative_base
import time
from uuid import uuid4

Base = declarative_base()


def uid():
    return str(uuid4())


def now():
    return time.time()


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(String, primary_key=True, default=uid)
    name = Column(String, nullable=False)
    settings = Column(
        Text,
        nullable=False,
        default='{"currency":"EUR","units":"metric","language":"en","region":"illustrative-campus"}',
    )
    audit_head = Column(String, nullable=False, default="")


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=uid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="viewer")
    active = Column(Boolean, nullable=False, default=True)


class Session(Base):
    __tablename__ = "sessions"
    token_hash = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    csrf = Column(String, nullable=False)
    expires = Column(Float, nullable=False)


class Aircraft(Base):
    __tablename__ = "aircraft"
    id = Column(String, primary_key=True, default=uid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    model = Column(String, nullable=False)
    manufacturer = Column(String, nullable=False)
    category = Column(String, nullable=False)
    status = Column(String, nullable=False, default="available")
    battery = Column(Float, nullable=False, default=100)
    capacity = Column(Float, nullable=False)
    endurance = Column(Float, nullable=False)
    firmware = Column(String, nullable=False, default="sim-1.0")
    connectivity = Column(String, nullable=False, default="simulated")
    active_mission_id = Column(String, nullable=True)
    maintenance = Column(Text, nullable=False, default="[]")
    revision = Column(Integer, nullable=False, default=1)
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)


class Mission(Base):
    __tablename__ = "missions"
    id = Column(String, primary_key=True, default=uid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    aircraft_id = Column(String, ForeignKey("aircraft.id"))
    label = Column(String, nullable=False)
    package_weight = Column(Float, nullable=False)
    package_kind = Column(String, nullable=False)
    destination = Column(Text, nullable=False)
    origin = Column(Text, nullable=False)
    state = Column(String, nullable=False, default="requested", index=True)
    plan = Column(Text, nullable=False, default="{}")
    scenario = Column(String, nullable=False, default="nominal")
    tick = Column(Integer, nullable=False, default=0)
    phase_tick = Column(Integer, nullable=False, default=0)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(Float, nullable=False, default=now)
    scheduled_at = Column(Float, nullable=True)
    authorized_until = Column(Float, nullable=True)
    outcome = Column(String, nullable=True)
    delivered = Column(Boolean, nullable=False, default=False)
    last_telemetry = Column(Text, nullable=False, default="{}")
    track_hash = Column(String, nullable=False, index=True)
    track_expires = Column(Float, nullable=False)


class MissionEvent(Base):
    __tablename__ = "mission_events"
    id = Column(String, primary_key=True, default=uid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    mission_id = Column(String, ForeignKey("missions.id"), nullable=False, index=True)
    at = Column(Float, nullable=False, default=now)
    state = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    correlation_id = Column(String, nullable=False)
    detail = Column(Text, nullable=False)


class Audit(Base):
    __tablename__ = "audits"
    id = Column(String, primary_key=True, default=uid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    at = Column(Float, nullable=False)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    detail = Column(Text, nullable=False)
    correlation_id = Column(String, nullable=False)
    previous = Column(String, nullable=False)
    digest = Column(String, nullable=False)


class Receipt(Base):
    __tablename__ = "receipts"
    tenant_id = Column(String, ForeignKey("tenants.id"), primary_key=True)
    key = Column(String, primary_key=True)
    actor = Column(String, nullable=False)
    request_hash = Column(String, nullable=False)
    response = Column(Text, nullable=False)
    at = Column(Float, nullable=False, default=now)


class Telemetry(Base):
    __tablename__ = "telemetry"
    mission_id = Column(String, ForeignKey("missions.id"), primary_key=True)
    seq = Column(Integer, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    payload = Column(Text, nullable=False)


class Incident(Base):
    __tablename__ = "incidents"
    id = Column(String, primary_key=True, default=uid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    detail = Column(String, nullable=False)
    state = Column(String, nullable=False, default="open")
    at = Column(Float, nullable=False, default=now)


class SchemaRevision(Base):
    __tablename__ = "schema_revision"
    version = Column(String, primary_key=True)
    checksum = Column(String, nullable=False)

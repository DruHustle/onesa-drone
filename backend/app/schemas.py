from pydantic import BaseModel, Field, ConfigDict
from typing import Literal


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Login(Strict):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=200)


class Point(Strict):
    lat: float = Field(ge=-85, le=85)
    lon: float = Field(ge=-180, le=180)


class AircraftIn(Strict):
    name: str = Field(min_length=2, max_length=40, pattern=r"^[\w .-]+$")
    model: str = Field(min_length=1, max_length=80)
    manufacturer: str = Field(min_length=1, max_length=80)
    category: Literal["multirotor", "fixed-wing", "vtol"]
    capacity: float = Field(gt=0, le=100)
    endurance: float = Field(ge=5, le=240)


class AircraftCommand(Strict):
    action: Literal["inspect", "decommission", "restore", "charge", "maintenance"]
    note: str = Field(default="", max_length=500)
    revision: int = Field(ge=1)


class MissionIn(Strict):
    label: str = Field(min_length=2, max_length=100)
    package_weight: float = Field(gt=0, le=100)
    package_kind: Literal["standard", "medical", "fragile"] = "standard"
    origin: Point
    destination: Point
    scenario: Literal[
        "nominal",
        "low_battery",
        "communication_loss",
        "gps_degradation",
        "weather",
        "obstruction",
        "aircraft_fault",
    ] = "nominal"
    scheduled_at: float | None = Field(default=None, ge=0)


class Command(Strict):
    action: Literal["plan", "validate", "authorize", "launch", "cancel", "recover", "reschedule", "replan"]
    revision: int = Field(ge=1)
    aircraft_id: str | None = Field(default=None, max_length=40)
    scheduled_at: float | None = Field(default=None, ge=0)
    route_index: int = Field(default=0, ge=0, le=2)


class AssistantIn(Strict):
    question: str = Field(min_length=2, max_length=2000)


class FlightPlanIn(Strict):
    source: str = Field(min_length=1, max_length=12288)


class SettingsIn(Strict):
    virtual_radius_m: float = Field(default=3000, ge=100, le=3000)
    wind_mps: float = Field(default=5, ge=0, le=30)
    reserve_percent: float = Field(default=25, ge=25, le=80)
    altitude_m: float = Field(default=60, ge=10, le=100)
    currency: Literal["EUR", "USD", "ZAR", "NAD", "BWP", "ZMW", "GBP"]
    units: Literal["metric", "imperial"]
    language: Literal["en", "de"]
    region: str = Field(min_length=2, max_length=80)


class UserIn(Login):
    role: Literal["viewer", "operator", "admin"]
    password: str = Field(min_length=14, max_length=200)


class IncidentIn(Strict):
    title: str = Field(min_length=3, max_length=100)
    detail: str = Field(min_length=3, max_length=1000)


class IncidentUpdate(Strict):
    state: Literal["open", "investigating", "resolved"]

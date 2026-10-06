"""
Message schema. Every message on the bus is JSON matching one of these models.

Topics (MQTT-style; `+` = one level wildcard):
    site/{site_id}/env                          EnvReading      weather station -> gateway
    site/{site_id}/worker/{worker_id}/vitals    VitalsReading   wearable        -> gateway
    site/{site_id}/worker/{worker_id}/alert     AlertMessage    gateway         -> wearable/UI

Sensors may send null for any measurement they could not take. A real device
plugs in by publishing these JSON bodies on these topics; nothing else changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AlertLevel = Literal["NONE", "ADVISORY", "WARNING", "CRITICAL"]
Workload = Literal["light", "moderate", "heavy"]


def env_topic(site_id: str) -> str:
    return f"site/{site_id}/env"


def vitals_topic(site_id: str, worker_id: str) -> str:
    return f"site/{site_id}/worker/{worker_id}/vitals"


def alert_topic(site_id: str, worker_id: str) -> str:
    return f"site/{site_id}/worker/{worker_id}/alert"


class EnvReading(BaseModel):
    schema_: Literal["grandheck.env.v1"] = Field("grandheck.env.v1", alias="schema")
    site_id: str
    ts: datetime = Field(description="ISO 8601 with UTC offset")
    air_temp_c: float | None = None
    rh_pct: float | None = Field(None, ge=0, le=100)
    solar_wm2: float | None = Field(None, ge=0, description="global horizontal irradiance")
    wind_ms: float | None = Field(None, ge=0, description="wind speed at ~2 m")
    pressure_hpa: float | None = None

    model_config = {"populate_by_name": True}


class VitalsReading(BaseModel):
    schema_: Literal["grandheck.vitals.v1"] = Field("grandheck.vitals.v1", alias="schema")
    site_id: str
    worker_id: str
    ts: datetime
    hr_bpm: float | None = Field(None, gt=0, lt=250)
    skin_temp_c: float | None = None
    activity: float | None = Field(None, ge=0, le=1, description="accelerometer activity index, 0 = still, 1 = max")
    battery_pct: float | None = None

    model_config = {"populate_by_name": True}


class AlertMessage(BaseModel):
    schema_: Literal["grandheck.alert.v1"] = Field("grandheck.alert.v1", alias="schema")
    site_id: str
    worker_id: str
    ts: datetime
    level: AlertLevel
    kind: Literal["escalated", "renotify", "resolved", "signal_lost", "signal_restored"]
    ttc_min: float | None = Field(None, description="forecast minutes to critical strain")
    reasons: list[str] = []
    action: str = ""

    model_config = {"populate_by_name": True}


class WorkerProfile(BaseModel):
    worker_id: str
    name: str
    role: str
    age: int
    acclimatized: bool
    workload: Workload
    resting_hr: float | None = None   # if unknown, learned from the first minutes

    @property
    def age_band(self) -> str:
        if self.age < 30:
            return "18-29"
        if self.age < 45:
            return "30-44"
        return "45+"

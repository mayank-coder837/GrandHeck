"""
The site gateway: the whole Monitor -> Detect -> Assess -> Warn pipeline.

It subscribes to sensor topics on the bus, and once per minute `tick(now)`:
  1. DETECT   computes WBGT (+ heat index) from the latest weather reading
  2. ASSESS   updates each worker's core-temp estimate, PSI and exposure
  3. WARN     forecasts time-to-critical, steps the alert state machine,
              and publishes any alert to site/{site}/worker/{id}/alert

No network access, no cloud calls: this runs as-is on an offline gateway.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from .. import config as C
from ..bus import Bus
from ..schema import (AlertMessage, EnvReading, VitalsReading, WorkerProfile, alert_topic,
                      env_topic, vitals_topic)
from ..science import heat_index as hi
from ..science import limits
from ..science.ectemp import ECTempFilter
from ..science.psi import psi as compute_psi
from ..science.psi import psi_band
from ..science.wbgt import estimate_wbgt
from .alerts import AlertInputs, AlertStateMachine
from .forecaster import Forecast, ReasonInputs, combine_with_model, explain, forecast
from .model import RidgeModel, feature_vector, time_to_limit


def _trend_per_hour(points: list[tuple[float, float]], window_min: float) -> float | None:
    if len(points) < 3:
        return None
    now = points[-1][0]
    pts = [(t, v) for t, v in points if t > now - window_min]
    if len(pts) < 3:
        return None
    t = np.array([p[0] for p in pts]) - pts[-1][0]
    v = np.array([p[1] for p in pts])
    return float(np.polyfit(t, v, 1)[0] * 60.0)


@dataclass
class SiteState:
    env: EnvReading | None = None
    last_env_minute: float | None = None
    wbgt_c: float | None = None
    wbgt_method: str | None = None
    heat_index_c: float | None = None
    wbgt_history: deque = field(default_factory=lambda: deque(maxlen=C.HISTORY_MINUTES))

    def trend(self) -> float | None:
        return _trend_per_hour(list(self.wbgt_history), 30)

    def reported_trend(self) -> float | None:
        """Trend as shown to people: withheld until there is enough history to mean anything."""
        h = self.wbgt_history
        if not h or h[-1][0] - h[0][0] < C.WBGT_TREND_MIN_HISTORY_MIN:
            return None
        return self.trend()

    def snapshot(self, minute: float) -> dict[str, Any]:
        stale = self.last_env_minute is None or minute - self.last_env_minute >= C.DROPOUT_TIMEOUT_MIN
        e = self.env
        return {
            "air_temp_c": e.air_temp_c if e else None,
            "rh_pct": e.rh_pct if e else None,
            "solar_wm2": e.solar_wm2 if e else None,
            "wind_ms": e.wind_ms if e else None,
            "wbgt_c": self.wbgt_c,
            "wbgt_method": self.wbgt_method,
            "wbgt_trend_c_per_h": self.reported_trend(),
            "heat_index_c": self.heat_index_c,
            "heat_index_band": hi.heat_index_band(self.heat_index_c) if self.heat_index_c is not None else None,
            "categories": {w: limits.classify_environment(self.wbgt_c, w) for w in ("light", "moderate", "heavy")}
                          if self.wbgt_c is not None else {},
            "limits": {w: {"acclimatized": round(limits.wbgt_limit_c(w, True), 1),
                           "unacclimatized": round(limits.wbgt_limit_c(w, False), 1)}
                       for w in ("light", "moderate", "heavy")},
            "station_stale": stale,
        }


class WorkerState:
    """Everything the gateway knows about one worker."""

    def __init__(self, profile: WorkerProfile) -> None:
        self.p = profile
        self.filter = ECTempFilter()
        self.core_limit_c = (C.CORE_LIMIT_ACCLIMATIZED_C if profile.acclimatized
                             else C.CORE_LIMIT_UNACCLIMATIZED_C)
        self.workload = profile.workload     # current, inferred from activity once data arrive
        self._working_activity: deque = deque(maxlen=C.WORKLOAD_WINDOW_MIN)
        self.hr0 = profile.resting_hr
        self._early_hr: list[float] = []
        self.tc0 = C.ECT_CT0_C
        self.alerts = AlertStateMachine()
        self.last_seen_minute: float | None = None
        self.latest: VitalsReading | None = None
        self.hr: float | None = None
        self.psi: float | None = None
        self.skin_temp_c: float | None = None
        self.activity: float | None = None
        self.resting = False
        self._low_activity_run = 0
        self._recent_activity: deque = deque(maxlen=C.ACTIVITY_SMOOTHING_MIN)
        self.minutes_since_rest = 0
        self.exposure_total_min = 0
        self.exposure_continuous_min = 0
        self.observed_minutes = 0
        self.features = None                # last v2 feature vector (also used for training)
        self.forecast: Forecast | None = None
        self.reasons: list[str] = []
        self.history: deque = deque(maxlen=C.HISTORY_MINUTES)

    @property
    def wbgt_limit_c(self) -> float:
        return limits.wbgt_limit_c(self.workload, self.p.acclimatized)

    def _infer_workload(self, activity: float | None) -> None:
        """Workload from the accelerometer, so a worker switched to heavy work is noticed."""
        if activity is None or self.resting:
            return
        self._working_activity.append(activity)
        if len(self._working_activity) < C.WORKLOAD_WINDOW_MIN:
            return
        level = float(np.median(self._working_activity))
        self.workload = next(name for upper, name in C.ACTIVITY_WORKLOAD_BANDS if level < upper)

    @property
    def older(self) -> bool:
        return self.p.age_band == "45+"

    def _baseline_hr(self, hr: float) -> float:
        if self.hr0 is not None:
            return self.hr0
        self._early_hr.append(hr)          # no pre-shift value: learn from first readings
        if len(self._early_hr) >= 10:
            self.hr0 = min(self._early_hr)
        return min(self._early_hr)

    def _track_rest(self, activity: float | None) -> None:
        if activity is None:
            return
        self._recent_activity.append(activity)
        if float(np.median(self._recent_activity)) < C.ACTIVITY_REST_THRESHOLD:
            self._low_activity_run += 1
            if self._low_activity_run >= C.REST_MIN_DURATION_MIN:
                self.minutes_since_rest = 0
                self.exposure_continuous_min = 0
        else:
            self._low_activity_run = 0
            self.minutes_since_rest += 1
        self.resting = self._low_activity_run > 0

    def update(self, minute: float, vitals: VitalsReading | None, wbgt_c: float | None) -> None:
        observed = vitals is not None and vitals.hr_bpm is not None
        if observed:
            self.observed_minutes += 1
            self.filter.update(vitals.hr_bpm)
            self.hr = vitals.hr_bpm
            self.psi = compute_psi(self.filter.ct, self.hr, self.tc0, self._baseline_hr(self.hr))
            self.skin_temp_c = vitals.skin_temp_c
            self.activity = vitals.activity
            self.last_seen_minute = minute
            self._track_rest(vitals.activity)
            self._infer_workload(vitals.activity)
            working = not self.resting
            if working and wbgt_c is not None and wbgt_c > self.wbgt_limit_c:
                self.exposure_total_min += 1
                self.exposure_continuous_min += 1
        else:
            self.filter.predict(1)          # no data: carry the estimate, uncertainty grows

        self.history.append({
            "minute": minute,
            "hr": self.hr if observed else None,
            "core_c": round(self.filter.ct, 3) if observed else None,
            "psi": round(self.psi, 2) if (observed and self.psi is not None) else None,
            "wbgt_c": round(wbgt_c, 2) if wbgt_c is not None else None,
        })

    @property
    def signal_lost(self) -> bool:
        if self.last_seen_minute is None:
            return True
        return self.history[-1]["minute"] - self.last_seen_minute >= C.DROPOUT_TIMEOUT_MIN

    def hr_rise_15min(self) -> float | None:
        hrs = [h for h in self.history if h["hr"] is not None and h["minute"] > self.history[-1]["minute"] - 15]
        if len(hrs) < 5:
            return None
        return float(np.mean([h["hr"] for h in hrs[-3:]]) - np.mean([h["hr"] for h in hrs[:3]]))


class Gateway:
    def __init__(self, profiles: list[WorkerProfile], bus: Bus, site_id: str = C.SITE_ID,
                 lat: float = C.SITE_LAT_DEG, lon: float = C.SITE_LON_DEG,
                 forecaster: str = C.FORECASTER_VERSION, risk_z: float = C.V2_RISK_Z) -> None:
        self.site_id = site_id
        self.risk_z = risk_z
        self.model = RidgeModel.load() if forecaster == "v2" else None
        self.forecaster_version = "v2" if self.model is not None else "v1"
        self.bus = bus
        self.lat, self.lon = lat, lon
        self.site = SiteState()
        self.workers = {p.worker_id: WorkerState(p) for p in profiles}
        self._pending_vitals: dict[str, VitalsReading] = {}
        self._last_solar: tuple[float, float] | None = None     # (minute, W/m2) last good reading
        self._start: datetime | None = None
        self.rejected_messages = 0
        bus.subscribe(env_topic(site_id), self._on_env)
        bus.subscribe(vitals_topic(site_id, "+"), self._on_vitals)

    # --- ingest ------------------------------------------------------------------
    def _minute(self, ts: datetime) -> float:
        if self._start is None:
            self._start = ts
        return (ts - self._start).total_seconds() / 60.0

    def _on_env(self, topic: str, payload: dict) -> None:
        try:
            self.site.env = EnvReading.model_validate(payload)
            self.site.last_env_minute = self._minute(self.site.env.ts)
        except ValueError:
            self.rejected_messages += 1

    def _on_vitals(self, topic: str, payload: dict) -> None:
        try:
            v = VitalsReading.model_validate(payload)
        except ValueError:
            self.rejected_messages += 1
            return
        if v.worker_id in self.workers:
            self._pending_vitals[v.worker_id] = v

    # --- the per-minute pipeline -----------------------------------------------------
    def tick(self, now: datetime) -> dict[str, Any]:
        minute = self._minute(now)

        # DETECT
        e = self.site.env
        if e is not None and e.air_temp_c is not None and e.rh_pct is not None:
            solar, held = e.solar_wm2, False
            if solar is not None:
                self._last_solar = (minute, solar)
            elif self._last_solar and minute - self._last_solar[0] <= C.SOLAR_CARRY_FORWARD_MAX_MIN:
                solar, held = self._last_solar[1], True        # short pyranometer gap: hold last value
            w = estimate_wbgt(e.air_temp_c, e.rh_pct, e.wind_ms, solar, e.ts,
                              self.lat, self.lon, e.pressure_hpa)
            self.site.wbgt_c = w.wbgt_c
            self.site.wbgt_method = "liljegren_held_solar" if held else w.method
            self.site.heat_index_c = hi.heat_index_c(e.air_temp_c, e.rh_pct)
            self.site.wbgt_history.append((minute, w.wbgt_c))
        site = self.site.snapshot(minute)

        # ASSESS + WARN
        workers_out, alerts_out = [], []
        for wid, ws in self.workers.items():
            ws.update(minute, self._pending_vitals.pop(wid, None), self.site.wbgt_c)
            hist = list(ws.history)
            fc = forecast([h["minute"] for h in hist], [h["core_c"] for h in hist],
                          [h["psi"] for h in hist], ws.core_limit_c)
            ws.features = feature_vector(
                core_est=ws.filter.ct, core_slope_c_per_h=fc.core_slope_c_per_h, hr=ws.hr,
                hr_rise_15=ws.hr_rise_15min(), psi=ws.psi,
                wbgt_excess=None if self.site.wbgt_c is None else self.site.wbgt_c - ws.wbgt_limit_c,
                wbgt_trend_c_per_h=self.site.trend(), working=not ws.resting,
                minutes_since_rest=ws.minutes_since_rest, acclimatized=ws.p.acclimatized,
                workload=ws.workload, older=ws.older, data_minutes=ws.observed_minutes)
            if self.model is not None and not fc.stale and not ws.signal_lost:
                path = self.model.predict_path(ws.features, ws.filter.ct)
                risk = self.model.risk_path(path, self.risk_z)
                fc = combine_with_model(fc, path, ws.core_limit_c, time_to_limit(risk, ws.core_limit_c), risk,
                                        ttc_core_expected=time_to_limit(path, ws.core_limit_c))
            ws.forecast = fc
            at_threshold = (not ws.signal_lost) and (
                ws.filter.ct >= ws.core_limit_c or (ws.psi is not None and ws.psi >= C.PSI_CRITICAL))
            extra = C.ALERT_OLDER_WORKER_EXTRA_MIN if ws.older else 0.0
            events = ws.alerts.step(AlertInputs(
                ttc_min=fc.ttc_min, ttc_expected_min=fc.ttc_expected_min, at_threshold=at_threshold,
                exposure_minutes=ws.exposure_continuous_min, signal_lost=ws.signal_lost,
                extra_lead_min=extra))
            ws.reasons = explain(ReasonInputs(
                core_c=ws.filter.ct, core_slope_c_per_h=fc.core_slope_c_per_h,
                hr_rise_bpm_15min=ws.hr_rise_15min(), psi=ws.psi, wbgt_c=self.site.wbgt_c,
                wbgt_limit_c=ws.wbgt_limit_c, wbgt_trend_c_per_h=site["wbgt_trend_c_per_h"],
                minutes_since_rest=ws.minutes_since_rest, acclimatized=ws.p.acclimatized,
                older_worker=ws.older, workload=ws.workload))
            for ev in events:
                msg = self._alert_message(ws, ev, now)
                self.bus.publish(alert_topic(self.site_id, wid), msg.model_dump(mode="json", by_alias=True))
                alerts_out.append(msg.model_dump(mode="json", by_alias=True))
            workers_out.append(self._worker_snapshot(ws))

        return {"ts": now.isoformat(), "minute": minute, "site": site,
                "workers": workers_out, "alerts": alerts_out}

    def _alert_message(self, ws: WorkerState, ev, now: datetime) -> AlertMessage:
        if ev.kind == "signal_lost":
            reasons = [f"No wearable data for {C.DROPOUT_TIMEOUT_MIN}+ min - forecast frozen"]
            action = "Check on the worker in person and check the wearable (battery, fit)."
        elif ev.kind == "signal_restored":
            reasons, action = ["Wearable data restored"], ""
        elif ev.kind == "resolved":
            reasons = ["Forecast back below this tier"]
            action = C.ACTIONS.get(ev.level, "Continue normal work-rest schedule and hydration.")
        else:
            reasons, action = ws.reasons, C.ACTIONS[ev.level]
        return AlertMessage(site_id=self.site_id, worker_id=ws.p.worker_id, ts=now, level=ev.level,
                            kind=ev.kind, ttc_min=None if ev.ttc_min is None else round(ev.ttc_min, 1),
                            reasons=reasons, action=action)

    def _worker_snapshot(self, ws: WorkerState) -> dict[str, Any]:
        fc = ws.forecast
        h = ws.history[-1]
        return {
            "worker_id": ws.p.worker_id,
            "profile": ws.p.model_dump() | {"age_band": ws.p.age_band},
            "core_limit_c": ws.core_limit_c,
            "wbgt_limit_c": round(ws.wbgt_limit_c, 1),
            "workload_observed": ws.workload,
            "level": ws.alerts.level_name,
            "signal_lost": ws.signal_lost,
            "hr": ws.hr,
            "core_c": round(ws.filter.ct, 2),
            "core_std_c": round(ws.filter.std_c, 3),
            "psi": None if ws.psi is None else round(ws.psi, 1),
            "psi_band": None if ws.psi is None else psi_band(ws.psi),
            "skin_temp_c": ws.skin_temp_c,
            "activity": ws.activity,
            "resting": ws.resting,
            "minutes_since_rest": ws.minutes_since_rest,
            "exposure_total_min": ws.exposure_total_min,
            "exposure_continuous_min": ws.exposure_continuous_min,
            "ttc_min": None if fc.ttc_min is None else round(fc.ttc_min, 1),
            "ttc_expected_min": None if fc.ttc_expected_min is None else round(fc.ttc_expected_min, 1),
            "ttc_driver": fc.driver,
            "forecast_stale": fc.stale,
            "core_slope_c_per_h": None if fc.core_slope_c_per_h is None else round(fc.core_slope_c_per_h, 2),
            "forecast_line": [(round(k, 1), round(v, 3)) for k, v in fc.core_line],
            "risk_line": [(round(k, 1), round(v, 3)) for k, v in fc.risk_line],
            "reasons": ws.reasons,
            "point": h,
        }

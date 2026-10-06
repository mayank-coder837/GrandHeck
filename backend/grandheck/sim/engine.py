"""
Shift simulator. Each `step()` advances one simulated minute and returns the
messages the site's sensors would publish, plus the hidden ground truth.

Live scenario controls (callable mid-shift from the dashboard):
    set_weather("afternoon_build")  humid heat surge starting now
    trigger_spike(worker_id)        worker switches to heavy work with no breaks
    trigger_dropout(worker_id)      wearable goes silent; station loses its solar sensor
    send_to_rest(worker_id)         supervisor pulls the worker into shade
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from .. import config as C
from ..schema import WorkerProfile, env_topic, vitals_topic
from ..science.wbgt import solar_cos_zenith, wbgt_liljegren
from .crew import DEMO_CREW
from .physiology import SimWorker
from .weather import PROFILES, WeatherModel

SITE_TZ = timezone(timedelta(hours=C.SITE_UTC_OFFSET_H))
SIM_DATE = (2026, 7, 15)        # mid-summer


@dataclass
class SimStep:
    minute: int
    now: datetime
    messages: list[tuple[str, dict]]
    truth: dict[str, dict]                      # worker_id -> ground truth
    env_truth: dict = field(default_factory=dict)


class Simulator:
    def __init__(self, weather: str = "normal", seed: int = 7,
                 crew: list[WorkerProfile] | None = None,
                 start_hour: float = C.SIM_SHIFT_START_HOUR,
                 shift_length_min: int = C.SIM_SHIFT_LENGTH_MIN,
                 site_id: str = C.SITE_ID) -> None:
        self.rng = random.Random(seed)
        self.site_id = site_id
        self.weather_name = weather
        self.weather = WeatherModel(PROFILES[weather], random.Random(seed * 31 + 1))
        crew = crew or DEMO_CREW
        self.workers: dict[str, SimWorker] = {}
        for i, p in enumerate(crew):
            w = SimWorker(p, random.Random(f"{seed}-{p.worker_id}"), schedule_offset=(i * 7) % 20)
            self.workers[p.worker_id] = w
        # Profiles as the gateway would know them: resting HR from a pre-shift check.
        self.profiles = [p.model_copy(update={"resting_hr": self.workers[p.worker_id].resting_hr()})
                         for p in crew]
        h, m = int(start_hour), int(round((start_hour % 1) * 60))
        self.start = datetime(*SIM_DATE, h, m, tzinfo=SITE_TZ)
        self.minute = 0
        self.shift_length_min = shift_length_min
        self._dropout_until: dict[str, int] = {}
        self._solar_dropout_until = -1

    @property
    def now(self) -> datetime:
        return self.start + timedelta(minutes=self.minute)

    @property
    def finished(self) -> bool:
        return self.minute >= self.shift_length_min

    # --- live scenario controls ---------------------------------------------------
    def set_weather(self, name: str) -> None:
        self.weather_name = name
        profile = PROFILES[name]
        if profile.humid_surge_dp_c:
            hour = self.now.hour + self.now.minute / 60.0
            profile = replace(profile, surge_start_h=max(hour, profile.surge_start_h if self.minute == 0 else hour))
        self.weather.p = profile

    def trigger_spike(self, worker_id: str) -> None:
        w = self.workers[worker_id]
        w.workload = "heavy"
        w.no_rest = True

    def trigger_dropout(self, worker_id: str, minutes: int = 20, solar_minutes: int = 15) -> None:
        self._dropout_until[worker_id] = self.minute + minutes
        self._solar_dropout_until = self.minute + solar_minutes

    def send_to_rest(self, worker_id: str, minutes: int = 20) -> None:
        w = self.workers[worker_id]
        w.no_rest = False
        w.workload = w.profile.workload
        w.forced_rest_until = self.minute + minutes

    def start_directed_rest(self, worker_id: str, location: str = "shade") -> None:
        """Supervisor pulls the worker off work until end_directed_rest() is called."""
        w = self.workers[worker_id]
        w.no_rest = False
        w.workload = w.profile.workload
        w.directed_rest = True
        w.rest_location = location

    def end_directed_rest(self, worker_id: str) -> None:
        w = self.workers[worker_id]
        w.directed_rest = False
        w.forced_rest_until = -1

    # --- stepping -------------------------------------------------------------------
    def step(self) -> SimStep:
        now = self.now
        ts = now.isoformat()
        env = self.weather.sample(now)
        cza = solar_cos_zenith(now, self.weather.lat, self.weather.lon)
        wbgt_sun = wbgt_liljegren(env["air_temp_c"], env["rh_pct"], env["wind_ms"], env["solar_wm2"], cza).wbgt_c
        wbgt_shade = wbgt_liljegren(env["air_temp_c"], env["rh_pct"], env["wind_ms"], 0.0, cza).wbgt_c

        messages: list[tuple[str, dict]] = []
        env_msg = {"schema": "grandheck.env.v1", "site_id": self.site_id, "ts": ts, **env}
        if self.minute < self._solar_dropout_until:
            env_msg["solar_wm2"] = None
        messages.append((env_topic(self.site_id), env_msg))

        truth = {}
        minute_of_day = now.hour * 60 + now.minute
        for wid, w in self.workers.items():
            s = w.step(self.minute, minute_of_day, wbgt_sun, wbgt_shade)
            truth[wid] = s
            if self.minute < self._dropout_until.get(wid, -1):
                continue
            messages.append((vitals_topic(self.site_id, wid), {
                "schema": "grandheck.vitals.v1", "site_id": self.site_id, "worker_id": wid, "ts": ts,
                "hr_bpm": round(s["hr"], 1),
                "skin_temp_c": round(w.skin_temp(env["air_temp_c"]), 2),
                "activity": round(s["activity"], 3),
                "battery_pct": round(max(5.0, 100.0 - self.minute * 0.12), 1),
            }))

        self.minute += 1
        return SimStep(minute=self.minute - 1, now=now, messages=messages, truth=truth,
                       env_truth={**env, "wbgt_sun": wbgt_sun, "wbgt_shade": wbgt_shade})

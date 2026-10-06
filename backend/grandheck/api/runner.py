"""
Drives the live demo: advances the simulator, feeds its messages through the
bus to the gateway, logs results to SQLite, and hands each tick to listeners
(the WebSocket clients).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any, Awaitable, Callable

from .. import config as C
from ..bus import Bus
from ..pipeline.gateway import Gateway
from ..sim.engine import Simulator
from ..sim.weather import PROFILES

Listener = Callable[[dict[str, Any]], Awaitable[None]]
SPEEDS = [0.5, 1, 2, 5, 10, 20]
SNAPSHOT_TICKS = 600        # a whole shift, so the dashboard's shift overview survives a reload
SNAPSHOT_ALERTS = 1000
DB_PATH = Path(__file__).resolve().parents[3] / "data" / "grandheck.db"


class History:
    """Append-only SQLite log of alerts and per-minute worker state (the gateway's black box)."""

    def __init__(self, path: Path = DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS alerts (run_id TEXT, ts TEXT, worker_id TEXT, level TEXT,
                                               kind TEXT, ttc_min REAL, reasons TEXT, action TEXT);
            CREATE TABLE IF NOT EXISTS readings (run_id TEXT, ts TEXT, worker_id TEXT, hr REAL,
                                                 core_c REAL, psi REAL, wbgt_c REAL, level TEXT, ttc_min REAL);
        """)

    def log(self, run_id: str, tick: dict[str, Any]) -> None:
        self.db.executemany("INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?)", [
            (run_id, a["ts"], a["worker_id"], a["level"], a["kind"], a["ttc_min"],
             json.dumps(a["reasons"]), a["action"]) for a in tick["alerts"]])
        self.db.executemany("INSERT INTO readings VALUES (?,?,?,?,?,?,?,?,?)", [
            (run_id, tick["ts"], w["worker_id"], w["hr"], w["core_c"], w["psi"],
             tick["site"]["wbgt_c"], w["level"], w["ttc_min"]) for w in tick["workers"]])
        self.db.commit()


class DemoRunner:
    def __init__(self) -> None:
        self.listeners: set[Listener] = set()
        self.speed = C.SIM_DEFAULT_SPEED
        self.paused = False
        self.history = History()
        self.ticks: list[dict[str, Any]] = []
        self.alerts: list[dict[str, Any]] = []
        self.run_no = 0
        self.reset("normal", C.SIM_SHIFT_START_HOUR)
        self._task: asyncio.Task | None = None

    def reset(self, weather: str, start_hour: float, seed: int = 7) -> None:
        if weather not in PROFILES:
            raise ValueError(f"unknown weather profile {weather}")
        self.run_no += 1
        self.run_id = f"run{self.run_no}"
        length = int((C.SIM_SHIFT_START_HOUR * 60 + C.SIM_SHIFT_LENGTH_MIN) - start_hour * 60)
        warmup = C.SIM_WARMUP_MIN
        # Start the simulation a little before the shift clock and run that part silently,
        # so the estimator and forecaster are already calibrated when the dashboard opens.
        self.sim = Simulator(weather, seed=seed, start_hour=start_hour - warmup / 60.0,
                             shift_length_min=max(60, length) + warmup)
        self.bus = Bus()
        self.gateway = Gateway(self.sim.profiles, self.bus)
        self.ticks, self.alerts = [], []
        self.truth: list[dict[str, Any]] = []
        for _ in range(warmup):
            self.step_once()

    def state(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "weather": self.sim.weather_name,
            "weather_profiles": {k: v.name for k, v in PROFILES.items()},
            "speed": self.speed,
            "speeds": SPEEDS,
            "paused": self.paused,
            "finished": self.sim.finished,
            "forecaster": self.gateway.forecaster_version,
            "profiles": [p.model_dump() | {"age_band": p.age_band} for p in self.sim.profiles],
            "site": {"id": C.SITE_ID, "name": C.SITE_NAME, "lat": C.SITE_LAT_DEG, "lon": C.SITE_LON_DEG,
                     "utc_offset_h": C.SITE_UTC_OFFSET_H},
            "thresholds": {
                "core_acclimatized_c": C.CORE_LIMIT_ACCLIMATIZED_C,
                "core_unacclimatized_c": C.CORE_LIMIT_UNACCLIMATIZED_C,
                "psi_critical": C.PSI_CRITICAL,
                "ttc_advisory_min": C.ALERT_TTC_ADVISORY_MIN,
                "ttc_warning_min": C.ALERT_TTC_WARNING_MIN,
                "ttc_critical_min": C.ALERT_TTC_CRITICAL_MIN,
                "horizon_min": C.FORECAST_HORIZON_MIN,
            },
        }

    def step_once(self) -> dict[str, Any] | None:
        if self.sim.finished:
            return None
        st = self.sim.step()
        for topic, msg in st.messages:
            self.bus.publish(topic, msg)
        tick = self.gateway.tick(st.now)
        # Ground truth travels separately and is only shown in the UI's "truth" overlay.
        tick["truth"] = {w: {"core_c": round(t["tc_true"], 3), "working": t["working"]}
                         for w, t in st.truth.items()}
        self.ticks.append(tick)
        self.alerts.extend(tick["alerts"])
        self.history.log(self.run_id, tick)
        return tick

    async def _loop(self) -> None:
        while True:
            if not self.paused:
                tick = self.step_once()
                if tick is not None:
                    await self.broadcast({"type": "tick", "tick": tick})
            await asyncio.sleep(1.0 / self.speed)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def broadcast(self, msg: dict[str, Any]) -> None:
        for listener in list(self.listeners):
            try:
                await listener(msg)
            except Exception:
                self.listeners.discard(listener)

    def snapshot_message(self) -> dict[str, Any]:
        """Everything a newly connected client needs to draw the full picture."""
        return {"type": "init", "state": self.state(), "ticks": self.ticks[-SNAPSHOT_TICKS:],
                "alerts": self.alerts[-SNAPSHOT_ALERTS:]}

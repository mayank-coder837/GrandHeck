"""
Supervisor-directed rest in the live demo.

A directed rest moves the simulated worker off work (to a cooled shelter or shade).
It ends after DIRECTED_REST_MIN, unless the worker was sent to rest while over
their red line: then the rest is held until the dashboard shows they have
recovered, i.e. the ESTIMATED core temperature is back below the limit (with a
margin) AND the measured heart rate is near their resting rate. Release uses only
what the gateway can see, never the simulator's hidden truth.

Demo option: acknowledging a Critical alert sends that worker to rest a few
minutes later, as a supervisor would.

This is demo / simulation behaviour. The gateway's detection and alerting do not
depend on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .. import config as C
from ..pipeline.gateway import Gateway
from ..sim.engine import Simulator

LOCATIONS = ("cooled", "shade")


@dataclass
class DirectedRest:
    start_minute: int
    location: str
    until_clear: bool
    core_below_c: float
    hr_below_bpm: float


class RestPolicy:
    def __init__(self, location: str = C.DIRECTED_REST_LOCATION, auto_rest_on_ack: bool = C.AUTO_REST_ON_ACK) -> None:
        self.location = location
        self.auto_rest_on_ack = auto_rest_on_ack
        self.rests: dict[str, DirectedRest] = {}
        self.pending: dict[str, int] = {}       # worker_id -> minute the auto-rest starts

    def clear(self) -> None:
        self.rests.clear()
        self.pending.clear()

    def start(self, sim: Simulator, gw: Gateway, worker_id: str) -> DirectedRest:
        ws = gw.workers[worker_id]
        resting_hr = ws.hr0 if ws.hr0 is not None else (ws.p.resting_hr or 70.0)
        rest = DirectedRest(
            start_minute=sim.minute,
            location=self.location,
            until_clear=ws.filter.ct >= ws.core_limit_c + C.REST_UNTIL_CLEAR_TRIGGER_C,
            core_below_c=round(ws.core_limit_c - C.REST_RELEASE_CORE_MARGIN_C, 1),
            hr_below_bpm=round(resting_hr + C.REST_RELEASE_HR_MARGIN_BPM),
        )
        self.rests[worker_id] = rest
        self.pending.pop(worker_id, None)
        sim.start_directed_rest(worker_id, rest.location)
        return rest

    def acknowledge(self, sim: Simulator, worker_id: str, level: str) -> bool:
        """Returns True when an automatic rest was scheduled."""
        if not self.auto_rest_on_ack or level != "CRITICAL" or worker_id in self.rests:
            return False
        self.pending[worker_id] = sim.minute + C.AUTO_REST_DELAY_MIN
        return True

    def before_step(self, sim: Simulator, gw: Gateway) -> None:
        for wid, due in list(self.pending.items()):
            if sim.minute >= due:
                self.start(sim, gw, wid)

    def recovered(self, gw: Gateway, worker_id: str, rest: DirectedRest) -> bool:
        ws = gw.workers[worker_id]
        return (not ws.signal_lost and ws.hr is not None
                and ws.filter.ct < rest.core_below_c and ws.hr < rest.hr_below_bpm)

    def after_tick(self, sim: Simulator, gw: Gateway) -> None:
        for wid, rest in list(self.rests.items()):
            if sim.minute - rest.start_minute < C.DIRECTED_REST_MIN:
                continue
            if not rest.until_clear or self.recovered(gw, wid, rest):
                sim.end_directed_rest(wid)
                del self.rests[wid]

    def snapshot(self, minute: int) -> dict[str, Any]:
        return {
            "rest": {wid: {"location": r.location, "until_clear": r.until_clear, "core_below_c": r.core_below_c,
                           "hr_below_bpm": r.hr_below_bpm, "elapsed_min": minute - r.start_minute}
                     for wid, r in self.rests.items()},
            "pending_rest": {wid: due - minute for wid, due in self.pending.items()},
        }

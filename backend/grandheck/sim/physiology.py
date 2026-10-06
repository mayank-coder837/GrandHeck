"""
Ground-truth physiology for one simulated worker.

This is the hidden "real body" the detection pipeline never sees directly.
The pipeline only receives what a wearable would send: noisy heart rate,
skin temperature and an activity index.

Core temperature (Tc) model, one step per minute:
    dTc/dt = (Tc_eq(M) - Tc) / TAU                      settling toward a steady state
           + K * max(0, WBGT - tolerance) * fatigue     heat gain the body cannot shed
where M is metabolic rate, tolerance is the worker's personal compensable
WBGT (around the NIOSH REL/RAL for that work rate, plus individual
variation), and fatigue grows with continuous work since the last rest
(a stand-in for dehydration).

Heart rate is drawn around the population HR-to-core relationship that
ECTemp assumes, BUT with per-worker offset, per-worker slope, a workload
effect, cardiovascular drift with time since rest, short exertion bursts and
measurement noise. Those deviations are what make ECTemp's estimate imperfect,
as it is in the field (published RMSE ~0.3 C [BUL13]); the evaluation reports
the estimator error measured on these data.

Parameters here are simulation choices tuned for plausibility, not detection
thresholds, and are deliberately kept out of config.py.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..schema import WorkerProfile
from ..science.ectemp import hr_from_core
from ..science.limits import metabolic_rate_w, niosh_ral_c, niosh_rel_c

# --- simulation model parameters (not used by the detection pipeline) -------
TAU_MIN = 25.0              # core temperature settling time constant
K_HEAT_GAIN = 0.0022        # C/min per C of WBGT above tolerance
TC_EQ_BASE = 36.75          # steady core temp = base + slope * M  (compensable heat)
TC_EQ_PER_W = 0.0028
FATIGUE_GAIN = 0.6          # heat gain multiplier rises by up to 60% ...
FATIGUE_FULL_MIN = 120.0    # ... after 2 h of work without a rest
SELF_STOP_TC = 39.6         # a worker this hot stops working by themselves
HR_WORKLOAD_PER_W = 0.04    # bpm per W of metabolic rate relative to 300 W
REST_SHADE = True           # breaks are taken in shade
COOLED_SHELTER_WBGT_C = 22.0  # an air-conditioned rest shelter (simulation choice)
TAU_COOLED_MIN = 15.0       # in a cooled shelter the body sheds heat faster than in shade


@dataclass
class Traits:
    """Per-person variation, drawn once per worker."""
    tc_start: float
    tolerance_offset_c: float
    heat_gain_mult: float
    metabolic_mult: float
    hr_offset: float
    hr_slope: float
    hr_drift_per_h: float

    @staticmethod
    def draw(rng: random.Random) -> "Traits":
        return Traits(
            tc_start=rng.uniform(36.9, 37.2),
            tolerance_offset_c=rng.gauss(0.0, 1.0),
            heat_gain_mult=math.exp(rng.gauss(0.0, 0.2)),
            metabolic_mult=rng.uniform(0.9, 1.1),
            hr_offset=rng.gauss(0.0, 6.0),
            hr_slope=rng.uniform(0.85, 1.15),
            hr_drift_per_h=rng.uniform(0.0, 6.0),
        )


class SimWorker:
    def __init__(self, profile: WorkerProfile, rng: random.Random, schedule_offset: int = 0) -> None:
        self.profile = profile
        self.rng = rng
        self.t = Traits.draw(rng)
        self.tc = self.t.tc_start
        self.hr = self._hr_target(working=False, minutes_since_rest=0)
        self.workload = profile.workload
        self.schedule_offset = schedule_offset
        self.minutes_since_rest = 0
        self.no_rest = False            # "sudden spike" scenario
        self.forced_rest_until = -1     # minute index; set by "send to rest"
        self.directed_rest = False      # supervisor-directed rest, held until released
        self.rest_location = "shade"    # "shade" | "cooled" for directed rest
        self._burst = 0
        self.working = False

    def resting_hr(self) -> float:
        """What a pre-shift resting measurement would read (used as the PSI baseline)."""
        return round(self._hr_target(working=False, minutes_since_rest=0, tc=self.t.tc_start), 1)

    # --- schedule -------------------------------------------------------------
    def scheduled_to_work(self, minute_of_day: int, minute_index: int) -> bool:
        if self.directed_rest or minute_index < self.forced_rest_until:
            return False
        if self.tc >= SELF_STOP_TC:
            return False
        if self.no_rest:
            return True
        if 11 * 60 + 30 <= minute_of_day < 12 * 60:          # lunch break in shade
            return False
        return (minute_of_day + self.schedule_offset) % 60 < 45  # 45 min work / 15 min rest

    # --- physiology -------------------------------------------------------------
    def _metabolic(self, working: bool) -> float:
        if not working:
            return metabolic_rate_w("rest")
        return metabolic_rate_w(self.workload) * self.t.metabolic_mult

    def _tolerance(self, m: float) -> float:
        base = niosh_rel_c(m) if self.profile.acclimatized else niosh_ral_c(m)
        return base + self.t.tolerance_offset_c

    def _hr_target(self, working: bool, minutes_since_rest: int, tc: float | None = None) -> float:
        tc = self.tc if tc is None else tc
        ref = hr_from_core(37.1)
        hr = ref + self.t.hr_slope * (hr_from_core(tc) - ref) + self.t.hr_offset
        hr += HR_WORKLOAD_PER_W * (self._metabolic(working) - 300.0)
        hr += self.t.hr_drift_per_h * minutes_since_rest / 60.0
        return hr

    def step(self, minute_index: int, minute_of_day: int, wbgt_sun: float, wbgt_shade: float) -> dict:
        self.working = self.scheduled_to_work(minute_of_day, minute_index)
        if self.working:
            self.minutes_since_rest += 1
        else:
            self.minutes_since_rest = max(0, self.minutes_since_rest - 4)  # recovers 4x faster

        m = self._metabolic(self.working)
        if self.working or not REST_SHADE:
            env = wbgt_sun
        elif self.directed_rest and self.rest_location == "cooled":
            env = COOLED_SHELTER_WBGT_C
        else:
            env = wbgt_shade
        tc_eq = TC_EQ_BASE + TC_EQ_PER_W * m + (0.1 if not self.profile.acclimatized else 0.0)
        fatigue = 1.0 + FATIGUE_GAIN * min(1.0, self.minutes_since_rest / FATIGUE_FULL_MIN)
        gain = K_HEAT_GAIN * self.t.heat_gain_mult
        if not self.profile.acclimatized:
            gain *= 1.25
        if self.profile.age >= 45:
            gain *= 1.1
        excess = max(0.0, env - self._tolerance(m))
        tau = TAU_COOLED_MIN if (not self.working and self.directed_rest and self.rest_location == "cooled") else TAU_MIN
        self.tc += (tc_eq - self.tc) / tau + gain * excess * fatigue + self.rng.gauss(0, 0.005)

        # heart rate: lagged response toward target, AR noise, occasional exertion bursts
        target = self._hr_target(self.working, self.minutes_since_rest)
        if self.working and self._burst == 0 and self.rng.random() < 0.02:
            self._burst = self.rng.randint(1, 3)
        if self._burst > 0:
            target += 15.0
            self._burst -= 1
        self.hr += 0.5 * (target - self.hr) + self.rng.gauss(0, 3.0)

        activity = {"light": 0.35, "moderate": 0.55, "heavy": 0.8}[self.workload] if self.working else 0.05
        activity = min(1.0, max(0.0, activity + self.rng.gauss(0, 0.05)))
        return {
            "tc_true": self.tc,
            "hr": self.hr,
            "activity": activity,
            "working": self.working,
            "metabolic_w": m,
        }

    def skin_temp(self, air_temp_c: float) -> float:
        base = 33.5 + 0.12 * (air_temp_c - 30.0) + 0.3 * (self.tc - 37.0)
        if not self.working:
            base -= 0.8
        return min(38.5, max(31.0, base + self.rng.gauss(0, 0.15)))

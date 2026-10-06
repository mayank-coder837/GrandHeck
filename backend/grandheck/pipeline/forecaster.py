"""
Time-to-critical forecaster (v1: explainable trend extrapolation).

For each worker we fit a straight line to the last FORECAST_WINDOW_MIN minutes
of estimated core temperature, and separately of PSI, and extrapolate forward
to find when each would cross its danger threshold:

    ttc = (threshold - current) / slope        (only if slope is meaningfully > 0)

The earlier of the two crossings is reported, with which signal drove it.
Missing minutes (sensor dropout) are excluded from the fit rather than
filled in, and too few real points means "no forecast" (stale) - never a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .. import config as C


@dataclass
class Forecast:
    ttc_min: float | None           # None = no crossing within the horizon
    driver: str | None              # "core" | "psi" | None
    core_slope_c_per_h: float | None
    psi_slope_per_h: float | None
    stale: bool                     # not enough real data to forecast
    core_line: list[tuple[float, float]] = field(default_factory=list)  # (minutes ahead, core C)


def _slope_per_min(t: np.ndarray, y: np.ndarray) -> float:
    t = t - t.mean()
    denom = float((t * t).sum())
    return 0.0 if denom == 0.0 else float((t * (y - y.mean())).sum() / denom)


def _time_to(current: float, threshold: float, slope_per_min: float, min_slope_per_min: float) -> float | None:
    if current >= threshold:
        return 0.0
    if slope_per_min < min_slope_per_min:
        return None
    ttc = (threshold - current) / slope_per_min
    return ttc if ttc <= C.FORECAST_HORIZON_MIN else None


def forecast(times_min: list[float], core_c: list[float | None], psi: list[float | None],
             core_limit_c: float, psi_limit: float = C.PSI_CRITICAL) -> Forecast:
    """
    times_min: minute stamps (ascending) for the recent history.
    core_c / psi: values at those stamps; None where the sensor gave nothing.
    """
    if not times_min:
        return Forecast(None, None, None, None, stale=True)
    now = times_min[-1]
    window = [(t, c, p) for t, c, p in zip(times_min, core_c, psi)
              if t > now - C.FORECAST_WINDOW_MIN and c is not None and p is not None]
    if len(window) < C.FORECAST_MIN_POINTS:
        return Forecast(None, None, None, None, stale=True)

    t = np.array([w[0] for w in window], dtype=float)
    c = np.array([w[1] for w in window], dtype=float)
    p = np.array([w[2] for w in window], dtype=float)
    core_slope = _slope_per_min(t, c)
    psi_slope = _slope_per_min(t, p)

    ttc_core = _time_to(c[-1], core_limit_c, core_slope, C.FORECAST_MIN_CORE_SLOPE_C_PER_H / 60.0)
    ttc_psi = _time_to(p[-1], psi_limit, psi_slope, C.FORECAST_MIN_PSI_SLOPE_PER_H / 60.0)

    candidates = [(v, name) for v, name in ((ttc_core, "core"), (ttc_psi, "psi")) if v is not None]
    ttc, driver = min(candidates) if candidates else (None, None)

    # Projected core line for the chart: out to the crossing (plus a little), max 60 min.
    reach = min(60.0, (ttc_core + 10.0) if ttc_core is not None else 60.0)
    line = [(float(k), float(c[-1] + core_slope * k)) for k in range(0, int(reach) + 1, 5)]
    return Forecast(ttc, driver, core_slope * 60.0, psi_slope * 60.0, stale=False, core_line=line)


@dataclass
class ReasonInputs:
    core_c: float
    core_slope_c_per_h: float | None
    hr_rise_bpm_15min: float | None
    psi: float | None
    wbgt_c: float | None
    wbgt_limit_c: float
    wbgt_trend_c_per_h: float | None
    minutes_since_rest: int
    acclimatized: bool
    older_worker: bool
    workload: str


def explain(x: ReasonInputs) -> list[str]:
    """Rank contributing factors and return the top few as plain-language reasons."""
    s = C.REASON_SCALES
    factors: list[tuple[float, str]] = []
    if x.core_slope_c_per_h and x.core_slope_c_per_h > 0:
        factors.append((x.core_slope_c_per_h / s["core_trend_c_per_h"],
                        f"Core temp rising {x.core_slope_c_per_h:+.1f} °C/h (est. {x.core_c:.1f} °C)"))
    if x.hr_rise_bpm_15min and x.hr_rise_bpm_15min > 0:
        factors.append((x.hr_rise_bpm_15min / s["hr_rise_bpm_15min"],
                        f"Heart rate up {x.hr_rise_bpm_15min:.0f} bpm in 15 min"))
    if x.wbgt_c is not None and x.wbgt_c > x.wbgt_limit_c:
        excess = x.wbgt_c - x.wbgt_limit_c
        factors.append((excess / s["wbgt_excess_c"],
                        f"WBGT {x.wbgt_c:.1f} °C, {excess:.1f} °C over limit for {x.workload} work"))
    if x.wbgt_trend_c_per_h and x.wbgt_trend_c_per_h > 0:
        factors.append((x.wbgt_trend_c_per_h / s["wbgt_trend_c_per_h"],
                        f"WBGT rising {x.wbgt_trend_c_per_h:+.1f} °C/h"))
    if x.minutes_since_rest > 0:
        factors.append((x.minutes_since_rest / s["minutes_since_rest"],
                        f"{x.minutes_since_rest} min without rest"))
    if x.psi is not None and x.psi > 0:
        factors.append((x.psi / s["psi"], f"Strain index PSI {x.psi:.1f}"))
    if not x.acclimatized:
        factors.append((C.REASON_FIXED_SCORES["unacclimatized"], "Not yet acclimatized"))
    if x.older_worker:
        factors.append((C.REASON_FIXED_SCORES["older_worker"], "Age 45+ (higher risk)"))
    factors.sort(key=lambda f: f[0], reverse=True)
    return [text for score, text in factors if score >= C.REASON_MIN_SCORE][:C.REASON_MAX]

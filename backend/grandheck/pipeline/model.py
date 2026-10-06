"""
Forecaster v2: a small, explainable ridge regression on top of ECTemp.

Problem it fixes: ECTemp is deliberately slow-moving, so when core temperature
climbs fast (new worker, heavy work, WBGT far above their limit) the estimate
lags behind the real body. The heart-rate trend alone sees it late.

v2 predicts, for horizons of 0..60 min, how far the true core temperature will
be from the current ECTemp estimate, using only what the gateway can observe:
ECTemp state and trend, heart rate, PSI, WBGT relative to the worker's own
limit, workload, acclimatization, time since rest. Each horizon is one linear
model, so every prediction decomposes into per-feature contributions.

The model file is produced by `python -m eval.train_forecaster` on simulator
shifts that are never used for evaluation. In the field, the same training
script would be run on logged wearable + reference core temperature data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODEL_PATH = Path(__file__).with_name("forecaster_v2.json")
HORIZONS_MIN = [0, 10, 20, 30, 45, 60]

FEATURES = [
    "core_est",             # ECTemp estimate, C
    "core_slope_c_per_h",   # ECTemp 20-min trend
    "hr",                   # latest heart rate
    "hr_rise_15",           # bpm change over 15 min
    "psi",
    "wbgt_excess",          # WBGT minus this worker's NIOSH limit, C
    "wbgt_trend_c_per_h",
    "working",              # 1 = active, 0 = resting
    "minutes_since_rest_h", # hours
    "unacclimatized",
    "heavy",
    "light",
    "older",
    "data_minutes_h",       # how long the filter has been running (warm-up lag), hours, capped at 1
    "excess_x_working",
    "excess_x_unacclimatized",
    "heavy_x_working",
]

FEATURE_TEXT = {
    "core_est": "core temp estimate",
    "core_slope_c_per_h": "core temp trend",
    "hr": "heart rate",
    "hr_rise_15": "heart rate rising",
    "psi": "strain index (PSI)",
    "wbgt_excess": "WBGT above own limit",
    "wbgt_trend_c_per_h": "WBGT rising",
    "working": "working (not resting)",
    "minutes_since_rest_h": "time since rest",
    "unacclimatized": "not acclimatized",
    "heavy": "heavy workload",
    "light": "light workload",
    "older": "age 45+",
    "data_minutes_h": "early in monitoring",
    "excess_x_working": "working while WBGT over limit",
    "excess_x_unacclimatized": "not acclimatized and WBGT over limit",
    "heavy_x_working": "heavy work, no break",
}


def feature_vector(*, core_est: float, core_slope_c_per_h: float | None, hr: float | None,
                   hr_rise_15: float | None, psi: float | None, wbgt_excess: float | None,
                   wbgt_trend_c_per_h: float | None, working: bool, minutes_since_rest: int,
                   acclimatized: bool, workload: str, older: bool, data_minutes: float) -> np.ndarray:
    ex = wbgt_excess or 0.0
    w = 1.0 if working else 0.0
    un = 0.0 if acclimatized else 1.0
    heavy = 1.0 if workload == "heavy" else 0.0
    return np.array([
        core_est, core_slope_c_per_h or 0.0, hr or 0.0, hr_rise_15 or 0.0, psi or 0.0, ex,
        wbgt_trend_c_per_h or 0.0, w, minutes_since_rest / 60.0, un, heavy,
        1.0 if workload == "light" else 0.0, 1.0 if older else 0.0, min(data_minutes, 60.0) / 60.0,
        ex * w, ex * un, heavy * w,
    ], dtype=float)


def smooth_over_horizons(values: np.ndarray) -> np.ndarray:
    """
    Each horizon has its own linear model, so neighbouring predictions can
    disagree and the path zigzags. A least-squares quadratic through the six
    points keeps the overall shape (rising, falling, or one bend) and removes
    the zigzag.
    """
    h = np.array(HORIZONS_MIN, dtype=float)
    return np.polyval(np.polyfit(h, values, 2), h)


@dataclass
class RidgeModel:
    mean: np.ndarray
    scale: np.ndarray
    coef: np.ndarray            # (n_horizons, n_features)
    intercept: np.ndarray       # (n_horizons,)
    resid_std: np.ndarray | None = None   # validation error per horizon, C

    def predict_path(self, x: np.ndarray, core_est: float) -> list[tuple[int, float]]:
        z = (x - self.mean) / self.scale
        residual = smooth_over_horizons(self.coef @ z + self.intercept)
        return [(h, core_est + float(r)) for h, r in zip(HORIZONS_MIN, residual)]

    def risk_path(self, path: list[tuple[int, float]], z: float) -> list[tuple[int, float]]:
        """Upper edge of the forecast: mean + z x typical error at each horizon."""
        if self.resid_std is None:
            return path
        return [(h, v + z * float(s)) for (h, v), s in zip(path, self.resid_std)]

    def contributions(self, x: np.ndarray, horizon_index: int = 3) -> list[tuple[str, float]]:
        """Per-feature contribution (C) to the prediction at one horizon, largest positive first."""
        z = (x - self.mean) / self.scale
        parts = self.coef[horizon_index] * z
        return sorted(zip(FEATURES, parts.tolist()), key=lambda p: p[1], reverse=True)

    def save(self, path: Path = MODEL_PATH, meta: dict | None = None) -> None:
        path.write_text(json.dumps({
            "features": FEATURES, "horizons_min": HORIZONS_MIN, "mean": self.mean.tolist(),
            "scale": self.scale.tolist(), "coef": self.coef.tolist(),
            "intercept": self.intercept.tolist(),
            "resid_std": None if self.resid_std is None else self.resid_std.tolist(), "meta": meta or {},
        }, indent=1), encoding="utf-8")

    @staticmethod
    def load(path: Path = MODEL_PATH) -> "RidgeModel | None":
        if not path.exists():
            return None
        d = json.loads(path.read_text(encoding="utf-8"))
        if d["features"] != FEATURES or d["horizons_min"] != HORIZONS_MIN:
            return None          # stale model file from an older feature set
        return RidgeModel(np.array(d["mean"]), np.array(d["scale"]), np.array(d["coef"]),
                          np.array(d["intercept"]),
                          None if d.get("resid_std") is None else np.array(d["resid_std"]))


def fit_ridge(X: np.ndarray, Y: np.ndarray, alpha: float) -> RidgeModel:
    """Closed-form ridge on standardised features. Y has one column per horizon."""
    mean, scale = X.mean(axis=0), X.std(axis=0)
    scale[scale == 0] = 1.0
    Z = (X - mean) / scale
    y_mean = Y.mean(axis=0)
    A = Z.T @ Z + alpha * np.eye(Z.shape[1])
    coef = np.linalg.solve(A, Z.T @ (Y - y_mean)).T
    return RidgeModel(mean, scale, coef, y_mean)


def time_to_limit(path: list[tuple[int, float]], limit_c: float) -> float | None:
    """First crossing of the limit along the predicted path, linearly interpolated."""
    if path[0][1] >= limit_c:
        return 0.0
    for (h0, v0), (h1, v1) in zip(path, path[1:]):
        if v1 >= limit_c:
            return h0 + (limit_c - v0) / (v1 - v0) * (h1 - h0)
    return None

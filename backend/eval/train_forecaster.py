"""
Train forecaster v2 (pipeline/model.py) on simulated shifts.

    python -m eval.train_forecaster            (from backend/)

Seeds: training 0-299, validation 300-399. Evaluation uses seeds >= 1000, which
are never seen here. Features are exactly what the gateway computes live.

Target: the hidden true core temperature h minutes later, minus the current
ECTemp estimate, IF THE WORKER KEEPS WORKING AS THEY ARE NOW. A warning should
answer "what happens if nothing changes", not "what happens if they happen to
take their usual break". So for a worker who is working at the sample time we
copy their simulated body and run it forward with no breaks, under the same
weather; for a resting worker the target is their actual future.
"""

from __future__ import annotations

import copy
import sys
from multiprocessing import Pool

import numpy as np

from grandheck import config as C
from grandheck.bus import Bus
from grandheck.pipeline.gateway import Gateway
from grandheck.pipeline.model import HORIZONS_MIN, MODEL_PATH, fit_ridge

from .evaluate import apply_event, make_shift

TRAIN_SEEDS = range(0, 300)
VALID_SEEDS = range(300, 400)
SAMPLE_EVERY_MIN = 3


def _run(seed: int, on_minute) -> None:
    sim, events, _ = make_shift(seed)
    gw = Gateway(sim.profiles, Bus(), forecaster="v1")
    while not sim.finished:
        if sim.minute in events:
            apply_event(sim, events[sim.minute])
        st = sim.step()
        for topic, msg in st.messages:
            gw.bus.publish(topic, msg)
        gw.tick(st.now)
        on_minute(sim, gw, st)


def collect(seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Rows of (features, targets per horizon, current estimate, v1 straight-line path)."""
    # Pass 1: record the weather the shift will have (it does not depend on the workers).
    env: list[tuple[float, float]] = []
    _run(seed, lambda sim, gw, st: env.append((st.env_truth["wbgt_sun"], st.env_truth["wbgt_shade"])))
    horizon = HORIZONS_MIN[-1]
    X, Y, E, V1 = [], [], [], []

    # Pass 2: replay the identical shift; at sample minutes roll a copy of each worker forward.
    def sample(sim, gw, st) -> None:
        m = st.minute
        if m % SAMPLE_EVERY_MIN or m + horizon >= len(env):
            return
        for w, ws in gw.workers.items():
            fc = ws.forecast
            if fc is None or fc.stale or ws.signal_lost:
                continue
            body = copy.deepcopy(sim.workers[w])
            if st.truth[w]["working"]:
                body.no_rest = True
            future = {0: st.truth[w]["tc_true"]}
            minute_of_day = st.now.hour * 60 + st.now.minute
            for h in range(1, horizon + 1):
                sun, shade = env[m + h]
                future[h] = body.step(m + h, minute_of_day + h, sun, shade)["tc_true"]
            est = ws.filter.ct
            slope = (fc.core_slope_c_per_h or 0.0) / 60.0
            X.append(ws.features.copy())
            Y.append([future[h] - est for h in HORIZONS_MIN])
            E.append(est)
            V1.append([slope * h for h in HORIZONS_MIN])

    _run(seed, sample)
    return np.array(X), np.array(Y), np.array(E), np.array(V1)


def gather(seeds) -> tuple[np.ndarray, ...]:
    with Pool() as pool:
        parts = pool.map(collect, list(seeds), chunksize=4)
    return tuple(np.concatenate([p[i] for p in parts if len(p[0])]) for i in range(4))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    Xt, Yt, _, _ = gather(TRAIN_SEEDS)
    Xv, Yv, _, V1v = gather(VALID_SEEDS)
    model = fit_ridge(Xt, Yt, alpha=C.V2_RIDGE_ALPHA)

    Z = (Xv - model.mean) / model.scale
    pred = Z @ model.coef.T + model.intercept
    print(f"train rows {len(Xt)}, validation rows {len(Xv)}")
    print("Validation RMSE of predicted true core temp if work continues unchanged (C), by horizon:")
    print("  horizon   ECTemp only   v1 straight line   v2 model")
    metrics = {}
    for i, h in enumerate(HORIZONS_MIN):
        persist = float(np.sqrt(np.mean(Yv[:, i] ** 2)))
        v1 = float(np.sqrt(np.mean((Yv[:, i] - V1v[:, i]) ** 2)))
        v2 = float(np.sqrt(np.mean((Yv[:, i] - pred[:, i]) ** 2)))
        metrics[h] = {"ectemp_only": persist, "v1": v1, "v2": v2}
        print(f"  {h:>4} min   {persist:10.3f}   {v1:16.3f}   {v2:8.3f}")
    model.resid_std = np.sqrt(np.mean((Yv - pred) ** 2, axis=0))
    model.save(MODEL_PATH, meta={"train_seeds": [TRAIN_SEEDS.start, TRAIN_SEEDS.stop - 1],
                                 "alpha": C.V2_RIDGE_ALPHA, "validation_rmse_c": metrics})
    print(f"saved {MODEL_PATH}")


if __name__ == "__main__":
    main()

"""
Evaluation: our early-warning system vs. two naive alarms, over many simulated shifts.

    python run.py eval                 # 200 shifts (default)
    python run.py eval --shifts 50     # quicker

Systems compared (each produces, per worker and minute, "alarm on/off"):
  ours      gateway alert level >= WARNING (also reported: >= ADVISORY)
  wbgt      site WBGT >= a fixed threshold (NIOSH REL for moderate work), same for everyone
  hr        heart rate above 180 - age, sustained for HR_SUSTAINED_MINUTES (ACGIH criterion)

Ground truth: a worker's critical event is the first minute their HIDDEN simulated core
temperature reaches their ACGIH limit (38.5 C acclimatized / 38.0 C not). No system sees it.

Metrics (H = ACTIONABLE_WINDOW_MIN):
  detected     an alarm was active at some point in the H minutes before the event
  lead time    event time minus the onset of that alarm, capped at H
  missed       event with no alarm in that window
  false alarm  an alarm episode whose onset is not followed by that worker's event within H
               (episodes starting after the worker's event are not counted either way)

Shifts are randomised (crew, weather, live events) with seeds that were not used while
tuning the system (tuning used seeds < 1000).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from grandheck import config as C
from grandheck.bus import Bus
from grandheck.pipeline.gateway import Gateway
from grandheck.science.limits import niosh_rel_c
from grandheck.sim.crew import random_crew
from grandheck.sim.engine import Simulator
from grandheck.sim.weather import PROFILES

ACTIONABLE_WINDOW_MIN = 60
WBGT_FIXED_THRESHOLD_C = round(niosh_rel_c(C.METABOLIC_RATE_W["moderate"]), 1)
EVAL_SEED_BASE = 1000
OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "results"

SYSTEMS = {
    "ours": "GrandHeck v2 (Warning or higher)",
    "ours_advisory": "GrandHeck v2 (Advisory or higher)",
    "ours_v1": "GrandHeck v1, trend only (Warning or higher)",
    "wbgt": f"Naive WBGT alarm (≥ {WBGT_FIXED_THRESHOLD_C} °C)",
    "hr": "Naive heart-rate alarm (> 180 − age, sustained)",
}


def make_shift(seed: int) -> tuple[Simulator, dict[int, tuple[str, str]], str]:
    """A randomised shift: random crew, jittered weather, and random live events (minute -> event)."""
    rng = random.Random(seed)
    weather = rng.choice(list(PROFILES))
    crew = random_crew(rng)
    sim = Simulator(weather, seed=seed, crew=crew)
    sim.weather.p = replace(sim.weather.p, t_max_c=sim.weather.p.t_max_c + rng.uniform(-2.5, 2.5),
                            dew_point_c=sim.weather.p.dew_point_c + rng.uniform(-3, 3))
    events = {}
    if rng.random() < 0.35:
        events[rng.randint(60, 360)] = ("spike", rng.choice(crew).worker_id)
    if rng.random() < 0.25:
        events[rng.randint(60, 420)] = ("dropout", rng.choice(crew).worker_id)
    return sim, events, weather


def apply_event(sim: Simulator, event: tuple[str, str]) -> None:
    kind, wid = event
    sim.trigger_spike(wid) if kind == "spike" else sim.trigger_dropout(wid)


def simulate_shift(seed: int, risk_z: float = C.V2_RISK_Z) -> dict:
    """Run one randomised shift; return per-worker alarm series and ground-truth event time."""
    sim, events, weather = make_shift(seed)
    crew = sim.profiles
    bus = Bus()
    gw = Gateway(sim.profiles, bus, forecaster="v2", risk_z=risk_z)   # both gateways hear the same sensors
    gw_v1 = Gateway(sim.profiles, bus, forecaster="v1")
    if gw.forecaster_version != "v2":
        raise SystemExit("No v2 model file: run `python -m eval.train_forecaster` first.")
    ages = {p.worker_id: p.age for p in crew}
    series = {w: {k: [] for k in [*SYSTEMS, "tc", "est"]} for w in ages}
    hr_window = {w: [] for w in ages}

    while not sim.finished:
        if sim.minute in events:
            apply_event(sim, events[sim.minute])
        st = sim.step()
        for topic, msg in st.messages:
            bus.publish(topic, msg)
        tick = gw.tick(st.now)
        gw_v1.tick(st.now)
        wbgt = tick["site"]["wbgt_c"]
        seen_hr = {m["worker_id"]: m["hr_bpm"] for t, m in st.messages if t.endswith("/vitals")}
        for w, s in series.items():
            level = gw.workers[w].alerts.level
            s["ours"].append(level >= 2)
            s["ours_advisory"].append(level >= 1)
            s["ours_v1"].append(gw_v1.workers[w].alerts.level >= 2)
            s["wbgt"].append(wbgt is not None and wbgt >= WBGT_FIXED_THRESHOLD_C)
            hr = seen_hr.get(w)
            win = hr_window[w]
            win.append(hr)
            del win[:-C.HR_SUSTAINED_MINUTES]
            limit = C.HR_SUSTAINED_LIMIT_BASE - ages[w]
            s["hr"].append(len(win) == C.HR_SUSTAINED_MINUTES and all(h is not None and h > limit for h in win))
            s["tc"].append(st.truth[w]["tc_true"])
            s["est"].append(gw.workers[w].filter.ct if w in seen_hr else math.nan)

    out = {"seed": seed, "weather": weather, "workers": []}
    for w, s in series.items():
        limit = gw.workers[w].core_limit_c
        event = next((i for i, tc in enumerate(s["tc"]) if tc >= limit), None)
        tc, est = np.array(s["tc"]), np.array(s["est"])
        ok = ~np.isnan(est)
        out["workers"].append({
            "worker_id": w, "event": event,
            "alarms": {k: s[k] for k in SYSTEMS},
            "sq_err": float(np.sum((est[ok][30:] - tc[ok][30:]) ** 2)), "n_err": int(max(0, ok.sum() - 30)),
        })
    return out


def episodes(alarm: list[bool]) -> list[tuple[int, int]]:
    """(onset, end) minute pairs of contiguous alarm periods."""
    eps, start = [], None
    for i, on in enumerate(alarm):
        if on and start is None:
            start = i
        elif not on and start is not None:
            eps.append((start, i))
            start = None
    if start is not None:
        eps.append((start, len(alarm)))
    return eps


def score(shifts: list[dict]) -> dict:
    H = ACTIONABLE_WINDOW_MIN
    res = {k: {"leads": [], "missed": 0, "false_alarms": 0, "alarm_episodes": 0,
               "quiet_workers_alarmed": 0} for k in SYSTEMS}
    n_events = n_quiet = n_worker_shifts = 0
    sq, n = 0.0, 0
    for shift in shifts:
        for w in shift["workers"]:
            n_worker_shifts += 1
            sq += w["sq_err"]
            n += w["n_err"]
            ev = w["event"]
            if ev is None:
                n_quiet += 1
            else:
                n_events += 1
            for k in SYSTEMS:
                r = res[k]
                eps = episodes(w["alarms"][k])
                if ev is not None:
                    overlapping = [(a, b) for a, b in eps if a < ev and b > ev - H]
                    if overlapping:
                        onset = min(a for a, _ in overlapping)
                        r["leads"].append(min(H, ev - onset))
                    else:
                        r["missed"] += 1
                elif eps:
                    r["quiet_workers_alarmed"] += 1
                for a, _ in eps:
                    if ev is not None and a >= ev:
                        continue                      # after the event: neither true nor false
                    r["alarm_episodes"] += 1
                    if ev is None or ev - a > H:
                        r["false_alarms"] += 1

    summary = {"n_shifts": len(shifts), "n_worker_shifts": n_worker_shifts, "n_events": n_events,
               "actionable_window_min": H, "wbgt_fixed_threshold_c": WBGT_FIXED_THRESHOLD_C,
               "ectemp_rmse_c": math.sqrt(sq / n) if n else None, "systems": {}}
    for k, r in res.items():
        leads = r["leads"]
        summary["systems"][k] = {
            "label": SYSTEMS[k],
            "detected": len(leads),
            "detection_rate": len(leads) / n_events if n_events else None,
            "median_lead_min": statistics.median(leads) if leads else None,
            "mean_lead_min": statistics.mean(leads) if leads else None,
            "missed": r["missed"],
            "false_alarms": r["false_alarms"],
            "false_alarms_per_100_worker_shifts": 100.0 * r["false_alarms"] / n_worker_shifts,
            "precision": ((r["alarm_episodes"] - r["false_alarms"]) / r["alarm_episodes"]
                          if r["alarm_episodes"] else None),
            "quiet_workers_alarmed_pct": 100.0 * r["quiet_workers_alarmed"] / n_quiet if n_quiet else None,
        }
    return summary


def write_report(summary: dict) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def f(v, d=0, suffix=""):
        return "—" if v is None else f"{v:.{d}f}{suffix}"

    lines = [
        f"Simulated shifts: **{summary['n_shifts']}** · worker-shifts: **{summary['n_worker_shifts']}** · "
        f"critical events (true core temp reached limit): **{summary['n_events']}** · "
        f"actionable window: {summary['actionable_window_min']} min · "
        f"ECTemp core-temp error vs. truth: **{f(summary['ectemp_rmse_c'], 2)} °C RMSE**",
        "",
        "| System | Detected | Median lead (min) | Mean lead (min) | Missed | False alarms / 100 worker-shifts | Alarm precision | Workers never in danger who were alarmed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in summary["systems"].values():
        lines.append(
            f"| {s['label']} | {s['detected']} ({f(100 * s['detection_rate'] if s['detection_rate'] is not None else None, 0, '%')}) "
            f"| {f(s['median_lead_min'])} | {f(s['mean_lead_min'], 1)} | {s['missed']} "
            f"| {f(s['false_alarms_per_100_worker_shifts'], 1)} | {f(100 * s['precision'] if s['precision'] is not None else None, 0, '%')} "
            f"| {f(s['quiet_workers_alarmed_pct'], 0, '%')} |")
    table = "\n".join(lines)
    (OUT_DIR / "results.md").write_text(table + "\n", encoding="utf-8")
    plot(summary)
    return table


def plot(summary: dict) -> None:
    """One figure, three aligned panels: detection, lead time, false alarms. Ours highlighted."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order = ["ours", "ours_v1", "wbgt", "hr"]               # the Advisory variant stays in the table
    names = {"ours": "GrandHeck (v2)", "ours_v1": "GrandHeck v1\n(trend only)",
             "wbgt": f"Naive WBGT alarm\n(≥ {summary['wbgt_fixed_threshold_c']} °C)",
             "hr": "Naive heart-rate\nalarm (180 − age)"}
    colors = ["#0284c7", "#7dd3fc", "#9ca3af", "#9ca3af"]
    sysd = summary["systems"]
    panels = [
        ("Critical events warned in time", lambda r: 100 * r["detection_rate"], "{:.0f}%", "higher is better"),
        ("Median warning lead time", lambda r: r["median_lead_min"] or 0, "{:.0f} min",
         f"capped at {summary['actionable_window_min']} min"),
        ("False alarms per 100 worker-shifts", lambda r: r["false_alarms_per_100_worker_shifts"], "{:.0f}",
         "lower is better"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), dpi=150, sharey=True)
    y = list(range(len(order)))[::-1]
    for ax, (title, fn, fmt, note) in zip(axes, panels):
        vals = [fn(sysd[k]) for k in order]
        ax.barh(y, vals, color=colors, height=0.62)
        top = max(vals) * 1.25 or 1
        for yi, v in zip(y, vals):
            ax.text(v + top * 0.02, yi, fmt.format(v), va="center", fontsize=11, fontweight="bold")
        ax.set_xlim(0, top)
        ax.set_title(title, fontsize=12, fontweight="bold", loc="left")
        ax.set_xlabel(note, fontsize=9, color="#555")
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="x", labelsize=8)
    axes[0].set_yticks(y, [names[k] for k in order], fontsize=10)
    fig.suptitle(f"{summary['n_shifts']} simulated desert shifts · {summary['n_worker_shifts']} worker-shifts · "
                 f"{summary['n_events']} critical heat-strain events (held-out seeds)", fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "results_chart.png")


def tune(workers: int | None) -> None:
    from functools import partial
    seeds = list(range(300, 400))
    print("z     detected  median lead  false alarms/100  precision   (validation seeds 300-399)")
    for z in (0.0, 0.5, 1.0, 1.5, 2.0):
        with Pool(workers) as pool:
            r = score(pool.map(partial(simulate_shift, risk_z=z), seeds, chunksize=2))["systems"]["ours"]
        print(f"{z:<5} {100 * r['detection_rate']:6.0f}%  {r['median_lead_min'] or 0:9.0f}"
              f"  {r['false_alarms_per_100_worker_shifts']:14.1f}  {100 * (r['precision'] or 0):8.0f}%")


def main() -> None:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--shifts", type=int, default=200)
    ap.add_argument("--workers", type=int, default=None, help="parallel processes")
    ap.add_argument("--tuning", action="store_true",
                    help="sweep V2 risk z on validation seeds 300-399 instead (never the eval seeds)")
    args = ap.parse_args()
    t0 = time.time()
    if args.tuning:
        tune(args.workers)
        return
    seeds = [EVAL_SEED_BASE + i for i in range(args.shifts)]
    with Pool(args.workers) as pool:
        shifts = pool.map(simulate_shift, seeds, chunksize=2)
    summary = score(shifts)
    print(write_report(summary))
    print(f"\nwrote {OUT_DIR} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

"""Directed rest in the demo: cooled shelter, hold-until-recovered, auto-rest on acknowledge."""

from grandheck import config as C
from grandheck.api.rest_policy import RestPolicy
from grandheck.bus import Bus
from grandheck.pipeline.gateway import Gateway
from grandheck.pipeline.model import HORIZONS_MIN, smooth_over_horizons
from grandheck.sim.engine import Simulator

import numpy as np


def setup(weather="afternoon_build", start=11):
    sim = Simulator(weather, seed=7, start_hour=start, shift_length_min=360)
    gw = Gateway(sim.profiles, Bus())
    return sim, gw


def step(sim, gw, policy, n):
    for _ in range(n):
        policy.before_step(sim, gw)
        st = sim.step()
        for topic, msg in st.messages:
            gw.bus.publish(topic, msg)
        gw.tick(st.now)
        policy.after_tick(sim, gw)
        yield st


def test_cooled_shelter_cools_faster_than_shade():
    ends = {}
    for location in ("shade", "cooled"):
        sim, gw = setup()
        policy = RestPolicy(location=location)
        list(step(sim, gw, policy, 90))                  # get hot first
        policy.start(sim, gw, "W3")
        start = sim.workers["W3"].tc
        last = list(step(sim, gw, policy, 20))[-1]
        ends[location] = start - last.truth["W3"]["tc_true"]
    assert ends["cooled"] > ends["shade"]


def test_rest_is_held_until_estimate_and_heart_rate_recover():
    sim, gw = setup()
    policy = RestPolicy(location="shade")
    list(step(sim, gw, policy, 200))
    ws = gw.workers["W3"]
    assert ws.filter.ct >= ws.core_limit_c, "scenario should have W3 over the limit"
    rest = policy.start(sim, gw, "W3")
    assert rest.until_clear
    released_at = None
    for i, _ in enumerate(step(sim, gw, policy, 240)):
        if "W3" not in policy.rests:
            released_at = i
            break
        assert not sim.workers["W3"].working
    assert released_at is not None and released_at >= C.DIRECTED_REST_MIN - 1
    # at release, what the gateway sees has recovered
    assert ws.filter.ct < rest.core_below_c and ws.hr < rest.hr_below_bpm


def test_short_rest_when_below_the_line():
    sim, gw = setup(weather="normal", start=7)
    policy = RestPolicy()
    list(step(sim, gw, policy, 20))
    rest = policy.start(sim, gw, "W4")             # light-work surveyor, nowhere near the limit
    assert not rest.until_clear
    list(step(sim, gw, policy, C.DIRECTED_REST_MIN + 1))
    assert "W4" not in policy.rests


def test_acknowledging_critical_sends_worker_to_rest_after_delay():
    sim, gw = setup()
    policy = RestPolicy(auto_rest_on_ack=True)
    list(step(sim, gw, policy, 10))
    assert policy.acknowledge(sim, "W3", "CRITICAL")
    assert not policy.acknowledge(sim, "W1", "WARNING")
    list(step(sim, gw, policy, C.AUTO_REST_DELAY_MIN + 1))
    assert "W3" in policy.rests and sim.workers["W3"].directed_rest


def test_auto_rest_can_be_turned_off():
    sim, gw = setup()
    policy = RestPolicy(auto_rest_on_ack=False)
    assert not policy.acknowledge(sim, "W3", "CRITICAL")


def test_forecast_path_smoothing_removes_zigzag():
    zig = np.array([0.30, 0.10, 0.35, 0.12, 0.40, 0.20])
    smooth = smooth_over_horizons(zig)
    d = np.sign(np.diff(smooth))
    d = d[d != 0]
    assert int(np.sum(d[1:] != d[:-1])) <= 1           # at most one bend
    rising = np.array([0.0, 0.1, 0.2, 0.3, 0.45, 0.6])
    assert np.allclose(smooth_over_horizons(rising), rising, atol=0.02)   # real trends survive
    assert len(smooth) == len(HORIZONS_MIN)

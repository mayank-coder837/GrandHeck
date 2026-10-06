"""End-to-end checks of the gateway fed by the simulator over the bus."""

from grandheck import config as C
from grandheck.bus import Bus, topic_matches
from grandheck.pipeline.gateway import Gateway
from grandheck.sim.engine import Simulator


def setup(**kw):
    sim = Simulator(seed=3, **kw)
    bus = Bus()
    gw = Gateway(sim.profiles, bus)
    return sim, bus, gw


def advance(sim, bus, gw, minutes):
    out = []
    for _ in range(minutes):
        st = sim.step()
        for topic, msg in st.messages:
            bus.publish(topic, msg)
        out.append(gw.tick(st.now))
    return out


def test_topic_matching():
    assert topic_matches("site/+/worker/+/vitals", "site/a/worker/W1/vitals")
    assert topic_matches("site/#", "site/a/env")
    assert not topic_matches("site/+/env", "site/a/worker/W1/vitals")


def test_full_shift_runs_and_produces_snapshots():
    sim, bus, gw = setup(shift_length_min=120)
    ticks = advance(sim, bus, gw, 120)
    last = ticks[-1]
    assert len(last["workers"]) == len(sim.profiles)
    assert last["site"]["wbgt_method"] == "liljegren"
    assert all(36.0 < w["core_c"] < 40.0 for w in last["workers"])


def test_sensor_dropout_is_flagged_and_recovers():
    sim, bus, gw = setup()
    advance(sim, bus, gw, 30)
    sim.trigger_dropout("W2", minutes=10, solar_minutes=5)
    ticks = advance(sim, bus, gw, 10)
    w2 = next(w for w in ticks[-1]["workers"] if w["worker_id"] == "W2")
    assert w2["signal_lost"]
    alerts = [a for t in ticks for a in t["alerts"] if a["worker_id"] == "W2"]
    assert [a["kind"] for a in alerts].count("signal_lost") == 1
    # The weather station lost its solar sensor: the last good reading is held, and flagged.
    assert ticks[2]["site"]["wbgt_method"] == "liljegren_held_solar"
    assert ticks[-1]["site"]["wbgt_method"] == "liljegren"
    later = advance(sim, bus, gw, 2)
    w2 = next(w for w in later[-1]["workers"] if w["worker_id"] == "W2")
    assert not w2["signal_lost"]
    assert any(a["kind"] == "signal_restored" for t in later for a in t["alerts"])


def test_long_solar_outage_falls_back_to_shade_formula():
    sim, bus, gw = setup()
    advance(sim, bus, gw, 10)
    sim.trigger_dropout("W1", minutes=1, solar_minutes=C.SOLAR_CARRY_FORWARD_MAX_MIN + 5)
    ticks = advance(sim, bus, gw, C.SOLAR_CARRY_FORWARD_MAX_MIN + 3)
    assert ticks[0]["site"]["wbgt_method"] == "liljegren_held_solar"
    assert ticks[-1]["site"]["wbgt_method"] == "bom_shade"


def test_dropout_gap_is_not_filled_in_history():
    sim, bus, gw = setup()
    advance(sim, bus, gw, 20)
    sim.trigger_dropout("W1", minutes=5)
    advance(sim, bus, gw, 5)
    recent = list(gw.workers["W1"].history)[-5:]
    assert all(p["core_c"] is None and p["hr"] is None for p in recent)


def test_invalid_messages_are_rejected_not_crashing():
    sim, bus, gw = setup()
    bus.publish(f"site/{C.SITE_ID}/worker/W1/vitals", {"worker_id": "W1", "hr_bpm": "fast"})
    bus.publish(f"site/{C.SITE_ID}/env", {"air_temp_c": 40})
    assert gw.rejected_messages == 2
    advance(sim, bus, gw, 3)


def test_spike_drives_worker_to_warning_before_true_critical():
    """The headline behaviour on one worker: warned before ground truth crosses the limit."""
    sim, bus, gw = setup(start_hour=10, shift_length_min=300)
    sim.trigger_spike("W1")
    limit = gw.workers["W1"].core_limit_c
    warned_at = crossed_at = None
    for minute in range(300):
        st = sim.step()
        for topic, msg in st.messages:
            bus.publish(topic, msg)
        gw.tick(st.now)
        if warned_at is None and gw.workers["W1"].alerts.level >= 2:
            warned_at = minute
        if crossed_at is None and st.truth["W1"]["tc_true"] >= limit:
            crossed_at = minute
    assert crossed_at is not None and warned_at is not None
    assert warned_at < crossed_at

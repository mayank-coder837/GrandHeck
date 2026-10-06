from grandheck import config as C
from grandheck.pipeline.alerts import AlertInputs, AlertStateMachine, raw_level


def inp(ttc=None, at=False, exposure=0, lost=False, extra=0.0):
    return AlertInputs(ttc_min=ttc, at_threshold=at, exposure_minutes=exposure, signal_lost=lost,
                       extra_lead_min=extra)


def run(sm, inputs):
    events = []
    for x in inputs:
        events.extend(sm.step(x))
    return events


def test_raw_level_tiers():
    assert raw_level(inp(None)) == 0
    assert raw_level(inp(C.ALERT_TTC_ADVISORY_MIN - 1)) == 1
    assert raw_level(inp(C.ALERT_TTC_WARNING_MIN - 1)) == 2
    assert raw_level(inp(C.ALERT_TTC_CRITICAL_MIN - 1)) == 3
    assert raw_level(inp(None, at=True)) == 3
    assert raw_level(inp(None, exposure=C.ALERT_EXPOSURE_ADVISORY_MIN)) == 1


def test_older_worker_extra_lead_warns_earlier():
    ttc = C.ALERT_TTC_WARNING_MIN + 5
    assert raw_level(inp(ttc)) == 1
    assert raw_level(inp(ttc, extra=C.ALERT_OLDER_WORKER_EXTRA_MIN)) == 2


def test_escalation_needs_consecutive_ticks():
    sm = AlertStateMachine()
    events = run(sm, [inp(10)] * (C.ALERT_ESCALATE_TICKS - 1))
    assert events == [] and sm.level == 0
    events = sm.step(inp(10))
    assert [(e.level, e.kind) for e in events] == [("WARNING", "escalated")]


def test_reaching_threshold_escalates_immediately():
    sm = AlertStateMachine()
    events = sm.step(inp(0.0, at=True))
    assert sm.level_name == "CRITICAL" and events[0].kind == "escalated"


def test_one_minute_blip_does_not_alert():
    sm = AlertStateMachine()
    events = run(sm, [inp(None), inp(10), inp(None), inp(10), inp(None)])
    assert events == [] and sm.level == 0


def test_no_flapping_around_a_boundary():
    """TTC oscillating across the Warning line must not produce a stream of alerts."""
    sm = AlertStateMachine()
    run(sm, [inp(15)] * C.ALERT_ESCALATE_TICKS)          # now WARNING
    assert sm.level_name == "WARNING"
    wobble = [inp(C.ALERT_TTC_WARNING_MIN + d) for d in (3, -2, 4, -1, 5, -3) * 5]
    events = run(sm, wobble)
    assert [e for e in events if e.kind in ("escalated", "resolved")] == []
    assert sm.level_name == "WARNING"


def test_deescalation_needs_margin_and_time():
    sm = AlertStateMachine()
    run(sm, [inp(15)] * C.ALERT_ESCALATE_TICKS)
    # Comfortably clear, but not yet for long enough:
    events = run(sm, [inp(None)] * (C.ALERT_DEESCALATE_TICKS - 1))
    assert sm.level_name == "WARNING" and not any(e.kind == "resolved" for e in events)
    events = sm.step(inp(None))
    assert sm.level_name == "NONE" and events[0].kind == "resolved"


def test_deescalation_blocked_without_margin():
    sm = AlertStateMachine()
    run(sm, [inp(15)] * C.ALERT_ESCALATE_TICKS)
    just_over = C.ALERT_TTC_WARNING_MIN + C.ALERT_DEESCALATE_MARGIN_MIN - 1   # advisory, but within margin
    run(sm, [inp(just_over)] * 20)
    assert sm.level_name == "WARNING"


def test_renotify_is_rate_limited():
    sm = AlertStateMachine()
    events = run(sm, [inp(10)] * (C.ALERT_ESCALATE_TICKS + 3 * C.ALERT_RENOTIFY_MIN))
    kinds = [e.kind for e in events]
    assert kinds.count("escalated") == 1
    assert kinds.count("renotify") == 3


def test_advisory_is_not_renotified():
    sm = AlertStateMachine()
    events = run(sm, [inp(40)] * 60)
    assert [e.kind for e in events] == ["escalated"]


def test_signal_loss_announced_once_and_holds_level():
    sm = AlertStateMachine()
    run(sm, [inp(10)] * C.ALERT_ESCALATE_TICKS)
    events = run(sm, [inp(None, lost=True)] * 20)
    assert [e.kind for e in events] == ["signal_lost"]
    assert sm.level_name == "WARNING"            # never silently downgraded while blind
    events = sm.step(inp(10))
    assert events[0].kind == "signal_restored"

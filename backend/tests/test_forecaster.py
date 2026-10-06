import pytest

from grandheck import config as C
from grandheck.pipeline.forecaster import ReasonInputs, explain, forecast

T = list(range(0, 30))


def line(start, per_min, n=30):
    return [start + per_min * i for i in range(n)]


def test_linear_rise_gives_expected_time_to_critical():
    core = line(37.5, 0.01)                       # +0.6 C/h, now at 37.79
    fc = forecast(T, core, [1.0] * 30, core_limit_c=38.5)
    assert fc.driver == "core"
    assert fc.ttc_min == pytest.approx((38.5 - core[-1]) / 0.01, rel=1e-6)
    assert fc.core_slope_c_per_h == pytest.approx(0.6)


def test_flat_core_has_no_crossing():
    fc = forecast(T, [37.6] * 30, [2.0] * 30, core_limit_c=38.5)
    assert fc.ttc_min is None and not fc.stale


def test_cooling_has_no_crossing():
    fc = forecast(T, line(38.2, -0.01), [2.0] * 30, core_limit_c=38.5)
    assert fc.ttc_min is None


def test_already_over_limit_is_zero():
    fc = forecast(T, line(38.55, 0.0), [3.0] * 30, core_limit_c=38.5)
    assert fc.ttc_min == 0.0


def test_crossing_beyond_horizon_reported_as_none():
    fc = forecast(T, line(37.0, 0.002), [1.0] * 30, core_limit_c=38.5)   # ~700 min away
    assert fc.ttc_min is None


def test_psi_can_drive_the_forecast():
    fc = forecast(T, [37.6] * 30, line(5.0, 0.05), core_limit_c=38.5)    # PSI hits 7 first
    assert fc.driver == "psi"
    assert fc.ttc_min == pytest.approx((C.PSI_CRITICAL - (5.0 + 0.05 * 29)) / 0.05)


def test_too_few_points_is_stale_not_a_guess():
    fc = forecast(T[:5], line(37.5, 0.05, 5), [1.0] * 5, core_limit_c=38.5)
    assert fc.stale and fc.ttc_min is None


def test_missing_samples_are_excluded_not_filled():
    core = line(37.5, 0.01)
    gappy = [c if i % 3 == 0 else None for i, c in enumerate(core)]       # 1 in 3 present
    fc = forecast(T, gappy, [1.0] * 30, core_limit_c=38.5)
    assert fc.stale                                                      # too few real points in window


def test_forecast_line_starts_at_current_value():
    core = line(37.5, 0.01)
    fc = forecast(T, core, [1.0] * 30, core_limit_c=38.5)
    assert fc.core_line[0] == (0.0, pytest.approx(core[-1]))


def _inputs(**kw):
    base = dict(core_c=38.0, core_slope_c_per_h=0.2, hr_rise_bpm_15min=2.0, psi=2.0, wbgt_c=30.0,
                wbgt_limit_c=29.0, wbgt_trend_c_per_h=0.1, minutes_since_rest=10, acclimatized=True,
                older_worker=False, workload="heavy")
    base.update(kw)
    return ReasonInputs(**base)


def test_explain_ranks_dominant_factors_first():
    reasons = explain(_inputs(minutes_since_rest=90, core_slope_c_per_h=1.2, wbgt_c=31.0))
    assert len(reasons) <= C.REASON_MAX
    assert reasons[0].startswith("90 min without rest")
    assert any("Core temp rising" in r for r in reasons)


def test_explain_drops_weak_factors():
    reasons = explain(_inputs(core_slope_c_per_h=0.05, hr_rise_bpm_15min=1.0, psi=0.5, wbgt_c=28.0,
                              wbgt_trend_c_per_h=0.0, minutes_since_rest=5))
    assert reasons == []


def test_explain_mentions_profile_risk():
    reasons = explain(_inputs(acclimatized=False, older_worker=True, core_slope_c_per_h=0.0,
                              hr_rise_bpm_15min=0.0, psi=0.0, wbgt_c=28.0, minutes_since_rest=0))
    assert "Not yet acclimatized" in reasons and "Age 45+ (higher risk)" in reasons

import math
from datetime import datetime, timedelta, timezone

import pytest

from grandheck import config as C
from grandheck.science import heat_index, limits, psi
from grandheck.science.ectemp import ECTempFilter, hr_from_core
from grandheck.science.wbgt import (estimate_wbgt, solar_cos_zenith, wbgt_bom_shade,
                                    wbgt_liljegren)

GST = timezone(timedelta(hours=4))


def stull_wet_bulb(t_c: float, rh: float) -> float:
    """Independent psychrometric wet-bulb approximation (Stull 2011, J Appl Meteor Climatol)."""
    return (t_c * math.atan(0.151977 * (rh + 8.313659) ** 0.5) + math.atan(t_c + rh)
            - math.atan(rh - 1.676331) + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh)
            - 4.686035)


# --- WBGT -------------------------------------------------------------------

def test_bom_shade_matches_hand_calculation():
    e = 0.5 * 6.105 * math.exp(17.27 * 30 / (237.7 + 30))
    expected = 0.567 * 30 + 0.393 * e + 3.94
    assert wbgt_bom_shade(30, 50).wbgt_c == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("t,rh", [(25, 60), (35, 30), (42, 15)])
def test_wet_bulb_without_sun_agrees_with_stull(t, rh):
    # No sun and a good breeze: the natural wet bulb approaches the psychrometric wet bulb.
    r = wbgt_liljegren(t, rh, wind_ms=4.0, solar_wm2=0.0, cos_zenith=-0.5)
    assert r.t_nwb_c == pytest.approx(stull_wet_bulb(t, rh), abs=1.0)


def test_globe_near_air_temp_without_sun():
    r = wbgt_liljegren(35, 30, wind_ms=3.0, solar_wm2=0.0, cos_zenith=-0.5)
    assert abs(r.t_globe_c - 35) < 3.0


def test_sun_raises_globe_and_wbgt():
    shade = wbgt_liljegren(40, 20, 2.0, 0.0, 0.95)
    sun = wbgt_liljegren(40, 20, 2.0, 900.0, 0.95)
    assert sun.t_globe_c > shade.t_globe_c + 8
    assert sun.wbgt_c > shade.wbgt_c + 1


def test_humidity_raises_wbgt():
    dry = wbgt_liljegren(40, 15, 2.0, 900.0, 0.95)
    humid = wbgt_liljegren(40, 45, 2.0, 900.0, 0.95)
    assert humid.wbgt_c > dry.wbgt_c + 3


def test_wind_cools_globe_in_sun():
    calm = wbgt_liljegren(40, 20, 0.5, 900.0, 0.95)
    windy = wbgt_liljegren(40, 20, 5.0, 900.0, 0.95)
    assert windy.t_globe_c < calm.t_globe_c


def test_wbgt_is_iso_weighted_sum():
    r = wbgt_liljegren(38, 25, 2.0, 800.0, 0.9)
    assert r.wbgt_c == pytest.approx(0.7 * r.t_nwb_c + 0.2 * r.t_globe_c + 0.1 * 38)


def test_fallback_used_when_solar_missing():
    r = estimate_wbgt(40, 20, wind_ms=2.0, solar_wm2=None, when=datetime(2026, 7, 1, 12, tzinfo=GST))
    assert r.method == "bom_shade"


def test_solar_position_day_and_night():
    noon = solar_cos_zenith(datetime(2026, 6, 21, 12, 20, tzinfo=GST), 23.1, 53.8)
    midnight = solar_cos_zenith(datetime(2026, 6, 21, 0, 20, tzinfo=GST), 23.1, 53.8)
    assert noon > 0.99          # sun almost overhead near the Tropic of Cancer at solstice
    assert midnight < 0


# --- heat index ---------------------------------------------------------------

@pytest.mark.parametrize("t_f,rh,expected_f", [(90, 50, 95), (96, 65, 121), (100, 40, 109), (84, 70, 91)])
def test_heat_index_matches_nws_table(t_f, rh, expected_f):
    hi_c = heat_index.heat_index_c((t_f - 32) * 5 / 9, rh)
    assert hi_c * 9 / 5 + 32 == pytest.approx(expected_f, abs=1.5)


def test_heat_index_band():
    assert heat_index.heat_index_band(45.0) == "Danger"
    assert heat_index.heat_index_band(20.0) == "Below caution"


# --- NIOSH limits -----------------------------------------------------------------

def test_niosh_limits_formulas():
    assert limits.niosh_rel_c(300) == pytest.approx(56.7 - 11.5 * math.log10(300))
    assert limits.niosh_ral_c(300) == pytest.approx(59.9 - 14.1 * math.log10(300))


def test_limits_are_lower_for_heavier_work_and_unacclimatized():
    assert limits.wbgt_limit_c("heavy", True) < limits.wbgt_limit_c("light", True)
    assert limits.wbgt_limit_c("moderate", False) < limits.wbgt_limit_c("moderate", True)


def test_environment_classification():
    assert limits.classify_environment(20.0, "moderate") == "low"
    assert limits.classify_environment(26.5, "moderate") == "elevated"
    assert limits.classify_environment(31.0, "moderate") == "high"


# --- ECTemp ---------------------------------------------------------------------

def test_ectemp_steady_at_initial_value():
    f = ECTempFilter()
    for _ in range(60):
        f.update(hr_from_core(C.ECT_CT0_C))
    assert f.ct == pytest.approx(C.ECT_CT0_C, abs=0.01)


def test_ectemp_converges_to_core_implied_by_hr():
    f = ECTempFilter()
    target = 38.3
    for _ in range(240):
        f.update(hr_from_core(target))
    assert f.ct == pytest.approx(target, abs=0.05)


def test_ectemp_moves_slowly_on_hr_spike():
    # One very high HR sample must not make the estimate jump (process noise is small).
    f = ECTempFilter()
    for _ in range(30):
        f.update(hr_from_core(37.1))
    before = f.ct
    f.update(190)
    # 190 bpm alone would imply > 41 C; one sample should move the estimate only ~0.1 C.
    assert 0 < f.ct - before < 0.15


def test_ectemp_higher_hr_gives_higher_core():
    lo, hi = ECTempFilter(), ECTempFilter()
    for _ in range(60):
        lo.update(100)
        hi.update(140)
    assert hi.ct > lo.ct


def test_ectemp_predict_only_grows_uncertainty():
    f = ECTempFilter()
    for _ in range(30):
        f.update(100)
    v = f.v
    f.predict(5)
    assert f.v > v


def test_ectemp_observation_model_values():
    # Spot values of the published quadratic: ~83 bpm at 37.1 C, ~137 bpm at 38.5 C.
    assert hr_from_core(37.1) == pytest.approx(83.3, abs=0.5)
    assert hr_from_core(38.5) == pytest.approx(137.5, abs=0.5)


# --- PSI ---------------------------------------------------------------------------

def test_psi_zero_at_baseline():
    assert psi.psi(37.0, 70, 37.0, 70) == 0.0


def test_psi_ten_at_maxima():
    assert psi.psi(39.5, 180, 37.0, 70) == pytest.approx(10.0)


def test_psi_worked_example():
    # Half way on both scales -> 2.5 + 2.5
    assert psi.psi(38.25, 125, 37.0, 70) == pytest.approx(5.0)


def test_psi_clipped_to_scale():
    assert psi.psi(36.5, 60, 37.0, 70) == 0.0
    assert psi.psi(41.0, 200, 37.0, 70) == 10.0


def test_psi_bands():
    assert psi.psi_band(1.0) == "No/little"
    assert psi.psi_band(7.5) == "High"

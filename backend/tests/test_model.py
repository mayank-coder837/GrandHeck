import numpy as np
import pytest

from grandheck.pipeline.forecaster import Forecast, combine_with_model
from grandheck.pipeline.model import (FEATURES, HORIZONS_MIN, RidgeModel, feature_vector, fit_ridge,
                                      time_to_limit)


def test_time_to_limit_interpolates():
    path = [(0, 37.8), (10, 38.0), (20, 38.2), (30, 38.6)]
    assert time_to_limit(path, 38.1) == pytest.approx(15.0)
    assert time_to_limit(path, 37.5) == 0.0
    assert time_to_limit(path, 39.0) is None


def test_fit_ridge_recovers_linear_relationship():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(2000, 3))
    Y = np.stack([2.0 * X[:, 0] - 1.0 * X[:, 2] + 0.5 for _ in HORIZONS_MIN], axis=1)
    m = fit_ridge(X, Y, alpha=1e-6)
    pred = ((X - m.mean) / m.scale) @ m.coef.T + m.intercept
    assert np.allclose(pred, Y, atol=1e-3)


def test_risk_path_adds_scaled_error():
    m = RidgeModel(np.zeros(1), np.ones(1), np.zeros((6, 1)), np.zeros(6), resid_std=np.full(6, 0.2))
    path = [(h, 38.0) for h in HORIZONS_MIN]
    assert all(v == pytest.approx(38.2) for _, v in m.risk_path(path, 1.0))


def test_feature_vector_matches_feature_list():
    x = feature_vector(core_est=37.8, core_slope_c_per_h=0.5, hr=130, hr_rise_15=10, psi=4.0,
                       wbgt_excess=3.0, wbgt_trend_c_per_h=1.0, working=True, minutes_since_rest=40,
                       acclimatized=False, workload="heavy", older=False, data_minutes=90)
    assert x.shape == (len(FEATURES),)
    assert x[FEATURES.index("excess_x_unacclimatized")] == 3.0
    assert x[FEATURES.index("data_minutes_h")] == 1.0          # capped


def test_shipped_model_loads_and_is_sane():
    m = RidgeModel.load()
    assert m is not None, "run `python -m eval.train_forecaster` to create the model file"
    hot = feature_vector(core_est=37.8, core_slope_c_per_h=0.8, hr=140, hr_rise_15=12, psi=5.0,
                         wbgt_excess=6.0, wbgt_trend_c_per_h=1.0, working=True, minutes_since_rest=80,
                         acclimatized=False, workload="heavy", older=False, data_minutes=120)
    rest = feature_vector(core_est=37.8, core_slope_c_per_h=-0.5, hr=90, hr_rise_15=-10, psi=2.0,
                          wbgt_excess=-2.0, wbgt_trend_c_per_h=0.0, working=False, minutes_since_rest=0,
                          acclimatized=True, workload="light", older=False, data_minutes=120)
    hot_30 = m.predict_path(hot, 37.8)[3][1]
    rest_30 = m.predict_path(rest, 37.8)[3][1]
    assert hot_30 > 37.8 > rest_30            # a hot, working new worker heats; a resting one cools


def test_combine_prefers_model_crossing_and_keeps_psi():
    v1 = Forecast(ttc_min=12.0, driver="psi", core_slope_c_per_h=0.4, psi_slope_per_h=3.0, stale=False)
    path = [(h, 37.8 + 0.01 * h) for h in HORIZONS_MIN]
    fc = combine_with_model(v1, path, 38.5, ttc_core_model=None)
    assert fc.ttc_min == 12.0 and fc.driver == "psi"
    fc = combine_with_model(v1, path, 38.5, ttc_core_model=8.0)
    assert fc.ttc_min == 8.0 and fc.driver == "core"

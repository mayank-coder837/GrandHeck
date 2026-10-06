"""
ECTemp: core body temperature estimated from heart rate alone, using a
one-state extended Kalman filter (Buller et al., 2013) [BUL13].

Model (one step per minute):
    time update    CT_t = A * CT_{t-1} + w,   w ~ N(0, GAMMA^2)
    observation    HR_t = B2*CT_t^2 + B1*CT_t + B0 + v,   v ~ N(0, SIGMA^2)

The observation is non-linear, so it is linearised around the predicted CT
(that is what makes it an *extended* Kalman filter).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import config as C


def hr_from_core(ct_c: float) -> float:
    """The filter's observation model: expected HR for a core temperature."""
    return C.ECT_B2 * ct_c * ct_c + C.ECT_B1 * ct_c + C.ECT_B0


@dataclass
class ECTempFilter:
    ct: float = C.ECT_CT0_C
    v: float = C.ECT_V0
    steps: int = field(default=0)

    def predict(self, minutes: int = 1) -> float:
        """Time update only. Used when an HR sample is missing: variance grows."""
        for _ in range(minutes):
            self.ct = C.ECT_A * self.ct
            self.v = C.ECT_A ** 2 * self.v + C.ECT_GAMMA_SQ
        return self.ct

    def update(self, hr_bpm: float) -> float:
        """One full step (time update + HR observation). Returns the new CT estimate."""
        ct_pred = C.ECT_A * self.ct
        v_pred = C.ECT_A ** 2 * self.v + C.ECT_GAMMA_SQ
        c = 2.0 * C.ECT_B2 * ct_pred + C.ECT_B1          # d(HR)/d(CT) at the prediction
        gain = v_pred * c / (c * c * v_pred + C.ECT_SIGMA_SQ)
        self.ct = ct_pred + gain * (hr_bpm - hr_from_core(ct_pred))
        self.v = (1.0 - gain * c) * v_pred
        self.steps += 1
        return self.ct

    @property
    def std_c(self) -> float:
        return self.v ** 0.5

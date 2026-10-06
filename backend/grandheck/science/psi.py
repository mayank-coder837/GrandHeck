"""
Physiological Strain Index (Moran et al., 1998) [MOR98].

    PSI = 5 * (Tc - Tc0) / (39.5 - Tc0) + 5 * (HR - HR0) / (180 - HR0)

Tc0 and HR0 are the worker's baseline (start-of-shift, at rest) values.
The result is clipped to the paper's 0-10 scale.
"""

from __future__ import annotations

from .. import config as C


def psi(tc_c: float, hr_bpm: float, tc0_c: float, hr0_bpm: float) -> float:
    thermal = 5.0 * (tc_c - tc0_c) / (C.PSI_TC_MAX_C - tc0_c)
    cardio = 5.0 * (hr_bpm - hr0_bpm) / (C.PSI_HR_MAX - hr0_bpm)
    return max(0.0, min(10.0, thermal + cardio))


def psi_band(value: float) -> str:
    band = C.PSI_BANDS[0][1]
    for lower, name in C.PSI_BANDS:
        if value >= lower:
            band = name
    return band

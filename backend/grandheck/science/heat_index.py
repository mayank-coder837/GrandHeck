"""Heat index (apparent temperature), NWS Rothfusz regression [NWS]. Shown for comparison."""

from __future__ import annotations

from .. import config as C


def heat_index_c(air_temp_c: float, rh_pct: float) -> float:
    t = air_temp_c * 9.0 / 5.0 + 32.0
    rh = rh_pct
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    if (simple + t) / 2.0 < 80.0:
        hi = simple
    else:
        hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh
              - 0.00683783 * t * t - 0.05481717 * rh * rh + 0.00122874 * t * t * rh
              + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
        if rh < 13.0 and 80.0 <= t <= 112.0:
            hi -= ((13.0 - rh) / 4.0) * ((17.0 - abs(t - 95.0)) / 17.0) ** 0.5
        elif rh > 85.0 and 80.0 <= t <= 87.0:
            hi += ((rh - 85.0) / 10.0) * ((87.0 - t) / 5.0)
    return (hi - 32.0) * 5.0 / 9.0


def heat_index_band(hi_c: float) -> str:
    band = "Below caution"
    for lower, name in C.HEAT_INDEX_BANDS_C:
        if hi_c >= lower:
            band = name
    return band

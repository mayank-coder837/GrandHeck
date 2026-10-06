"""
Outdoor WBGT estimated from standard weather measurements.

Primary method: Liljegren et al. (2008) [LIL08]. It solves energy balances for
the black globe and the natural wet-bulb wick by fixed-point iteration, using
air temperature, humidity, wind, solar radiation and the sun's position.
This is a Python port of the structure of the authors' reference C code.

Fallback: Australian Bureau of Meteorology shade approximation [BOM]. Used when
solar radiation or wind is missing. It ignores sun and wind, so it reads low
outdoors; results carry method="bom_shade" so the UI can say so.

Simplification vs. [LIL08]: wind is assumed to be measured at ~2 m, so the
stability-class height correction in the reference code is skipped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from .. import config as C

STEFAN_B = 5.6696e-8
CP_AIR = 1003.5             # J/(kg K)
M_AIR = 28.97
M_H2O = 18.015
R_GAS = 8314.34
R_AIR = R_GAS / M_AIR
PRANDTL = CP_AIR / (CP_AIR + 1.25 * R_AIR)
RATIO = CP_AIR * M_AIR / M_H2O
KELVIN = 273.15


@dataclass(frozen=True)
class WbgtResult:
    wbgt_c: float
    t_nwb_c: float | None   # natural wet bulb (None for the fallback)
    t_globe_c: float | None
    method: str             # "liljegren" | "bom_shade"


# --- thermophysical helpers ([LIL08] reference code) -----------------------

def esat_hpa(t_k: float) -> float:
    """Saturation vapour pressure over water (Buck 1981 form, with enhancement)."""
    return 1.004 * 6.1121 * math.exp(17.502 * (t_k - KELVIN) / (t_k - 32.18))


def dew_point_k(e_hpa: float) -> float:
    z = math.log(e_hpa / (6.1121 * 1.004))
    return KELVIN + 240.97 * z / (17.502 - z)


def _viscosity(t_k: float) -> float:
    """Air viscosity, kg/(m s)."""
    sigma, eps_kappa = 3.617, 97.0
    tr = t_k / eps_kappa
    omega = (tr - 2.9) / 0.4 * (-0.034) + 1.048
    return 2.6693e-6 * math.sqrt(M_AIR * t_k) / (sigma * sigma * omega)


def _thermal_cond(t_k: float) -> float:
    return (CP_AIR + 1.25 * R_AIR) * _viscosity(t_k)


def _diffusivity(t_k: float, p_hpa: float) -> float:
    """Diffusivity of water vapour in air, m2/s."""
    pcrit13 = (36.4 * 218.0) ** (1.0 / 3.0)
    tcrit512 = (132.0 * 647.3) ** (5.0 / 12.0)
    tcrit12 = math.sqrt(132.0 * 647.3)
    mmix = math.sqrt(1.0 / M_AIR + 1.0 / M_H2O)
    return 3.64e-4 * (t_k / tcrit12) ** 2.334 * pcrit13 * tcrit512 * mmix / (p_hpa / 1013.25) * 1e-4


def _evap_heat(t_k: float) -> float:
    """Latent heat of evaporation, J/kg."""
    return (313.15 - t_k) / 30.0 * (-71100.0) + 2.4073e6


def _emis_atm(t_k: float, rh_frac: float) -> float:
    """Atmospheric emissivity from vapour pressure (Oke)."""
    e = rh_frac * esat_hpa(t_k)
    return 0.575 * e ** (1.0 / 7.0)


def _reynolds(diameter: float, t_k: float, p_hpa: float, wind: float) -> float:
    density = p_hpa * 100.0 / (R_AIR * t_k)
    return max(wind, C.LIL_MIN_WIND_MS) * density * diameter / _viscosity(t_k)


def _h_sphere(diameter: float, t_k: float, p_hpa: float, wind: float) -> float:
    re = _reynolds(diameter, t_k, p_hpa, wind)
    nu = 2.0 + 0.6 * math.sqrt(re) * PRANDTL ** 0.3333
    return nu * _thermal_cond(t_k) / diameter


def _h_cylinder(diameter: float, t_k: float, p_hpa: float, wind: float) -> float:
    re = _reynolds(diameter, t_k, p_hpa, wind)
    nu = 0.281 * re ** (1.0 - 0.4) * PRANDTL ** (1.0 - 0.56)
    return nu * _thermal_cond(t_k) / diameter


# --- sun position --------------------------------------------------------

def solar_cos_zenith(when: datetime, lat_deg: float, lon_deg: float) -> float:
    """Cosine of the solar zenith angle (NOAA general solar position equations)."""
    if when.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    utc = when.astimezone(timezone.utc)
    doy = utc.timetuple().tm_yday
    hour = utc.hour + utc.minute / 60.0 + utc.second / 3600.0
    g = 2.0 * math.pi / 365.0 * (doy - 1 + (hour - 12.0) / 24.0)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    true_solar_min = hour * 60.0 + eqtime + 4.0 * lon_deg
    hour_angle = math.radians(true_solar_min / 4.0 - 180.0)
    lat = math.radians(lat_deg)
    return (math.sin(lat) * math.sin(decl)
            + math.cos(lat) * math.cos(decl) * math.cos(hour_angle))


def direct_beam_fraction(solar_wm2: float, cza: float) -> tuple[float, float]:
    """
    Split measured global radiation into the direct-beam fraction, [LIL08] eq. 13.
    Returns (fdir, solar_clipped) where solar is clipped to the top-of-atmosphere max.
    """
    cza_min = math.cos(math.radians(89.5))
    if cza <= cza_min or solar_wm2 <= 0.0:
        return 0.0, max(solar_wm2, 0.0)
    toa = C.LIL_SOLAR_CONST * cza
    s = min(solar_wm2 / toa, 1.0)
    solar = s * toa
    if s <= 0.0:
        return 0.0, solar
    fdir = math.exp(3.0 - 1.34 * s - 1.65 / s)
    return max(0.0, min(fdir, 0.9)), solar


# --- the two component temperatures -----------------------------------------

def globe_temp_k(t_k: float, rh: float, p: float, wind: float,
                 solar: float, fdir: float, cza: float) -> float:
    """Black globe temperature, [LIL08] eq. 8, solved by iteration."""
    t_sfc = t_k
    tg = t_k
    cza = max(cza, math.cos(math.radians(89.5)))
    for _ in range(C.LIL_MAX_ITER):
        t_ref = 0.5 * (tg + t_k)
        h = _h_sphere(C.LIL_D_GLOBE_M, t_ref, p, wind)
        rad = (0.5 * (_emis_atm(t_k, rh) * t_k ** 4 + C.LIL_EMIS_SFC * t_sfc ** 4)
               - h / (C.LIL_EMIS_GLOBE * STEFAN_B) * (tg - t_k)
               + solar / (2.0 * C.LIL_EMIS_GLOBE * STEFAN_B) * (1.0 - C.LIL_ALB_GLOBE)
               * (fdir * (1.0 / (2.0 * cza) - 1.0) + 1.0 + C.LIL_ALB_SFC))
        tg_new = rad ** 0.25
        if abs(tg_new - tg) < C.LIL_CONVERGENCE_K:
            return tg_new
        tg = 0.9 * tg + 0.1 * tg_new  # damped update, as in the reference code
    return tg


def natural_wet_bulb_k(t_k: float, rh: float, p: float, wind: float,
                       solar: float, fdir: float, cza: float) -> float:
    """Natural (unventilated, sunlit) wet-bulb temperature, [LIL08] eq. 4."""
    t_sfc = t_k
    cza = max(cza, math.cos(math.radians(89.5)))
    sza = math.acos(cza)
    e_air = rh * esat_hpa(t_k)
    twb = dew_point_k(e_air)
    d, length = C.LIL_D_WICK_M, C.LIL_L_WICK_M
    for _ in range(C.LIL_MAX_ITER):
        t_ref = 0.5 * (twb + t_k)
        h = _h_cylinder(d, t_ref, p, wind)
        f_atm = (STEFAN_B * C.LIL_EMIS_WICK
                 * (0.5 * (_emis_atm(t_k, rh) * t_k ** 4 + C.LIL_EMIS_SFC * t_sfc ** 4) - twb ** 4)
                 + (1.0 - C.LIL_ALB_WICK) * solar
                 * ((1.0 - fdir) * (1.0 + 0.25 * d / length)
                    + fdir * ((math.tan(sza) / math.pi) + 0.25 * d / length)
                    + C.LIL_ALB_SFC))
        e_wick = esat_hpa(twb)
        density = p * 100.0 / (R_AIR * t_ref)
        schmidt = _viscosity(t_ref) / (density * _diffusivity(t_ref, p))
        twb_new = (t_k - _evap_heat(t_ref) / RATIO * (e_wick - e_air) / (p - e_wick)
                   * (PRANDTL / schmidt) ** 0.56 + f_atm / h)
        if abs(twb_new - twb) < C.LIL_CONVERGENCE_K:
            return twb_new
        twb = 0.9 * twb + 0.1 * twb_new
    return twb


# --- public API -------------------------------------------------------------

def wbgt_liljegren(air_temp_c: float, rh_pct: float, wind_ms: float, solar_wm2: float,
                   cos_zenith: float, pressure_hpa: float = C.SITE_PRESSURE_HPA) -> WbgtResult:
    t_k = air_temp_c + KELVIN
    rh = max(min(rh_pct, 100.0), 0.5) / 100.0
    fdir, solar = direct_beam_fraction(solar_wm2, cos_zenith)
    tg = globe_temp_k(t_k, rh, pressure_hpa, wind_ms, solar, fdir, cos_zenith) - KELVIN
    tnwb = natural_wet_bulb_k(t_k, rh, pressure_hpa, wind_ms, solar, fdir, cos_zenith) - KELVIN
    wbgt = C.WBGT_W_NWB * tnwb + C.WBGT_W_GLOBE * tg + C.WBGT_W_AIR * air_temp_c
    return WbgtResult(wbgt_c=wbgt, t_nwb_c=tnwb, t_globe_c=tg, method="liljegren")


def wbgt_bom_shade(air_temp_c: float, rh_pct: float) -> WbgtResult:
    e = rh_pct / 100.0 * 6.105 * math.exp(17.27 * air_temp_c / (237.7 + air_temp_c))
    wbgt = C.BOM_A * air_temp_c + C.BOM_B * e + C.BOM_C
    return WbgtResult(wbgt_c=wbgt, t_nwb_c=None, t_globe_c=None, method="bom_shade")


def estimate_wbgt(air_temp_c: float, rh_pct: float, wind_ms: float | None,
                  solar_wm2: float | None, when: datetime,
                  lat_deg: float = C.SITE_LAT_DEG, lon_deg: float = C.SITE_LON_DEG,
                  pressure_hpa: float | None = None) -> WbgtResult:
    """Liljegren when wind and solar are available, otherwise the shade fallback."""
    if wind_ms is None or solar_wm2 is None:
        return wbgt_bom_shade(air_temp_c, rh_pct)
    cza = solar_cos_zenith(when, lat_deg, lon_deg)
    return wbgt_liljegren(air_temp_c, rh_pct, wind_ms, solar_wm2, cza,
                          pressure_hpa or C.SITE_PRESSURE_HPA)

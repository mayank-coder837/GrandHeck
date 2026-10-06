"""
Every threshold and constant used by GrandHeck lives in this file.

Rules:
  * Each value carries a comment citing its source.
  * Values marked  TODO(verify)  must be checked against the primary source
    before the demo. `python -m grandheck.config` lists them.
  * Values marked  DESIGN  are engineering choices (alert timing, smoothing,
    UI behaviour). They are NOT health thresholds and are labelled as such.

References (short keys used below):
  [ISO7243]   ISO 7243:2017 Ergonomics of the thermal environment - Assessment of
              heat stress using the WBGT index.
  [ISO8996]   ISO 8996:2021 Ergonomics of the thermal environment - Determination
              of metabolic rate.
  [ACGIH]     ACGIH, TLVs and BEIs: Heat Stress and Strain (TLV documentation).
  [NIOSH]     NIOSH (2016) Criteria for a Recommended Standard: Occupational
              Exposure to Heat and Hot Environments. DHHS (NIOSH) Pub. 2016-106.
  [OSHA]      OSHA Technical Manual, Section III Chapter 4: Heat Stress.
  [LIL08]     Liljegren JC, Carhart RA, Lawday P, Tschopp S, Sharp R (2008).
              Modeling the wet bulb globe temperature using standard
              meteorological measurements. J Occup Environ Hyg 5(10):645-655.
  [BOM]       Australian Bureau of Meteorology, "About the WBGT and Apparent
              Temperature indices" (shade WBGT approximation).
  [NWS]       NWS Weather Prediction Center, "The Heat Index Equation"
              (Rothfusz 1990 regression with Steadman adjustments).
  [BUL13]     Buller MJ, Tharion WJ, Cheuvront SN, et al. (2013). Estimation of
              human core temperature from sequential heart rate observations.
              Physiol Meas 34(7):781-798.
  [MOR98]     Moran DS, Shitzer A, Pandolf KB (1998). A physiological strain
              index to evaluate heat stress. Am J Physiol 275:R129-R134.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Site
# ---------------------------------------------------------------------------
SITE_ID = "desert-01"
SITE_NAME = "Inland desert work site"
SITE_LAT_DEG = 23.1        # DESIGN: inland Arabian desert (Liwa area); used for sun position
SITE_LON_DEG = 53.8
SITE_UTC_OFFSET_H = 4
SITE_PRESSURE_HPA = 1008.0  # DESIGN: near sea level; used if the station omits pressure

# ---------------------------------------------------------------------------
# WBGT estimation  [ISO7243] [LIL08] [BOM]
# ---------------------------------------------------------------------------
# Outdoor (solar load) WBGT weighting, [ISO7243]:
#   WBGT = 0.7 * T_nwb + 0.2 * T_g + 0.1 * T_a
WBGT_W_NWB = 0.7
WBGT_W_GLOBE = 0.2
WBGT_W_AIR = 0.1

# Liljegren model physical constants, [LIL08] (as in the authors' reference C code)
LIL_D_GLOBE_M = 0.0508      # standard 2-inch globe diameter
LIL_EMIS_GLOBE = 0.95
LIL_ALB_GLOBE = 0.05
LIL_D_WICK_M = 0.007
LIL_L_WICK_M = 0.0254
LIL_EMIS_WICK = 0.95
LIL_ALB_WICK = 0.4
LIL_ALB_SFC = 0.45          # ground albedo   TODO(verify): desert sand may be ~0.3-0.4
LIL_EMIS_SFC = 0.999
LIL_MIN_WIND_MS = 0.13      # wind floor used by [LIL08] to avoid zero convection
LIL_SOLAR_CONST = 1367.0    # W/m2
LIL_MAX_ITER = 50
LIL_CONVERGENCE_K = 0.02    # iteration stops when temperature change < 0.02 K

# Shade-only fallback, [BOM]: WBGT = 0.567*Ta + 0.393*e + 3.94  (e in hPa).
# Ignores sun and wind, so it UNDER-estimates outdoor WBGT. UI flags its use.
BOM_A = 0.567
BOM_B = 0.393
BOM_C = 3.94

# ---------------------------------------------------------------------------
# Heat index  [NWS]
# ---------------------------------------------------------------------------
# NWS heat-index risk bands (converted from deg F: 80, 90, 103, 125 F).
HEAT_INDEX_BANDS_C = [
    (26.7, "Caution"),
    (32.2, "Extreme caution"),
    (39.4, "Danger"),
    (51.7, "Extreme danger"),
]

# ---------------------------------------------------------------------------
# Workload -> metabolic rate  [ACGIH] metabolic rate categories, cf. [ISO8996]
# ---------------------------------------------------------------------------
METABOLIC_RATE_W = {
    "rest": 115.0,
    "light": 180.0,
    "moderate": 300.0,
    "heavy": 415.0,
    "very_heavy": 520.0,
}  # TODO(verify): confirm against current ACGIH TLV table (values for a 70 kg worker)

# ---------------------------------------------------------------------------
# Environmental limits  [NIOSH] Chapter 8 (WBGT in deg C, M in watts)
#   Recommended Alert Limit, unacclimatized:   RAL = 59.9 - 14.1 * log10(M)
#   Recommended Exposure Limit, acclimatized:  REL = 56.7 - 11.5 * log10(M)
# ---------------------------------------------------------------------------
NIOSH_RAL_A, NIOSH_RAL_B = 59.9, 14.1
NIOSH_REL_A, NIOSH_REL_B = 56.7, 11.5

# ---------------------------------------------------------------------------
# Core temperature estimation, ECTemp Kalman filter  [BUL13]
# State: core temperature CT (deg C). One update per minute of HR data.
#   time update:    CT_t = A * CT_{t-1},             process variance GAMMA^2
#   observation:    HR   = B2*CT^2 + B1*CT + B0,      observation variance SIGMA^2
# ---------------------------------------------------------------------------
ECT_A = 1.0
ECT_GAMMA_SQ = 0.022 ** 2
ECT_B0 = -7887.1
ECT_B1 = 384.4286
ECT_B2 = -4.5714
ECT_SIGMA_SQ = 18.88 ** 2
ECT_CT0_C = 37.1            # initial core temperature
ECT_V0 = 0.0                # initial variance
# TODO(verify): parameter values above against [BUL13] Table/Appendix before demo.

# ---------------------------------------------------------------------------
# Physiological Strain Index  [MOR98]
#   PSI = 5*(Tc - Tc0)/(39.5 - Tc0) + 5*(HR - HR0)/(180 - HR0),  scale 0-10
# ---------------------------------------------------------------------------
PSI_TC_MAX_C = 39.5
PSI_HR_MAX = 180.0
PSI_BANDS = [               # [MOR98] strain categories
    (0.0, "No/little"),
    (3.0, "Low"),
    (5.0, "Moderate"),
    (7.0, "High"),
    (9.0, "Very high"),
]
PSI_CRITICAL = 7.0          # "High" strain in [MOR98].  TODO(verify): confirm cutoff for alerting

# ---------------------------------------------------------------------------
# Personal danger thresholds  [ACGIH]
# ACGIH: core temperature should not exceed 38.5 C for medically selected,
# acclimatized workers, or 38.0 C for unselected, unacclimatized workers.
# ---------------------------------------------------------------------------
CORE_LIMIT_ACCLIMATIZED_C = 38.5    # TODO(verify) against current ACGIH TLV documentation
CORE_LIMIT_UNACCLIMATIZED_C = 38.0  # TODO(verify) against current ACGIH TLV documentation

# Heart-rate criterion [ACGIH]: sustained (several minutes) HR above 180 - age
# is a reason to stop exposure. Used by the HR-only baseline alarm.
HR_SUSTAINED_LIMIT_BASE = 180.0
HR_SUSTAINED_MINUTES = 5            # TODO(verify): ACGIH says "several minutes"

# ---------------------------------------------------------------------------
# Exposure tracking
# ---------------------------------------------------------------------------
ACTIVITY_REST_THRESHOLD = 0.15      # DESIGN: activity index (0-1) below this = resting
REST_MIN_DURATION_MIN = 10          # DESIGN: a rest bout must last this long to reset
                                    # "time since rest". NIOSH work/rest regimens use
                                    # >=15 min breaks per hour (see [NIOSH] Ch. 8).
DROPOUT_TIMEOUT_MIN = 3             # DESIGN: no vitals for this long -> SIGNAL LOST
HISTORY_MINUTES = 240               # DESIGN: per-worker history kept for charts

# ---------------------------------------------------------------------------
# Forecaster
# ---------------------------------------------------------------------------
FORECAST_WINDOW_MIN = 15            # DESIGN: rolling regression window
FORECAST_MIN_POINTS = 8             # DESIGN: need this many points before forecasting
FORECAST_HORIZON_MIN = 120          # DESIGN: beyond this we report "> 120 min"

# ---------------------------------------------------------------------------
# Alert state machine  (all DESIGN choices, not health thresholds)
# Tier is chosen from forecast time-to-critical (TTC) in minutes.
# ---------------------------------------------------------------------------
ALERT_TTC_ADVISORY_MIN = 45
ALERT_TTC_WARNING_MIN = 20
ALERT_TTC_CRITICAL_MIN = 5
ALERT_ESCALATE_TICKS = 2            # consecutive minutes a higher tier must hold
ALERT_DEESCALATE_TICKS = 5          # consecutive minutes a lower tier must hold
ALERT_DEESCALATE_MARGIN_MIN = 10    # TTC must exceed tier limit by this to step down
ALERT_RENOTIFY_MIN = 10             # re-send an unchanged Warning/Critical this often
ALERT_OLDER_WORKER_EXTRA_MIN = 10   # DESIGN: older workers (age band 45+) are warned
                                    # this much earlier; age is a heat-illness risk
                                    # factor in [NIOSH] Ch. 4, the margin itself is ours.
ALERT_EXPOSURE_ADVISORY_MIN = 30    # DESIGN: >= this many minutes above own WBGT limit
                                    # without rest raises an Advisory on its own.

# Actions per tier. Hydration guidance: about 1 cup (8 oz, ~240 ml) every
# 15-20 minutes during work in heat [NIOSH] [OSHA].
ACTIONS = {
    "ADVISORY": "Drink 1 cup (~240 ml) of water now and every 15-20 min. "
                "Buddy check. Take the next break in shade.",
    "WARNING": "Stop strenuous work now. Rest in shade or a cooled shelter and "
               "drink water. Supervisor to check on worker.",
    "CRITICAL": "Stop work immediately. Move to a cool area and start active "
                "cooling. Do not leave the worker alone. If confused or collapsed, "
                "treat as heat stroke: cool with cold water and call for medical evacuation.",
}
# TODO(verify): rest duration for WARNING. [NIOSH] work/rest tables specify
# minutes of rest per hour by WBGT and workload; we avoid stating a number here.

# ---------------------------------------------------------------------------
# Simulation defaults (DESIGN)
# ---------------------------------------------------------------------------
SIM_SHIFT_START_HOUR = 7
SIM_SHIFT_LENGTH_MIN = 540          # 07:00 - 16:00
SIM_DEFAULT_SPEED = 1.0             # simulated minutes per real second


def todo_items() -> list[str]:
    """Return every line in this file marked TODO(verify)."""
    import pathlib

    lines = pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
    return [f"config.py:{i + 1}: {ln.strip()}" for i, ln in enumerate(lines)
            if "TODO(verify)" in ln and "def todo_items" not in ln and "marked" not in ln]


if __name__ == "__main__":
    for item in todo_items():
        print(item)

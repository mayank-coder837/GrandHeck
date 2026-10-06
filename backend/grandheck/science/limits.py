"""
Workload-dependent WBGT limits, NIOSH (2016) [NIOSH] Chapter 8.

  RAL (unacclimatized) = 59.9 - 14.1 * log10(M)
  REL (acclimatized)   = 56.7 - 11.5 * log10(M)
"""

from __future__ import annotations

import math

from .. import config as C


def metabolic_rate_w(workload: str) -> float:
    return C.METABOLIC_RATE_W[workload]


def niosh_ral_c(metabolic_w: float) -> float:
    return C.NIOSH_RAL_A - C.NIOSH_RAL_B * math.log10(metabolic_w)


def niosh_rel_c(metabolic_w: float) -> float:
    return C.NIOSH_REL_A - C.NIOSH_REL_B * math.log10(metabolic_w)


def wbgt_limit_c(workload: str, acclimatized: bool) -> float:
    """The limit that applies to one worker: REL if acclimatized, else RAL."""
    m = metabolic_rate_w(workload)
    return niosh_rel_c(m) if acclimatized else niosh_ral_c(m)


def classify_environment(wbgt_c: float, workload: str) -> str:
    """
    Heat-stress category for a workload:
      "low"      below the RAL: acceptable for all workers
      "elevated" between RAL and REL: unacclimatized workers at risk
      "high"     above the REL: all workers at risk, controls required
    """
    m = metabolic_rate_w(workload)
    if wbgt_c < niosh_ral_c(m):
        return "low"
    if wbgt_c < niosh_rel_c(m):
        return "elevated"
    return "high"

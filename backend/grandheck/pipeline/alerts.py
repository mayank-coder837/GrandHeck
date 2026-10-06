"""
Per-worker alert state machine: NONE -> ADVISORY -> WARNING -> CRITICAL.

Why a state machine: raw forecasts wobble minute to minute. Firing an alert
every time they cross a line would flap and train people to ignore alarms.

  * Escalation needs the higher tier to hold for ALERT_ESCALATE_TICKS minutes.
    Exception: actually reaching the danger threshold escalates to CRITICAL at once.
  * De-escalation needs ALERT_DEESCALATE_TICKS minutes below the current tier
    AND the forecast must clear the tier's limit by ALERT_DEESCALATE_MARGIN_MIN.
  * De-duplication: one event per change of tier; an unchanged WARNING or
    CRITICAL is re-sent only every ALERT_RENOTIFY_MIN minutes.
  * Sensor dropout freezes the tier and emits its own signal_lost event.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config as C

LEVELS = ["NONE", "ADVISORY", "WARNING", "CRITICAL"]


@dataclass
class AlertInputs:
    ttc_min: float | None           # earliest likely crossing (v2: risk edge) -> Advisory/Warning
    ttc_expected_min: float | None  # crossing of the central forecast -> Critical
    at_threshold: bool              # core estimate or PSI already at/over the danger line
    exposure_minutes: int           # continuous minutes above own WBGT limit since last rest
    signal_lost: bool
    extra_lead_min: float = 0.0     # e.g. older workers get warned earlier


@dataclass
class AlertEvent:
    level: str
    kind: str                       # escalated | renotify | resolved | signal_lost | signal_restored
    ttc_min: float | None


def raw_level(x: AlertInputs) -> int:
    """The tier the current numbers point to, before any hysteresis."""
    lead = x.extra_lead_min
    if x.at_threshold or (x.ttc_expected_min is not None
                          and x.ttc_expected_min <= C.ALERT_TTC_CRITICAL_MIN + lead):
        return 3
    if x.ttc_min is not None and x.ttc_min <= C.ALERT_TTC_WARNING_MIN + lead:
        return 2
    if ((x.ttc_min is not None and x.ttc_min <= C.ALERT_TTC_ADVISORY_MIN + lead)
            or x.exposure_minutes >= C.ALERT_EXPOSURE_ADVISORY_MIN):
        return 1
    return 0


def _tier_limit(level: int, lead: float) -> float:
    return {1: C.ALERT_TTC_ADVISORY_MIN, 2: C.ALERT_TTC_WARNING_MIN,
            3: C.ALERT_TTC_CRITICAL_MIN}[level] + lead


class AlertStateMachine:
    def __init__(self) -> None:
        self.level = 0
        self._up_count = 0
        self._down_count = 0
        self._minutes_since_notify = 0
        self.signal_lost = False

    @property
    def level_name(self) -> str:
        return LEVELS[self.level]

    def _clear_for_step_down(self, x: AlertInputs) -> bool:
        if x.at_threshold:
            return False
        ttc = x.ttc_expected_min if self.level == 3 else x.ttc_min
        if ttc is None:
            return True
        return ttc > _tier_limit(self.level, x.extra_lead_min) + C.ALERT_DEESCALATE_MARGIN_MIN

    def step(self, x: AlertInputs) -> list[AlertEvent]:
        events: list[AlertEvent] = []
        self._minutes_since_notify += 1

        # Sensor dropout: announce once, hold the tier (we cannot know it improved).
        if x.signal_lost:
            if not self.signal_lost:
                self.signal_lost = True
                events.append(AlertEvent(self.level_name, "signal_lost", None))
            return events
        if self.signal_lost:
            self.signal_lost = False
            events.append(AlertEvent(self.level_name, "signal_restored", x.ttc_min))

        target = raw_level(x)
        if target > self.level:
            self._down_count = 0
            self._up_count += 1
            if self._up_count >= C.ALERT_ESCALATE_TICKS or x.at_threshold:
                self.level = target
                self._up_count = 0
                self._minutes_since_notify = 0
                events.append(AlertEvent(self.level_name, "escalated", x.ttc_min))
                return events
        elif target < self.level:
            self._up_count = 0
            self._down_count = self._down_count + 1 if self._clear_for_step_down(x) else 0
            if self._down_count >= C.ALERT_DEESCALATE_TICKS:
                self.level = target
                self._down_count = 0
                self._minutes_since_notify = 0
                events.append(AlertEvent(self.level_name, "resolved", x.ttc_min))
                return events
        else:
            self._up_count = 0
            self._down_count = 0

        if self.level >= 2 and self._minutes_since_notify >= C.ALERT_RENOTIFY_MIN:
            self._minutes_since_notify = 0
            events.append(AlertEvent(self.level_name, "renotify", x.ttc_min))
        return events

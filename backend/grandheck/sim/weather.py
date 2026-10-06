"""
Synthetic desert weather for one shift.

Air temperature follows a diurnal curve (minimum near sunrise, maximum mid
afternoon). Humidity comes from a dew point, so RH falls as the air heats,
as it does in a dry desert. Solar radiation follows the real sun position for
the site. The "afternoon build" profile adds a humid sea-breeze surge and
falling wind after midday, which pushes WBGT up fast.

Everything here is a simulation model, not a detection rule.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime

from .. import config as C
from ..science.wbgt import esat_hpa, solar_cos_zenith


@dataclass(frozen=True)
class WeatherProfile:
    name: str
    t_min_c: float          # near sunrise
    t_max_c: float          # mid-afternoon peak
    dew_point_c: float
    wind_ms: float
    humid_surge_dp_c: float = 0.0   # extra dew point added during the surge
    surge_start_h: float = 12.0
    surge_ramp_h: float = 2.5
    surge_wind_factor: float = 1.0  # wind multiplier at full surge


PROFILES = {
    "normal": WeatherProfile("Normal hot day", t_min_c=31, t_max_c=43, dew_point_c=12, wind_ms=2.5),
    "afternoon_build": WeatherProfile("Heat building through the afternoon", t_min_c=32, t_max_c=45,
                                      dew_point_c=13, wind_ms=2.5, humid_surge_dp_c=7,
                                      surge_start_h=11.5, surge_ramp_h=3.0, surge_wind_factor=0.5),
}


def rh_from_dew_point(t_c: float, td_c: float) -> float:
    return max(3.0, min(100.0, 100.0 * esat_hpa(td_c + 273.15) / esat_hpa(t_c + 273.15)))


class WeatherModel:
    def __init__(self, profile: WeatherProfile, rng: random.Random,
                 lat: float = C.SITE_LAT_DEG, lon: float = C.SITE_LON_DEG) -> None:
        self.p = profile
        self.rng = rng
        self.lat, self.lon = lat, lon
        self._wind_noise = 0.0
        self._temp_noise = 0.0
        self.heat_offset_c = 0.0    # set by live scenario events

    def _diurnal(self, hour: float) -> float:
        """0 at 06:00, 1 at 14:30, easing back towards 0 overnight."""
        if hour < 6.0:
            return 0.1 * (6.0 - hour) / 6.0
        if hour <= 14.5:
            return math.sin((hour - 6.0) / 8.5 * math.pi / 2.0)
        return max(0.0, math.cos((hour - 14.5) / 9.5 * math.pi / 2.0))

    def _surge(self, hour: float) -> float:
        if self.p.humid_surge_dp_c == 0.0 or hour < self.p.surge_start_h:
            return 0.0
        return min(1.0, (hour - self.p.surge_start_h) / self.p.surge_ramp_h)

    def sample(self, when: datetime) -> dict:
        hour = when.hour + when.minute / 60.0
        self._temp_noise = 0.9 * self._temp_noise + self.rng.gauss(0, 0.15)
        t = (self.p.t_min_c + (self.p.t_max_c - self.p.t_min_c) * self._diurnal(hour)
             + self._temp_noise + self.heat_offset_c)
        surge = self._surge(hour)
        td = self.p.dew_point_c + self.p.humid_surge_dp_c * surge + self.rng.gauss(0, 0.2)
        rh = rh_from_dew_point(t, td)

        cza = solar_cos_zenith(when, self.lat, self.lon)
        clear_sky = 1050.0 * max(cza, 0.0) ** 1.15      # clear-sky global irradiance shape
        solar = max(0.0, clear_sky * (1.0 + self.rng.gauss(0, 0.02)))

        self._wind_noise = 0.85 * self._wind_noise + self.rng.gauss(0, 0.25)
        wind_factor = 1.0 + (self.p.surge_wind_factor - 1.0) * surge
        wind = max(0.2, self.p.wind_ms * wind_factor + self._wind_noise)

        return {"air_temp_c": round(t, 2), "rh_pct": round(rh, 1), "solar_wm2": round(solar, 1),
                "wind_ms": round(wind, 2), "pressure_hpa": C.SITE_PRESSURE_HPA}

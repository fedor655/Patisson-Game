"""Clock, sun position, seasons and the lighting mood that follows from them."""

from __future__ import annotations

import math
from dataclasses import dataclass

from panda3d.core import Vec3

SEASONS = ("Весна", "Лето", "Осень", "Зима")

# Season -> (grass tint, tree tint, cloud cover bias, temperature label)
SEASON_STYLE = {
    0: (Vec3(0.42, 0.68, 0.26), Vec3(0.36, 0.62, 0.24), 0.10, "тепло"),
    1: (Vec3(0.38, 0.63, 0.20), Vec3(0.28, 0.55, 0.19), -0.06, "жарко"),
    2: (Vec3(0.60, 0.52, 0.20), Vec3(0.72, 0.42, 0.14), 0.16, "прохладно"),
    3: (Vec3(0.72, 0.76, 0.80), Vec3(0.55, 0.58, 0.62), 0.24, "морозно"),
}


@dataclass
class SkyState:
    sun_dir: Vec3
    sun_color: Vec3
    exposure: float
    cloud_cover: float
    fog_tint: Vec3
    ambient_scale: float
    is_night: bool


class DayNightCycle:
    """Drives an in-game clock and turns it into light."""

    def __init__(self, day_length: float, start_hour: float = 7.0,
                 season_days: int = 7, latitude: float = 52.0):
        self.day_length = day_length
        self.season_days = season_days
        self.latitude = math.radians(latitude)
        self.total_time = start_hour / 24.0 * day_length
        self.paused = False

    # -------------------------------------------------------------- clock

    @property
    def day(self) -> int:
        return int(self.total_time // self.day_length)

    @property
    def hour(self) -> float:
        frac = (self.total_time % self.day_length) / self.day_length
        return frac * 24.0

    @property
    def season(self) -> int:
        return (self.day // self.season_days) % 4

    @property
    def season_name(self) -> str:
        return SEASONS[self.season]

    def clock_string(self) -> str:
        h = int(self.hour)
        m = int((self.hour - h) * 60)
        return f"{h:02d}:{m:02d}"

    def advance(self, dt: float) -> None:
        if not self.paused:
            self.total_time += dt

    def skip_to_hour(self, hour: float) -> None:
        day_start = self.day * self.day_length
        target = day_start + hour / 24.0 * self.day_length
        if target <= self.total_time:
            target += self.day_length
        self.total_time = target

    # -------------------------------------------------------------- lighting

    def sun_direction(self) -> Vec3:
        """Direction *towards* the sun, world space, Z-up."""
        # Hour angle: 0 at solar noon.
        h = (self.hour - 12.0) / 24.0 * math.tau
        # Declination drifts with the season for longer summer days.
        season_phase = (self.day / (self.season_days * 4.0)) * math.tau
        decl = math.radians(20.0) * math.sin(season_phase)

        sin_alt = (math.sin(self.latitude) * math.sin(decl)
                   + math.cos(self.latitude) * math.cos(decl) * math.cos(h))
        alt = math.asin(max(-1.0, min(1.0, sin_alt)))
        cos_az = ((math.sin(decl) - math.sin(alt) * math.sin(self.latitude))
                  / max(math.cos(alt) * math.cos(self.latitude), 1e-4))
        az = math.acos(max(-1.0, min(1.0, cos_az)))
        if h > 0:
            az = math.tau - az

        # Azimuth measured from north (+Y), rotating east.
        x = math.cos(alt) * math.sin(az)
        y = math.cos(alt) * math.cos(az)
        z = math.sin(alt)
        return Vec3(x, y, z).normalized()

    def state(self) -> SkyState:
        sun = self.sun_direction()
        alt = sun.z

        # Sunlight reddens and dims as it approaches the horizon.
        day = max(0.0, min(1.0, alt * 5.5))
        warm = max(0.0, min(1.0, 1.0 - alt * 3.2))
        colour = Vec3(1.0, 0.96, 0.90) * (1.0 - warm) + Vec3(1.0, 0.58, 0.30) * warm
        intensity = 26.0 * day ** 0.75

        night = alt < -0.02
        if night:
            # Moonlight: dim, cold, and coming from roughly the opposite side.
            colour = Vec3(0.44, 0.56, 0.92)
            intensity = 0.85

        season = self.season
        cover = 0.40 + SEASON_STYLE[season][2]
        # A slow, deterministic weather wobble so days differ.
        cover += 0.18 * math.sin(self.total_time / self.day_length * 1.7)
        cover = max(0.05, min(0.85, cover))

        exposure = 0.165 if not night else 0.62
        if 0.0 < alt < 0.16:
            exposure = 0.165 + (0.16 - alt) * 2.6

        fog_tint = Vec3(1.0, 1.0, 1.0)
        if warm > 0.2 and not night:
            fog_tint = Vec3(1.0, 0.93, 0.86)
        if night:
            fog_tint = Vec3(0.78, 0.86, 1.12)

        return SkyState(
            sun_dir=sun if not night else Vec3(-sun.x, -sun.y, max(-sun.z, 0.12)).normalized(),
            sun_color=colour * intensity,
            exposure=exposure,
            cloud_cover=cover,
            fog_tint=fog_tint,
            ambient_scale=1.0 if not night else 0.55,
            is_night=night,
        )

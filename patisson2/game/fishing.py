"""Fishing: species, rarity, and a bite-then-reel minigame with real timing.

What bites depends on the hour and the season, so the pond is worth visiting at
different times. Landing it depends on the player: a strike window, then a
sweeping marker that has to be stopped inside a target band several times over.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Species:
    key: str
    name: str
    price: int              # per kilo
    weight: float           # relative chance before time/season modifiers
    size: tuple             # (min kg, max kg)
    hours: tuple            # (start, end) when it is most active; () = any
    seasons: tuple          # seasons it favours; () = any
    pulls: int              # successful pulls needed to land it
    band: float             # width of the target band, 0..1 — smaller is harder
    speed: float            # marker sweeps per second
    note: str = ""


SPECIES: tuple[Species, ...] = (
    Species("roach", "Плотва", 9, 30, (0.1, 0.5), (), (), 2, 0.30, 0.85,
            "Мелочь, но клюёт всегда."),
    Species("crucian", "Карась", 12, 26, (0.2, 0.9), (6.0, 20.0), (), 2, 0.27, 0.95,
            "Держится у берега днём."),
    Species("perch", "Окунь", 17, 20, (0.2, 1.2), (7.0, 18.0), (0, 1, 2), 3, 0.23, 1.15,
            "Полосатый, бойкий."),
    Species("trout", "Форель", 26, 11, (0.5, 2.2), (5.0, 10.0), (0, 1), 3, 0.19, 1.35,
            "Утренняя рыба, любит прохладу."),
    Species("pike", "Щука", 40, 7, (1.0, 5.0), (17.0, 21.0), (1, 2), 4, 0.16, 1.55,
            "Выходит на охоту в сумерках."),
    Species("catfish", "Сом", 55, 4, (3.0, 12.0), (22.0, 4.0), (1, 2), 4, 0.13, 1.15,
            "Ночной великан со дна."),
    Species("goldfish", "Золотая рыбка", 220, 1, (0.2, 0.4), (), (), 5, 0.11, 1.9,
            "Говорят, исполняет желания. Продать тоже можно."),
    Species("boot", "Старый сапог", 0, 8, (0.6, 1.4), (), (), 1, 0.40, 0.7,
            "Не рыба."),
)

BY_KEY = {s.key: s for s in SPECIES}

# Насколько реже клюёт рыба вне своего сезона. Не ноль: в справочнике
# перечисление сезонов читается как «в остальные не клюёт», и это
# неправда — поэтому число названо, и справочник берёт его отсюда.
OFF_SEASON = 0.35


def _hour_active(species: Species, hour: float) -> bool:
    if not species.hours:
        return True
    start, end = species.hours
    if start <= end:
        return start <= hour <= end
    return hour >= start or hour <= end        # window wrapping midnight


def roll_species(hour: float, season: int, luck: float,
                 rng: random.Random) -> Species:
    """Pick what bit. Luck (from a better rod) tilts towards rarer fish."""
    weights = []
    for s in SPECIES:
        w = float(s.weight)
        if _hour_active(s, hour):
            w *= 2.6
        elif s.hours:
            w *= 0.28
        if s.seasons and season not in s.seasons:
            w *= OFF_SEASON
        # Luck lifts the rare end and trims the junk.
        if s.weight <= 8 and s.key != "boot":
            w *= 1.0 + luck
        if s.key == "boot":
            w *= max(0.15, 1.0 - luck * 0.7)
        weights.append(w)
    return rng.choices(SPECIES, weights=weights)[0]


@dataclass
class Catch:
    species: Species
    size: float

    @property
    def value(self) -> int:
        return int(round(self.species.price * self.size))

    def describe(self) -> str:
        return f"{self.species.name}, {self.size:.1f} кг"


# --- states ------------------------------------------------------------------
IDLE = "idle"
WAITING = "waiting"      # line is out, nothing yet
BITE = "bite"            # strike window is open
REELING = "reeling"      # marker sweeping, land it
DONE = "done"


@dataclass
class FishingState:
    phase: str = IDLE
    timer: float = 0.0
    species: Species | None = None
    size: float = 0.0
    marker: float = 0.0          # 0..1 position of the sweeping marker
    direction: float = 1.0
    band_centre: float = 0.5
    pulls_done: int = 0
    misses: int = 0
    message: str = ""

    @property
    def band(self) -> float:
        return self.species.band if self.species else 0.25

    def in_band(self) -> bool:
        return abs(self.marker - self.band_centre) <= self.band * 0.5


MAX_MISSES = 3


class Fishing:
    """The rod's state machine. Owns no rendering — the HUD reads this."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.state = FishingState()

    @property
    def active(self) -> bool:
        return self.state.phase not in (IDLE, DONE)

    def cast(self, upgrades) -> None:
        s = self.state
        s.phase = WAITING
        base = 2.6 * upgrades.bite_speed
        s.timer = self.rng.uniform(base * 0.55, base * 1.9)
        s.species = None
        s.pulls_done = 0
        s.misses = 0
        s.message = "Ждём поклёвки…"

    def cancel(self) -> None:
        self.state = FishingState()

    def _start_reel(self, hour: float, season: int, luck: float) -> None:
        s = self.state
        s.species = roll_species(hour, season, luck, self.rng)
        lo, hi = s.species.size
        # Skew towards the small end so a big one means something.
        s.size = lo + (hi - lo) * (self.rng.random() ** 1.7)
        s.phase = REELING
        s.marker = self.rng.random()
        s.direction = 1.0 if self.rng.random() < 0.5 else -1.0
        s.band_centre = self.rng.uniform(0.25, 0.75)
        s.pulls_done = 0
        s.misses = 0
        s.message = "Тяни!"

    def strike(self, hour: float, season: int, luck: float) -> str | None:
        """Player pressed the action key. Returns an event name if one occurred."""
        s = self.state
        if s.phase == WAITING:
            s.phase = IDLE
            s.message = ""
            return "early"                      # struck too soon
        if s.phase == BITE:
            self._start_reel(hour, season, luck)
            return "hooked"
        if s.phase == REELING:
            if s.in_band():
                s.pulls_done += 1
                s.band_centre = self.rng.uniform(0.18, 0.82)
                if s.pulls_done >= s.species.pulls:
                    s.phase = DONE
                    return "landed"
                return "pull"
            s.misses += 1
            if s.misses >= MAX_MISSES:
                s.phase = IDLE
                s.message = ""
                return "lost"
            return "miss"
        return None

    def update(self, dt: float, upgrades) -> str | None:
        s = self.state
        if s.phase == WAITING:
            s.timer -= dt
            if s.timer <= 0.0:
                s.phase = BITE
                # Better rods buy a more forgiving strike window.
                s.timer = upgrades.strike_window
                s.message = "Подсекай!"
                return "bite"
        elif s.phase == BITE:
            s.timer -= dt
            if s.timer <= 0.0:
                s.phase = IDLE
                s.message = ""
                return "missed_bite"
        elif s.phase == REELING:
            speed = s.species.speed * upgrades.reel_ease
            s.marker += s.direction * speed * dt
            if s.marker > 1.0:
                s.marker = 2.0 - s.marker
                s.direction = -1.0
            elif s.marker < 0.0:
                s.marker = -s.marker
                s.direction = 1.0
        return None

    def take_catch(self) -> Catch | None:
        s = self.state
        if s.phase != DONE or s.species is None:
            return None
        catch = Catch(s.species, s.size)
        self.state = FishingState()
        return catch

"""The farm, simulated with nobody watching.

A hosted game needs one authoritative copy of the world: the beds, the
clock, the weather, the crows, the animals, the villagers and the money
all live here, on a machine that has no window and no graphics library.
The same classes the desktop game runs are reused unchanged — a second
implementation of farming would drift from the first, and then a plot
that is ripe on the server would still be a sprout on somebody's screen.

What the simulation asks of the renderer is small and already funnelled
through `game/view.py`; what it asks of the *world* is a little wider —
ground height, whether a spot may be tilled, a node to hang models on.
Those are answered here: the height comes from the same `HeightField`
the drawn terrain is built from, and everything scene-shaped is a node
that politely forgets what it is told.
"""

from __future__ import annotations

import random

from ..config import Config
from ..game.farming import Farm
from ..game.livestock import Livestock
from ..game.pests import Pests
from ..game.state import GameState
from ..game.view import NullNode, Vec3
from ..world.heightfield import HeightField
from ..world.layout import plot_positions


# Nobody is standing on the farm when only the server is running.
_FAR_AWAY = Vec3(1e6, 1e6, 0.0)


class _Mask:
    """The paint layer that hides grass. Nothing to hide without a screen."""

    def paint(self, *_args, **_kwargs) -> None:
        return None


class HeadlessWorld:
    """Answers the questions the simulation asks about the ground."""

    def __init__(self, cfg: Config):
        self.cfg = cfg.world
        self.field = HeightField(cfg.world)
        self.root = NullNode("world")
        self.mask = _Mask()
        self.blockers = _Blockers()

    def height_at(self, x: float, y: float) -> float:
        return self.field.height_at(x, y)

    def slope_at(self, x: float, y: float) -> float:
        return self.field.slope_at(x, y)

    def is_water(self, x: float, y: float) -> bool:
        return self.field.is_water(x, y)

    def can_till(self, x: float, y: float) -> bool:
        return self.field.can_till(x, y)


class _Blockers:
    """Collision, for code that asks whether a spot is free."""

    def resolve(self, x, y, _radius=0.0, _z=0.0):
        return x, y

    def add_post(self, *_a, **_k):
        return None

    add_box = add_walls = add_post


class _Pipeline:
    def apply_scene_shader(self, *_a, **_k) -> None:
        return None


class HeadlessProps:
    """Stands in for the scene dressing: no models, but the same handles."""

    def __init__(self, world: HeadlessWorld):
        self.world = world
        self.pipeline = _Pipeline()
        self.root = NullNode("props")
        self.dynamic = NullNode("dynamic")
        self.foliage = NullNode("foliage")
        self.animals: list = []
        self.lanterns: list = []
        self.trees: list = []
        self.bed_pos = None
        self.hearth_pos = None
        self.barn_light = None

    def ground(self, x: float, y: float) -> float:
        return self.world.height_at(x, y)


class SharedWorld:
    """One farm, simulated for everyone playing on it.

    Owns exactly what a client must not decide for itself: how the crops
    grow, what the weather does, when a crow lands, and how much money
    the farm has. Clients send what they *want* to do; this decides what
    actually happened.
    """

    def __init__(self, cfg: Config | None = None, seed: int | None = None):
        self.cfg = cfg or Config()
        self.world = HeadlessWorld(self.cfg)
        self.props = HeadlessProps(self.world)
        self.rng = random.Random(seed if seed is not None
                                 else self.cfg.world.seed)

        from ..world.daynight import DayNightCycle
        from ..world.weatherstate import WeatherState

        g = self.cfg.game
        self.cycle = DayNightCycle(g.day_length, g.start_hour,
                                   g.season_days)
        self.weather_state = WeatherState()
        self.state = GameState(g)
        self.farm = Farm(None, self.world, self.props, g.day_length)
        for x, y in plot_positions():
            self.farm.add_plot(x, y)
        self.pests = Pests(None, self.world, self.props, self.farm,
                           g.day_length, rng=self.rng)
        self.livestock = Livestock(None, self.world, self.props,
                                   g.day_length)
        self.events: list[str] = []

    # ------------------------------------------------------------ ticking

    @property
    def weather(self) -> str:
        return self.weather_state.kind

    def update(self, dt: float) -> list[str]:
        """Advance the whole farm by dt seconds and report what happened."""
        self.cycle.advance(dt)
        self.weather_state.roll(dt, self.cycle.season, self.rng)
        raining = self.weather in ("rain", "storm")
        events = self.farm.update(dt, self.cycle.season, raining)
        # Crows judge distance to the player; with nobody standing
        # there, they are simply never scared off by hand.
        events += self.pests.update(dt, _FAR_AWAY, raining)
        events += self.livestock.update(dt) or []
        if events:
            self.events.extend(events)
            del self.events[:-50]
        return events

    # ------------------------------------------------------------- saving

    def to_dict(self) -> dict:
        return {
            "day": self.cycle.day,
            "time": self.cycle.total_time,
            "weather": self.weather,
            "state": self.state.to_dict(),
            "farm": self.farm.to_dict(),
            "pests": self.pests.to_dict(),
        }

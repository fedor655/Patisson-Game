"""Crops, plots and growth.

A plot tracks water, nutrients and health. Growth only advances while the plant
has both water and food; neglect it long enough and it withers. Rain waters
everything for free, and each crop only thrives in its own seasons.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from panda3d.core import NodePath, Vec3

from ..world.props import place


@dataclass(frozen=True)
class Crop:
    key: str
    name: str
    stages: tuple            # ((model, scale), ...) low -> ripe
    grow_days: float         # in-game days from seed to ripe, well tended
    seed_price: int
    sell_price: int
    seasons: tuple           # season indices where it grows at full speed
    thirst: float = 1.0      # water use multiplier
    yield_count: int = 1


CROPS: dict[str, Crop] = {
    "patisson": Crop(
        "patisson", "Патиссон",
        (("patisson_0", 1.0), ("patisson_1", 1.0), ("patisson_2", 1.0), ("patisson_3", 1.0)),
        grow_days=2.5, seed_price=10, sell_price=52, seasons=(0, 1, 2), yield_count=1),
    "carrot": Crop(
        "carrot", "Морковь",
        (("patisson_0", 0.9), ("carrot", 0.55), ("carrot", 1.0)),
        grow_days=1.5, seed_price=4, sell_price=17, seasons=(0, 1, 2), thirst=0.85),
    "tomato": Crop(
        "tomato", "Томат",
        (("patisson_0", 1.0), ("tomato", 0.5), ("tomato", 1.0)),
        grow_days=2.0, seed_price=8, sell_price=31, seasons=(1, 2), thirst=1.25,
        yield_count=2),
    "wheat": Crop(
        "wheat", "Пшеница",
        (("patisson_0", 0.8), ("wheat", 0.55), ("wheat", 1.0)),
        grow_days=1.2, seed_price=3, sell_price=11, seasons=(0, 1, 2), thirst=0.7,
        yield_count=3),
    "pumpkin": Crop(
        "pumpkin", "Тыква",
        (("patisson_0", 1.1), ("pumpkin", 0.42), ("pumpkin", 0.72), ("pumpkin", 1.0)),
        grow_days=3.5, seed_price=16, sell_price=88, seasons=(2,), thirst=1.4),
}

CROP_ORDER = ("patisson", "carrot", "tomato", "wheat", "pumpkin")


@dataclass
class Plot:
    x: float
    y: float
    z: float
    crop: str | None = None
    progress: float = 0.0        # 0..1
    water: float = 0.0           # 0..1
    food: float = 0.0            # 0..1
    health: float = 1.0
    tilled: bool = False
    node: NodePath | None = None
    stage: int = -1
    _wither_warned: bool = False

    @property
    def ripe(self) -> bool:
        return self.crop is not None and self.progress >= 1.0

    @property
    def pos(self) -> Vec3:
        return Vec3(self.x, self.y, self.z)


class Farm:
    """All the plots, their state, and the plant models standing in them."""

    def __init__(self, base, world, props, day_length: float):
        self.base = base
        self.world = world
        self.props = props
        self.day_length = day_length
        self.root = world.root.attachNewNode("crops")
        props.pipeline.apply_scene_shader(self.root, wind=0.35, wind_pivot=0.02)
        self.plots: list[Plot] = []
        self.harvest_log: dict[str, int] = {}

    # -------------------------------------------------------------- plots

    def add_plot(self, x: float, y: float, tilled: bool = True) -> Plot:
        z = self.world.height_at(x, y)
        plot = Plot(x, y, z, tilled=tilled)
        self.plots.append(plot)
        if tilled:
            self.world.mask.paint(x, y, 0.52, 0)
        return plot

    def nearest(self, pos: Vec3, radius: float = 2.0) -> Plot | None:
        best, best_d = None, radius * radius
        for p in self.plots:
            d = (p.x - pos.x) ** 2 + (p.y - pos.y) ** 2
            if d < best_d:
                best, best_d = p, d
        return best

    def till(self, x: float, y: float) -> Plot | None:
        if not self.world.can_till(x, y):
            return None
        existing = self.nearest(Vec3(x, y, 0), 0.9)
        if existing is not None:
            return None
        return self.add_plot(x, y)

    # ------------------------------------------------------------- actions

    def plant(self, plot: Plot, crop_key: str) -> bool:
        if plot.crop is not None or not plot.tilled:
            return False
        plot.crop = crop_key
        plot.progress = 0.0
        plot.health = 1.0
        plot.water = max(plot.water, 0.35)
        plot.food = max(plot.food, 0.3)
        plot.stage = -1
        plot._wither_warned = False
        self._refresh_model(plot)
        return True

    def water_plot(self, plot: Plot, amount: float = 0.55) -> bool:
        if plot.crop is None:
            return False
        if plot.water >= 0.98:
            return False
        plot.water = min(1.0, plot.water + amount)
        return True

    def feed_plot(self, plot: Plot, amount: float = 0.6) -> bool:
        if plot.crop is None or plot.food >= 0.98:
            return False
        plot.food = min(1.0, plot.food + amount)
        return True

    def harvest(self, plot: Plot) -> tuple[str, int] | None:
        if not plot.ripe:
            return None
        crop = CROPS[plot.crop]
        bonus = 1 if plot.health > 0.92 and plot.food > 0.6 else 0
        count = crop.yield_count + bonus
        self.harvest_log[crop.key] = self.harvest_log.get(crop.key, 0) + count
        plot.crop = None
        plot.progress = 0.0
        plot.stage = -1
        plot.food = max(0.0, plot.food - 0.45)
        self._clear_model(plot)
        return crop.key, count

    def clear(self, plot: Plot) -> None:
        plot.crop = None
        plot.progress = 0.0
        plot.stage = -1
        self._clear_model(plot)

    # -------------------------------------------------------------- update

    def update(self, dt: float, season: int, raining: bool) -> list[str]:
        """Advance every plot. Returns notification strings."""
        events: list[str] = []
        day_frac = dt / self.day_length
        for plot in self.plots:
            if raining:
                plot.water = min(1.0, plot.water + dt * 0.06)
            if plot.crop is None:
                plot.water = max(0.0, plot.water - day_frac * 0.5)
                continue

            crop = CROPS[plot.crop]
            plot.water = max(0.0, plot.water - day_frac * 1.35 * crop.thirst)
            plot.food = max(0.0, plot.food - day_frac * 0.85)

            healthy = plot.water > 0.04 and plot.food > 0.02
            if healthy:
                plot.health = min(1.0, plot.health + day_frac * 1.2)
                rate = 1.0 / crop.grow_days
                if season not in crop.seasons:
                    rate *= 0.28      # out of season: slow, not impossible
                rate *= 0.75 + 0.25 * plot.water
                rate *= 0.80 + 0.20 * plot.food
                plot.progress = min(1.0, plot.progress + day_frac * rate)
            else:
                plot.health = max(0.0, plot.health - day_frac * 1.6)
                if plot.health < 0.35 and not plot._wither_warned:
                    plot._wither_warned = True
                    events.append(f"{crop.name} вянет — нужна вода!")
                if plot.health <= 0.0:
                    events.append(f"{crop.name} погиб.")
                    self.clear(plot)
                    continue

            stage = self._stage_for(crop, plot.progress)
            if stage != plot.stage:
                if plot.stage >= 0 and stage == len(crop.stages) - 1:
                    events.append(f"{crop.name} созрел!")
                self._refresh_model(plot)
        return events

    @staticmethod
    def _stage_for(crop: Crop, progress: float) -> int:
        n = len(crop.stages)
        if progress >= 1.0:
            return n - 1
        return min(n - 1, int(progress * (n - 1) + 1e-6))

    def _clear_model(self, plot: Plot):
        if plot.node is not None:
            plot.node.removeNode()
            plot.node = None

    def _refresh_model(self, plot: Plot):
        self._clear_model(plot)
        if plot.crop is None:
            return
        crop = CROPS[plot.crop]
        stage = self._stage_for(crop, plot.progress)
        plot.stage = stage
        model, scale = crop.stages[stage]
        # Wilting plants shrink and droop a little.
        scale *= 0.65 + 0.35 * plot.health
        h = (hash((round(plot.x, 2), round(plot.y, 2))) % 360)
        plot.node = place(self.root, model, (plot.x, plot.y, plot.z - 0.02), h, scale)
        if plot.health < 0.55:
            plot.node.setColorScale(0.72 + 0.28 * plot.health,
                                    0.55 + 0.45 * plot.health,
                                    0.42 + 0.35 * plot.health, 1.0)

    # ---------------------------------------------------------------- save

    def to_dict(self) -> dict:
        return {
            "plots": [
                {"x": p.x, "y": p.y, "crop": p.crop, "progress": p.progress,
                 "water": p.water, "food": p.food, "health": p.health,
                 "tilled": p.tilled}
                for p in self.plots
            ],
            "harvested": self.harvest_log,
        }

    def from_dict(self, data: dict):
        for plot in self.plots:
            self._clear_model(plot)
        self.plots.clear()
        for d in data.get("plots", []):
            plot = self.add_plot(d["x"], d["y"], d.get("tilled", True))
            plot.crop = d.get("crop")
            plot.progress = d.get("progress", 0.0)
            plot.water = d.get("water", 0.0)
            plot.food = d.get("food", 0.0)
            plot.health = d.get("health", 1.0)
            if plot.crop:
                self._refresh_model(plot)
        self.harvest_log = dict(data.get("harvested", {}))

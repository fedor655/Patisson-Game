"""Everything that wants your crops: weeds, blight and crows.

Watering used to be the only care decision a plot ever asked for. These give the
daily round a shape — hoe the weeds out, keep the beds from going soggy, and
keep the scarecrow standing, or come back to a stripped bed.
"""

from __future__ import annotations

import math
import random

from .view import Vec3, place

from ..world.layout import LAYOUT, plot_positions

# --- weeds -------------------------------------------------------------------
WEED_START = 0.22           # visible from here
WEED_SLOW = 0.35            # growth starts suffering
WEED_THIRST = 0.70          # and the weeds start drinking the plot dry

# --- blight ------------------------------------------------------------------
BLIGHT_SOGGY = 0.82         # water above this in the damp is asking for it
BLIGHT_DAILY_CHANCE = 0.55  # per in-game day, per susceptible plot

# --- crows -------------------------------------------------------------------
CROW_INTERVAL = (28.0, 65.0)     # seconds of real time between attempts
CROW_APPROACH = 5.0              # seconds circling before it settles to eat
CROW_EAT = 6.0                   # seconds on the plot before the crop is gone
CROW_SCARE_RANGE = 4.5           # how close the player must get to flush it


def _scarecrow_range() -> float:
    """Far enough to cover the garden it is standing in, and no further.

    This was 11 metres, picked by eye, while the far corner of the beds is
    14.2 m from where the scarecrow stands: it guarded thirteen of the
    twenty-four beds and the player had no way to move it. Half the farm was a
    lottery no amount of upkeep could win. Measuring it from the layout means
    moving either the beds or the scarecrow keeps the promise true.
    """
    x, y, _h = LAYOUT["scarecrow"]
    reach = max(math.hypot(px - x, py - y) for px, py in plot_positions())
    return reach + 1.0            # a little past the last bed


SCARECROW_RANGE = _scarecrow_range()
SCARECROW_WEAR_PER_DAY = 0.42
SCARECROW_RAIN_EXTRA = 0.55
SCARECROW_WORKING = 0.35


class Scarecrow:
    """Keeps crows off, but only while it is still standing up straight."""

    def __init__(self, props):
        x, y, h = LAYOUT["scarecrow"]
        self.pos = Vec3(x, y, props.ground(x, y))
        self.heading = h
        self.condition = 1.0
        self.node = None

    @property
    def working(self) -> bool:
        return self.condition >= SCARECROW_WORKING

    def protects(self, x: float, y: float) -> bool:
        if not self.working:
            return False
        return (x - self.pos.x) ** 2 + (y - self.pos.y) ** 2 < SCARECROW_RANGE ** 2

    def wear(self, day_frac: float, raining: bool) -> None:
        rate = SCARECROW_WEAR_PER_DAY + (SCARECROW_RAIN_EXTRA if raining else 0.0)
        self.condition = max(0.0, self.condition - day_frac * rate)

    def repair(self) -> bool:
        if self.condition > 0.95:
            return False
        self.condition = 1.0
        return True

    def status(self) -> str:
        if self.condition > 0.8:
            return "как новое"
        if self.working:
            return "потрёпано"
        return "развалилось — вороны не боятся"


class Crow:
    """One bird, one target plot, three phases: approach, eat, leave."""

    def __init__(self, node, plot, rng: random.Random):
        self.node = node
        self.plot = plot
        self.rng = rng
        self.phase = "approach"
        self.timer = CROW_APPROACH
        self.angle = rng.uniform(0, math.tau)
        self.height = 6.0
        self.landed = False

    def update(self, dt: float, player_pos: Vec3) -> str | None:
        self.timer -= dt
        target = self.plot.pos

        if self.phase == "approach":
            # Spiral down onto the plot.
            self.angle += dt * 1.6
            t = max(0.0, self.timer / CROW_APPROACH)
            radius = 1.2 + 5.5 * t
            self.height = 0.35 + 5.6 * t
            self.node.setPos(target.x + math.cos(self.angle) * radius,
                             target.y + math.sin(self.angle) * radius,
                             target.z + self.height)
            self.node.setH(math.degrees(self.angle) + 90.0)
            if self.timer <= 0.0:
                self.phase = "eat"
                self.timer = CROW_EAT
                self.landed = True          # the caw that announces it
        elif self.phase == "eat":
            # Hop about on the plot, pecking.
            bob = abs(math.sin(self.timer * 5.5)) * 0.09
            self.node.setPos(target.x, target.y, target.z + 0.06 + bob)
            self.node.setH(math.degrees(math.sin(self.timer * 1.3) * 40.0))
            if self.timer <= 0.0:
                return "stole"
        else:  # leaving
            self.angle += dt * 1.1
            self.height += dt * 4.5
            self.node.setPos(self.node.getX() + math.cos(self.angle) * dt * 6.0,
                             self.node.getY() + math.sin(self.angle) * dt * 6.0,
                             target.z + self.height)
            if self.height > 14.0:
                return "gone"

        if self.phase in ("approach", "eat"):
            d = (player_pos.x - target.x) ** 2 + (player_pos.y - target.y) ** 2
            if d < CROW_SCARE_RANGE ** 2:
                self.flee()
                return "scared"
        return None

    def flee(self) -> None:
        self.phase = "leaving"
        self.timer = 9e9


class Pests:
    """Owns the scarecrow and whatever crows are currently in the air."""

    def __init__(self, base, world, props, farm, day_length: float,
                 rng: random.Random | None = None):
        self.base = base
        self.world = world
        self.props = props
        self.farm = farm
        self.day_length = day_length
        self.rng = rng or random.Random(4242)
        self.scarecrow = Scarecrow(props)
        self.crows: list[Crow] = []
        self.timer = self.rng.uniform(*CROW_INTERVAL)
        self.root = world.root.attachNewNode("pests")
        props.pipeline.apply_scene_shader(self.root, wind=0.25, wind_pivot=0.2)

    # ---------------------------------------------------------------- crows

    def _ripe_unprotected(self):
        out = []
        for plot in self.farm.plots:
            if not plot.ripe:
                continue
            if self.scarecrow.protects(plot.x, plot.y):
                continue
            if any(c.plot is plot for c in self.crows):
                continue
            out.append(plot)
        return out

    def _spawn_crow(self) -> None:
        targets = self._ripe_unprotected()
        if not targets:
            return
        plot = self.rng.choice(targets)
        node = place(self.root, "crow", (plot.x, plot.y, plot.z + 6.0), 0, 1.0)
        self.crows.append(Crow(node, plot, self.rng))

    def scare_all(self) -> int:
        scared = sum(1 for c in self.crows if c.phase != "leaving")
        for c in self.crows:
            c.flee()
        return scared

    # --------------------------------------------------------------- update

    def update(self, dt: float, player_pos: Vec3, raining: bool) -> list[str]:
        events: list[str] = []
        day_frac = dt / self.day_length
        self.scarecrow.wear(day_frac, raining)

        self.timer -= dt
        if self.timer <= 0.0:
            self.timer = self.rng.uniform(*CROW_INTERVAL)
            self._spawn_crow()

        for crow in list(self.crows):
            result = crow.update(dt, player_pos)
            if crow.landed:
                crow.landed = False
                self.caw(crow.node.getPos())
            if result == "stole":
                crop = crow.plot.crop
                self.farm.clear(crow.plot)
                crow.flee()
                from .farming import CROPS
                name = CROPS[crop].name if crop in CROPS else "урожай"
                events.append(f"Ворона склевала {name}!")
            elif result == "gone":
                crow.node.removeNode()
                self.crows.remove(crow)
            elif result == "scared":
                self.caw(crow.node.getPos())
                events.append("Ворона улетела.")
        return events

    def caw(self, pos) -> None:
        """Overridden by the app to place the sound; a no-op without audio."""

    # ----------------------------------------------------------------- save

    def to_dict(self) -> dict:
        return {"scarecrow": self.scarecrow.condition}

    def from_dict(self, data: dict) -> None:
        from .state import as_dict, as_float

        condition = as_float(as_dict(data).get("scarecrow"), 1.0)
        self.scarecrow.condition = min(1.0, max(0.0, condition))

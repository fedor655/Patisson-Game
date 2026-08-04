"""Loads the generated .glb models and dresses the farm with them."""

from __future__ import annotations

import math
import random
from pathlib import Path

import gltf
from panda3d.core import NodePath, Vec3, Vec4

from ..engine.pipeline import MASK_SHADOW

MODEL_DIR = Path(__file__).resolve().parents[2] / "assets" / "models"

_cache: dict[str, NodePath] = {}


def load(name: str) -> NodePath:
    """Load a model once and hand out cheap instanced copies."""
    if name not in _cache:
        path = MODEL_DIR / f"{name}.glb"
        if not path.exists():
            raise FileNotFoundError(
                f"missing model {path}. Run: python -m patisson2.tools.make_assets")
        np_ = NodePath(gltf.load_model(str(path)))
        np_.setName(name)
        np_.clearModelNodes()
        np_.flattenStrong()
        _cache[name] = np_
    return _cache[name]


def place(parent: NodePath, name: str, pos, h: float = 0.0, scale: float = 1.0,
          p: float = 0.0) -> NodePath:
    node = parent.attachNewNode(f"{name}-inst")
    load(name).instanceTo(node)
    node.setPos(*pos)
    node.setHpr(h, p, 0)
    node.setScale(scale)
    return node


# Where the interesting things live. Positions are chosen to sit in the flat
# farm basin around the origin.
LAYOUT = {
    "house": (16.0, -13.0, 205.0),
    "barn": (-19.0, -16.0, 62.0),
    "well": (7.5, 7.0, 0.0),
    "market_stall": (-13.0, -2.0, 108.0),
    "signpost": (2.0, -8.5, 24.0),
    "scarecrow": (-4.5, 12.0, 200.0),
}

# The tilled plots the player starts with: (x, y).
PLOT_ORIGIN = (-3.0, 1.0)
PLOT_COLS, PLOT_ROWS = 6, 4
PLOT_SPACING = 1.5


def plot_positions():
    ox, oy = PLOT_ORIGIN
    for j in range(PLOT_ROWS):
        for i in range(PLOT_COLS):
            yield (ox + i * PLOT_SPACING, oy + j * PLOT_SPACING)


class Props:
    """Everything static in the world plus the little wandering things."""

    def __init__(self, base, world, pipeline):
        self.base = base
        self.world = world
        self.pipeline = pipeline
        self.root = world.root.attachNewNode("props")
        self.foliage = world.root.attachNewNode("foliage")
        # Anything that moves has to stay out of the flatten pass below.
        self.dynamic = world.root.attachNewNode("dynamic")
        self.animals: list = []
        self.lanterns: list = []
        self.rng = random.Random(world.cfg.seed)

        pipeline.apply_scene_shader(self.root, micro_detail=0.10)
        pipeline.apply_scene_shader(self.foliage, wind=0.55, wind_pivot=0.4,
                                    micro_detail=0.06)

        pipeline.apply_scene_shader(self.dynamic, micro_detail=0.08)

        self._place_buildings()
        self._place_fences()
        self._scatter_nature()
        self._place_animals()
        self._place_lanterns()
        self._batch_static()

    def _batch_static(self):
        """Merge the static dressing into a handful of geometry nodes.

        Every tree, fence and rock was its own NodePath, so a few hundred draw
        calls and cull traversals per frame — which on this scene costs far more
        than the triangles themselves. None of it moves, so it can be baked.
        """
        for node in (self.root, self.foliage, self.small_foliage):
            node.clearModelNodes()
            node.flattenStrong()

    def ground(self, x, y):
        return self.world.height_at(x, y)

    # ---------------------------------------------------------------- pieces

    def _place_buildings(self):
        for name, (x, y, h) in LAYOUT.items():
            place(self.root, name, (x, y, self.ground(x, y) - 0.05), h)
        # A few crates and barrels for dressing.
        for x, y, name in ((14.0, -8.6, "crate"), (13.2, -7.6, "crate"),
                           (-16.5, -12.0, "barrel"), (-15.6, -12.4, "barrel"),
                           (8.6, 6.2, "bucket"), (-11.6, -3.4, "crate")):
            place(self.root, name, (x, y, self.ground(x, y)),
                  self.rng.uniform(0, 360))

    def _place_fences(self):
        """Fence the vegetable garden, leaving a gap to walk through."""
        ox, oy = PLOT_ORIGIN
        w = (PLOT_COLS - 1) * PLOT_SPACING
        d = (PLOT_ROWS - 1) * PLOT_SPACING
        cx, cy = ox + w / 2, oy + d / 2
        hw, hd = w / 2 + 1.6, d / 2 + 1.6
        step = 2.4
        segments = []
        nx = max(int(round(hw * 2 / step)), 1)
        ny = max(int(round(hd * 2 / step)), 1)
        for i in range(nx):
            x = cx - hw + step * (i + 0.5)
            segments.append((x, cy - hd, 0.0))
            segments.append((x, cy + hd, 0.0))
        for j in range(ny):
            y = cy - hd + step * (j + 0.5)
            segments.append((cx - hw, y, 90.0))
            segments.append((cx + hw, y, 90.0))
        # Leave the segment nearest the house out as a gateway.
        gate = min(segments, key=lambda s: (s[0] - 8.0) ** 2 + (s[1] + 4.0) ** 2)
        for x, y, h in segments:
            if (x, y, h) == gate:
                continue
            place(self.root, "fence", (x, y, self.ground(x, y) - 0.06), h)

    def _scatter_nature(self):
        r = self.rng
        w = self.world
        cfg = w.cfg

        def free(x, y, clearance=6.0):
            if w.terrain.height_at(x, y) < cfg.water_level + 0.5:
                return False
            if w.terrain.slope_at(x, y) > 0.42:
                return False
            for name, (bx, by, _h) in LAYOUT.items():
                if (x - bx) ** 2 + (y - by) ** 2 < clearance ** 2:
                    return False
            # keep the vegetable plot clear
            if -8 < x < 8 and -4 < y < 10:
                return False
            return True

        # Trees: a ring of woodland around the farm, thinning towards the middle.
        placed = 0
        attempts = 0
        while placed < 115 and attempts < 6000:
            attempts += 1
            a = r.uniform(0, math.tau)
            d = 26.0 + abs(r.gauss(0, 1)) * 52.0
            x, y = math.cos(a) * d, math.sin(a) * d
            if abs(x) > 150 or abs(y) > 150 or not free(x, y, 9.0):
                continue
            kind = r.choices(["tree_oak", "tree_oak2", "tree_birch", "tree_pine"],
                             weights=[3, 3, 2, 2])[0]
            place(self.foliage, kind, (x, y, self.ground(x, y) - 0.1),
                  r.uniform(0, 360), r.uniform(0.8, 1.35))
            placed += 1

        for _ in range(90):
            a, d = r.uniform(0, math.tau), r.uniform(8, 105)
            x, y = math.cos(a) * d, math.sin(a) * d
            if free(x, y, 4.0):
                place(self.foliage, "bush", (x, y, self.ground(x, y) - 0.05),
                      r.uniform(0, 360), r.uniform(0.7, 1.3))

        # Flowers and reeds are too small to read as shadows but not too small
        # to cost a shadow-map pass, so they are excluded from it.
        self.small_foliage = self.world.root.attachNewNode("small-foliage")
        self.small_foliage.hide(MASK_SHADOW)
        self.pipeline.apply_scene_shader(self.small_foliage, wind=0.7,
                                         wind_pivot=0.02)
        for _ in range(130):
            a, d = r.uniform(0, math.tau), r.uniform(5, 90)
            x, y = math.cos(a) * d, math.sin(a) * d
            if free(x, y, 4.0):
                place(self.small_foliage, "flowers", (x, y, self.ground(x, y)),
                      r.uniform(0, 360), r.uniform(0.7, 1.5))

        for _ in range(70):
            a, d = r.uniform(0, math.tau), r.uniform(10, 120)
            x, y = math.cos(a) * d, math.sin(a) * d
            if free(x, y, 5.0):
                place(self.root, "rock_small" if r.random() < 0.7 else "rock_large",
                      (x, y, self.ground(x, y) - 0.08), r.uniform(0, 360),
                      r.uniform(0.6, 1.4))

        # Reeds and lily pads around the pond.
        from .terrain import POND_CENTRE, POND_RADIUS
        px, py = POND_CENTRE
        for _ in range(110):
            a = r.uniform(0, math.tau)
            d = POND_RADIUS * r.uniform(0.72, 1.12)
            x, y = px + math.cos(a) * d, py + math.sin(a) * d
            h = w.terrain.height_at(x, y)
            if cfg.water_level - 0.9 < h < cfg.water_level + 0.45:
                place(self.small_foliage, "reed", (x, y, max(h, cfg.water_level - 0.25)),
                      r.uniform(0, 360), r.uniform(0.7, 1.3))
        for _ in range(16):
            a = r.uniform(0, math.tau)
            d = POND_RADIUS * r.uniform(0.1, 0.7)
            x, y = px + math.cos(a) * d, py + math.sin(a) * d
            if w.terrain.height_at(x, y) < cfg.water_level - 0.5:
                place(self.small_foliage, "lilypad", (x, y, cfg.water_level + 0.03),
                      r.uniform(0, 360), r.uniform(0.7, 1.2))

    def _place_animals(self):
        r = self.rng
        for i in range(7):
            x = -19.0 + r.uniform(-6, 6)
            y = -16.0 + r.uniform(4, 10)
            node = place(self.dynamic, "chicken", (x, y, self.ground(x, y)),
                         r.uniform(0, 360), r.uniform(0.85, 1.15))
            self.animals.append(Wanderer(node, self.world, (x, y), 5.0, 0.75,
                                         bob=0.10, seed=i))
        for i in range(3):
            x = -26.0 + r.uniform(-5, 5)
            y = -4.0 + r.uniform(-6, 6)
            node = place(self.dynamic, "cow", (x, y, self.ground(x, y)),
                         r.uniform(0, 360), r.uniform(0.92, 1.08))
            self.animals.append(Wanderer(node, self.world, (x, y), 8.0, 0.45,
                                         bob=0.05, seed=20 + i))
        node = place(self.dynamic, "cat", (14.0, -9.5, self.ground(14.0, -9.5)), 40)
        self.animals.append(Wanderer(node, self.world, (14.0, -9.5), 7.0, 0.9,
                                     bob=0.06, seed=40))
        for i in range(14):
            a, d = r.uniform(0, math.tau), r.uniform(4, 30)
            x, y = math.cos(a) * d, math.sin(a) * d
            node = place(self.dynamic, "butterfly", (x, y, self.ground(x, y) + 1.0),
                         r.uniform(0, 360), r.uniform(0.8, 1.4))
            self.animals.append(Flutterer(node, self.world, (x, y), seed=60 + i))

    def _place_lanterns(self):
        """Four lanterns that become the game's point lights after dark."""
        spots = [(2.0, -7.0), (8.6, 5.6), (-12.0, -3.6), (14.6, -9.0)]
        for i, (x, y) in enumerate(spots):
            z = self.ground(x, y)
            post = place(self.root, "signpost", (x, y, z), self.rng.uniform(0, 360),
                         0.62) if i == 99 else None
            node = place(self.root, "lantern", (x, y, z + 1.35), 0, 1.0)
            self.lanterns.append((node, Vec3(x, y, z + 1.45)))

    # ---------------------------------------------------------------- update

    # Tree and bush colours are baked into the models, so the season shows
    # through a colour scale on the foliage roots.
    SEASON_TINT = {
        0: (1.10, 1.12, 0.88, 1.0),     # spring: fresh, yellow-green
        1: (1.0, 1.0, 1.0, 1.0),        # summer: as modelled
        2: (1.85, 0.92, 0.30, 1.0),     # autumn: warm and turning
        3: (0.55, 0.62, 0.74, 1.0),     # winter: cold and drained
    }

    def apply_season(self, season: int) -> None:
        tint = self.SEASON_TINT.get(season, (1.0, 1.0, 1.0, 1.0))
        for node in (self.foliage, self.small_foliage):
            node.setColorScale(*tint)

    def update(self, dt: float, time: float, night: float):
        for a in self.animals:
            a.update(dt, time)
        for i, (node, pos) in enumerate(self.lanterns):
            if i < len(self.pipeline.point_lights):
                warm = Vec3(1.0, 0.62, 0.26) * (5.5 * night)
                self.pipeline.set_point_light(i, pos, warm, (1.0, 0.20, 0.09))


class Wanderer:
    """Aimless animal that pootles about near its home spot."""

    def __init__(self, node, world, home, radius, speed, bob=0.0, seed=0):
        self.node = node
        self.world = world
        self.home = home
        self.radius = radius
        self.speed = speed
        self.bob = bob
        self.rng = random.Random(seed)
        self.base_scale = node.getScale()[0]
        self.target = self._pick()
        self.wait = self.rng.uniform(0.5, 3.0)
        self.phase = self.rng.uniform(0, 10)

    def _pick(self):
        a = self.rng.uniform(0, math.tau)
        d = self.rng.uniform(0, self.radius)
        return (self.home[0] + math.cos(a) * d, self.home[1] + math.sin(a) * d)

    def update(self, dt, time):
        p = self.node.getPos()
        if self.wait > 0:
            self.wait -= dt
        else:
            dx = self.target[0] - p.x
            dy = self.target[1] - p.y
            dist = math.hypot(dx, dy)
            if dist < 0.25:
                self.target = self._pick()
                self.wait = self.rng.uniform(0.8, 4.5)
            else:
                step = min(self.speed * dt, dist)
                p.x += dx / dist * step
                p.y += dy / dist * step
                # Turn smoothly towards the heading.
                want = math.degrees(math.atan2(dy, dx)) - 90.0
                cur = self.node.getH()
                delta = (want - cur + 180) % 360 - 180
                self.node.setH(cur + delta * min(dt * 4.0, 1.0))
        z = self.world.height_at(p.x, p.y)
        if self.bob and self.wait <= 0:
            z += abs(math.sin((time + self.phase) * 7.0)) * self.bob
        self.node.setPos(p.x, p.y, z)


class Flutterer:
    """Butterflies: a lazy horizontal drift with a bobbing flight path."""

    def __init__(self, node, world, home, seed=0):
        self.node = node
        self.world = world
        self.home = home
        self.rng = random.Random(seed)
        self.phase = self.rng.uniform(0, 20)
        self.r1 = self.rng.uniform(1.5, 4.5)
        self.r2 = self.rng.uniform(1.0, 3.5)
        self.speed = self.rng.uniform(0.25, 0.55)

    def update(self, dt, time):
        t = (time + self.phase) * self.speed
        x = self.home[0] + math.cos(t) * self.r1 + math.cos(t * 2.3) * 0.6
        y = self.home[1] + math.sin(t * 1.3) * self.r2
        z = self.world.height_at(x, y) + 0.85 + math.sin(t * 3.1) * 0.35
        self.node.setPos(x, y, z)
        self.node.setH(math.degrees(-t) * 30 % 360)
        self.node.setR(math.sin(t * 9.0) * 28.0)

"""Loads the generated .glb models and dresses the farm with them."""

from __future__ import annotations

import math
import random
from pathlib import Path

import gltf
from panda3d.core import NodePath, Vec3

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


from .layout import (  # noqa: F401  (re-exported for callers)
    BUILDING_SHAPES,
    LAYOUT,
    PLOT_ORIGIN,
    PLOT_COLS,
    PLOT_ROWS,
    PLOT_SPACING,
    plot_positions,
)


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
        # Trees are flattened into tiles below, so their positions would be
        # lost. The soundscape needs them: birdsong comes out of a real tree.
        self.trees: list[tuple[float, float, float]] = []
        self.rng = random.Random(world.cfg.seed)

        pipeline.apply_scene_shader(self.root, micro_detail=0.10)
        pipeline.apply_scene_shader(self.foliage, wind=0.55, wind_pivot=0.4,
                                    micro_detail=0.06)

        pipeline.apply_scene_shader(self.dynamic, micro_detail=0.08)

        self.bed_pos = None
        self.hearth_pos = None
        self.barn_light = None
        self._place_buildings()
        self._place_fences()
        self._scatter_nature()
        self._place_animals()
        self._place_lanterns()
        self._batch_static()

    # Static dressing is baked per grid cell of this size, in metres.
    BATCH_TILE = 40.0

    def _batch_static(self):
        """Bake the static dressing into one node per spatial tile.

        Every tree, fence and rock started as its own NodePath — a few hundred
        draw calls and cull traversals a frame. Flattening them all into a
        single node fixed that but destroyed frustum culling: one node spanning
        the whole map is either wholly in or wholly out, so every tree in the
        world was redrawn into the sun's shadow map each frame. Tiling gives
        both — a handful of draw calls *and* bounds tight enough to cull.
        """
        for node in (self.root, self.foliage, self.small_foliage):
            self._batch_by_tile(node)

    def _batch_by_tile(self, root: NodePath) -> int:
        tile = self.BATCH_TILE
        buckets: dict[tuple[int, int], list[NodePath]] = {}
        for child in root.getChildren():
            p = child.getPos(root)
            key = (int(math.floor(p.x / tile)), int(math.floor(p.y / tile)))
            buckets.setdefault(key, []).append(child)
        for (tx, ty), nodes in buckets.items():
            holder = root.attachNewNode(f"tile{tx}_{ty}")
            for n in nodes:
                n.reparentTo(holder)
            holder.clearModelNodes()
            holder.flattenStrong()
        return len(buckets)

    def _local_to_world(self, building: str, local):
        """Map a point in a building's own frame out into the world."""
        import math as _m
        bx, by, bh = LAYOUT[building]
        a = _m.radians(bh)
        ca, sa = _m.cos(a), _m.sin(a)
        lx, ly = local
        wx = bx + lx * ca - ly * sa
        wy = by + lx * sa + ly * ca
        return (wx, wy, self.ground(wx, wy))

    def ground(self, x, y):
        return self.world.height_at(x, y)

    # ---------------------------------------------------------------- pieces

    def _place_buildings(self):
        for name, (x, y, h) in LAYOUT.items():
            node = place(self.root, name, (x, y, self.ground(x, y) - 0.05), h)
            shape = BUILDING_SHAPES.get(name)
            if shape is not None:
                w, d, door = shape
                self.world.blockers.add_walls(x, y, h, w, d, thickness=0.34,
                                              door_side="front", door_width=door)
                # Blue channel of the field mask means "no grass here" — the
                # blades are placed on the GPU and know nothing about walls.
                self.world.mask.paint(x, y, math.hypot(w, d) / 2.0 + 0.6, 2,
                                      falloff=False)
        # Interior landmarks, in each building's own frame.
        self.bed_pos = self._local_to_world("house", (-1.55, 2.05))
        self.hearth_pos = self._local_to_world("house", (2.6, 1.2))
        self.barn_light = self._local_to_world("barn", (0.0, 1.0))
        # Solid dressing.
        wx, wy, _wh = LAYOUT["well"]
        self.world.blockers.add_post(wx, wy, 0.95, top=1.2)
        sx, sy, sh = LAYOUT["market_stall"]
        self.world.blockers.add_box(sx, sy, 1.25, 0.55, sh, top=1.3)
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
            self.world.blockers.add_box(x, y, 1.2, 0.09, h, top=1.1)

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
            # Draw in the same order as before — heading, then scale — so the
            # woodland comes out identical to every previous build.
            heading = r.uniform(0, 360)
            scale = r.uniform(0.8, 1.35)
            place(self.foliage, kind, (x, y, self.ground(x, y) - 0.1),
                  heading, scale)
            self.world.blockers.add_post(x, y, 0.40, top=2.6)
            # Sing from up in the canopy, not from the trunk.
            self.trees.append((x, y, self.ground(x, y) + 4.2 * scale))
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
        """Lanterns light the yard after dark; the hearth burns indoors always.

        There are only four point lights, so rather than pinning them to fixed
        lanterns the update picks whichever emitters are nearest the player.
        """
        spots = [(2.0, -7.0), (8.6, 5.6), (-12.0, -3.6), (14.6, -9.0),
                 (-17.0, -12.4), (12.6, -16.2)]
        for x, y in spots:
            z = self.ground(x, y)
            place(self.root, "lantern", (x, y, z + 1.35), 0, 1.0)
            self.lanterns.append((Vec3(x, y, z + 1.45), False))
        # A fire inside the house: the only thing that makes the interior
        # readable, since no sunlight reaches in through solid walls.
        if self.hearth_pos is not None:
            hx, hy, hz = self.hearth_pos
            self.lanterns.append((Vec3(hx, hy, hz + 1.05), True))
        if self.barn_light is not None:
            bx, by, bz = self.barn_light
            self.lanterns.append((Vec3(bx, by, bz + 2.2), True))

    # ---------------------------------------------------------------- update

    # Tree and bush colours are baked into the models, so the season shows
    # through a colour scale on the foliage roots. A scale can only multiply —
    # it cannot desaturate — so turning a saturated green canopy golden needs a
    # much larger red multiplier than the numbers look like they should be.
    SEASON_TINT = {
        0: (1.14, 1.14, 0.84, 1.0),     # spring: fresh, yellow-green
        1: (1.0, 1.0, 1.0, 1.0),        # summer: as modelled
        2: (3.10, 1.10, 0.20, 1.0),     # autumn: golden
        3: (0.62, 0.70, 0.84, 1.0),     # winter: cold and drained
    }

    def apply_season(self, season: int) -> None:
        tint = self.SEASON_TINT.get(season, (1.0, 1.0, 1.0, 1.0))
        for node in (self.foliage, self.small_foliage):
            node.setColorScale(*tint)

    def update(self, dt: float, time: float, night: float, player_pos=None):
        for a in self.animals:
            a.update(dt, time)

        slots = len(self.pipeline.point_lights)
        if player_pos is None:
            lit = self.lanterns[:slots]
        else:
            # Nearest emitters win the limited slots. Indoor fires always
            # count; outdoor lanterns only once it is dark enough to matter.
            candidates = [(pos, indoor) for pos, indoor in self.lanterns
                          if indoor or night > 0.03]
            candidates.sort(key=lambda e: (e[0] - player_pos).lengthSquared())
            lit = candidates[:slots]

        for i in range(slots):
            if i < len(lit):
                pos, indoor = lit[i]
                strength = 6.5 if indoor else 5.5 * night
                warm = Vec3(1.0, 0.58, 0.24) * strength
                self.pipeline.set_point_light(i, pos, warm, (1.0, 0.22, 0.10))
            else:
                self.pipeline.set_point_light(i, Vec3(0, 0, -500),
                                              Vec3(0, 0, 0), (1.0, 1.0, 1.0))


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

"""A drawn map of the farm, with live markers and travel between landmarks.

The image is baked once from the terrain height field — the same data the
ground shader reads — so the map can never disagree with the world. Markers are
GUI nodes laid over it and moved every frame the map is open.
"""

from __future__ import annotations

import math

import numpy as np
from direct.gui.DirectGui import DirectFrame
from direct.gui.OnscreenImage import OnscreenImage
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import SamplerState, TextNode, Texture, TransparencyAttrib

from ..world.layout import (BUILDING_SHAPES, LAYOUT, PLOT_COLS, PLOT_ORIGIN,
                            PLOT_ROWS, PLOT_SPACING)
from ..world.terrain import POND_CENTRE

MAP_RES = 512
# Half-width of the area drawn, in metres. At 120 the farm was a thumbnail in
# the middle of an empty meadow: everything a player needs is inside 70 m.
MAP_EXTENT = 72.0

INK = (0.96, 0.96, 0.94, 1)
DIM = (0.78, 0.80, 0.78, 1)
GOLD = (1.0, 0.85, 0.42, 1)
GREEN = (0.66, 0.92, 0.60, 1)

# Landmarks you can travel to: key -> (label, world xy)
def _landmarks():
    marks = [
        ("Дом", LAYOUT["house"][:2], "house"),
        ("Амбар", LAYOUT["barn"][:2], "barn"),
        ("Колодец", LAYOUT["well"][:2], "well"),
        ("Прилавок", LAYOUT["market_stall"][:2], "stall"),
        ("Котёл", LAYOUT["cooking_pot"][:2], "pot"),
        ("Пугало", LAYOUT["scarecrow"][:2], "scare"),
        ("Пруд", POND_CENTRE, "pond"),
        ("Грядки", (0.75, 3.25), "plots"),
    ]
    return marks


MARKER_COLOURS = {
    "house": (0.95, 0.62, 0.45, 1),
    "barn": (0.90, 0.42, 0.38, 1),
    "well": (0.55, 0.78, 1.00, 1),
    "stall": (1.00, 0.84, 0.44, 1),
    "pot": (0.85, 0.70, 0.55, 1),
    "scare": (0.80, 0.80, 0.55, 1),
    "pond": (0.45, 0.75, 0.95, 1),
    "plots": (0.66, 0.92, 0.60, 1),
}

# Walking pace used to charge in-game time for travelling, metres per second.
TRAVEL_SPEED = 3.4


def _px(v: float) -> float:
    """World metres -> pixel coordinate in the map image."""
    return (v + MAP_EXTENT) / (2.0 * MAP_EXTENT) * (MAP_RES - 1)


def _stamp_disc(rgb, x: float, y: float, radius: float, colour, softness=0.6):
    """Paint a soft disc of world-space radius at a world-space point."""
    cx, cy = _px(x), _px(y)
    r = radius / (2.0 * MAP_EXTENT) * (MAP_RES - 1)
    lo_x, hi_x = int(max(0, cx - r - 1)), int(min(MAP_RES, cx + r + 2))
    lo_y, hi_y = int(max(0, cy - r - 1)), int(min(MAP_RES, cy + r + 2))
    if lo_x >= hi_x or lo_y >= hi_y:
        return
    gx = np.arange(lo_x, hi_x)[:, None] - cx
    gy = np.arange(lo_y, hi_y)[None, :] - cy
    d = np.sqrt(gx * gx + gy * gy)
    a = np.clip((r - d) / max(r * softness, 0.75), 0.0, 1.0)[..., None]
    patch = rgb[lo_x:hi_x, lo_y:hi_y]
    rgb[lo_x:hi_x, lo_y:hi_y] = patch * (1 - a) + np.array(colour, np.float32) * a


def _stamp_rect(rgb, x: float, y: float, w: float, d: float, heading: float,
                colour):
    """Paint a rotated rectangle — a building footprint."""
    a = math.radians(heading)
    ca, sa = math.cos(a), math.sin(a)
    span = (abs(w * ca) + abs(d * sa) + abs(w * sa) + abs(d * ca)) / 2.0
    cx, cy = _px(x), _px(y)
    r = span / (2.0 * MAP_EXTENT) * (MAP_RES - 1)
    lo_x, hi_x = int(max(0, cx - r - 1)), int(min(MAP_RES, cx + r + 2))
    lo_y, hi_y = int(max(0, cy - r - 1)), int(min(MAP_RES, cy + r + 2))
    if lo_x >= hi_x or lo_y >= hi_y:
        return
    scale = (2.0 * MAP_EXTENT) / (MAP_RES - 1)
    wx = (np.arange(lo_x, hi_x)[:, None] - cx) * scale
    wy = (np.arange(lo_y, hi_y)[None, :] - cy) * scale
    # Into the building's own frame, the way props place their furniture.
    lx = wx * ca + wy * sa
    ly = -wx * sa + wy * ca
    inside = (np.abs(lx) <= w / 2.0) & (np.abs(ly) <= d / 2.0)
    patch = rgb[lo_x:hi_x, lo_y:hi_y]
    rgb[lo_x:hi_x, lo_y:hi_y] = np.where(inside[..., None],
                                         np.array(colour, np.float32), patch)


def build_map_texture(terrain, cfg, props=None) -> Texture:
    """Shade the height field into a paper-map image."""
    res = MAP_RES
    xs = np.linspace(-MAP_EXTENT, MAP_EXTENT, res)
    # Sample the baked lookup rather than re-running the noise.
    lut = terrain.heights
    lut_res = terrain.lut_res
    u = (xs - terrain.lut_min) / terrain.lut_size * (lut_res - 1)
    u = np.clip(u, 0, lut_res - 1.001)
    i0 = u.astype(np.int32)
    fu = (u - i0).astype(np.float32)

    def sample(ix, iy):
        return lut[ix[:, None], iy[None, :]]

    i1 = np.minimum(i0 + 1, lut_res - 1)
    h = (sample(i0, i0) * (1 - fu)[:, None] * (1 - fu)[None, :]
         + sample(i1, i0) * fu[:, None] * (1 - fu)[None, :]
         + sample(i0, i1) * (1 - fu)[:, None] * fu[None, :]
         + sample(i1, i1) * fu[:, None] * fu[None, :])

    water = cfg.water_level
    # Slope shading: a low sun from the north-west, which is how paper maps read.
    # This modulates *around* 1.0 — the colours below are picked as they should
    # appear on screen, and an 8-bit texture is read back as sRGB, so shading
    # them down towards zero the way a lighting term would just makes mud.
    gx, gy = np.gradient(h.astype(np.float32))
    step = (2.0 * MAP_EXTENT) / res
    shade = np.clip(1.0 - (gx - gy) / (step * 3.0), 0.55, 1.42)

    rgb = np.zeros((res, res, 3), dtype=np.float32)
    land = h >= water
    depth = np.clip((water - h) / 2.6, 0.0, 1.0)
    # Water: shallow teal to deep blue.
    rgb[..., 0] = np.where(land, 0.0, 0.36 - 0.20 * depth)
    rgb[..., 1] = np.where(land, 0.0, 0.64 - 0.30 * depth)
    rgb[..., 2] = np.where(land, 0.0, 0.70 - 0.16 * depth)

    # Land: sand at the waterline, meadow, then bare hill.
    above = np.clip((h - water) / 12.0, 0.0, 1.0)
    sand = np.clip(1.0 - (h - water) / 0.9, 0.0, 1.0)
    meadow = np.stack([np.full_like(h, 0.47), np.full_like(h, 0.63),
                       np.full_like(h, 0.34)], axis=-1)
    hill = np.stack([np.full_like(h, 0.66), np.full_like(h, 0.60),
                     np.full_like(h, 0.45)], axis=-1)
    sandc = np.stack([np.full_like(h, 0.82), np.full_like(h, 0.76),
                      np.full_like(h, 0.57)], axis=-1)
    ground = meadow * (1 - above[..., None]) + hill * above[..., None]
    ground = ground * (1 - sand[..., None]) + sandc * sand[..., None]
    rgb = np.where(land[..., None], ground, rgb)
    rgb *= shade[..., None]

    # The height field alone draws a bare meadow. Everything a player uses to
    # find their way — the wood, the buildings, the beds — is props data, and
    # stamping it here keeps the map honest: it is the same list the world was
    # built from, not a second drawing that can drift out of step.
    if props is not None:
        for tx, ty, _tz in getattr(props, "trees", ()):
            _stamp_disc(rgb, tx, ty, 1.9, (0.24, 0.40, 0.22))
        ox, oy = PLOT_ORIGIN
        _stamp_rect(rgb, ox + (PLOT_COLS - 1) * PLOT_SPACING / 2.0,
                    oy + (PLOT_ROWS - 1) * PLOT_SPACING / 2.0,
                    (PLOT_COLS - 1) * PLOT_SPACING + 3.2,
                    (PLOT_ROWS - 1) * PLOT_SPACING + 3.2, 0.0,
                    (0.44, 0.32, 0.22))
        for name, (w, d, _door) in BUILDING_SHAPES.items():
            bx, by, bh = LAYOUT[name]
            _stamp_rect(rgb, bx, by, w + 0.6, d + 0.6, bh, (0.30, 0.26, 0.24))
            _stamp_rect(rgb, bx, by, w - 0.8, d - 0.8, bh,
                        (0.72, 0.34, 0.28) if name == "house"
                        else (0.62, 0.28, 0.26))

    # A soft parchment vignette so it reads as a drawing, not a data plot.
    yy, xx = np.mgrid[0:res, 0:res]
    r = np.sqrt(((xx / res) - 0.5) ** 2 + ((yy / res) - 0.5) ** 2)
    rgb *= np.clip(1.06 - r * 0.34, 0.0, 1.2)[..., None]
    rgb = np.clip(rgb, 0.0, 1.0)

    data = np.zeros((res, res, 4), dtype=np.uint8)
    # The sampling above is indexed [x][y]; Panda wants rows of y.
    flipped = np.transpose(rgb, (1, 0, 2))
    data[..., 0] = (flipped[..., 2] * 255).astype(np.uint8)   # B
    data[..., 1] = (flipped[..., 1] * 255).astype(np.uint8)   # G
    data[..., 2] = (flipped[..., 0] * 255).astype(np.uint8)   # R
    data[..., 3] = 255

    tex = Texture("worldmap")
    tex.setup2dTexture(res, res, Texture.TUnsignedByte, Texture.FRgba)
    tex.setRamImage(np.ascontiguousarray(data).tobytes())
    tex.setMinfilter(SamplerState.FT_linear)
    tex.setMagfilter(SamplerState.FT_linear)
    return tex


class WorldMap:
    """The map screen: image, markers, and a travel cursor."""

    SIZE = 0.72          # half-height on screen, in aspect2d units

    def __init__(self, base, hud, world, cfg, props=None):
        self.base = base
        self.hud = hud
        self.world = world
        self.cfg = cfg
        self.visible = False
        self.cursor = 0
        self.landmarks = _landmarks()

        self.texture = build_map_texture(world.terrain, cfg, props)

        self.root = base.aspect2d.attachNewNode("worldmap")
        self.root.hide()
        self.backdrop = DirectFrame(parent=self.root,
                                    frameColor=(0.05, 0.05, 0.06, 0.86),
                                    frameSize=(-1.78, 1.78, -1.0, 1.0))
        # Everything else on this screen sits in the "fixed" bin, which draws
        # after the default one — without pinning the scrim below them it would
        # be painted over the map instead of behind it.
        self.backdrop.setBin("fixed", 0)
        self.image = OnscreenImage(parent=self.root, image=self.texture,
                                   pos=(-0.42, 0, 0.02),
                                   scale=(self.SIZE, 1, self.SIZE))
        self.image.setTransparency(TransparencyAttrib.MAlpha)
        self.frame = DirectFrame(parent=self.root, frameColor=(0.75, 0.66, 0.45, 0.9),
                                 frameSize=(-self.SIZE - 0.012, self.SIZE + 0.012,
                                            -self.SIZE - 0.012, self.SIZE + 0.012),
                                 pos=(-0.42, 0, 0.02))
        self.frame.setBin("fixed", 1)
        self.image.setBin("fixed", 2)

        self.title = OnscreenText(text="Карта фермы", pos=(-0.42, 0.82), scale=0.070,
                                  fg=GOLD, font=hud.font, align=TextNode.ACenter,
                                  parent=self.root, mayChange=True)
        self.legend = OnscreenText(text="", pos=(0.46, 0.62), scale=0.045, fg=INK,
                                   font=hud.font, align=TextNode.ALeft,
                                   parent=self.root, mayChange=True)
        self.hint = OnscreenText(
            text="↑↓ выбрать · Enter — идти туда · Tab/Esc — закрыть",
            pos=(-0.42, -0.86), scale=0.040, fg=DIM, font=hud.font,
            align=TextNode.ACenter, parent=self.root, mayChange=True)

        self.marks: list = []
        for _label, _xy, kind in self.landmarks:
            m = DirectFrame(parent=self.root, frameColor=MARKER_COLOURS[kind],
                            frameSize=(-0.012, 0.012, -0.012, 0.012))
            m.setBin("fixed", 3)
            self.marks.append(m)
        # Eight identical squares told you nothing about which was which. The
        # selected one says its name on the map, next to the list.
        self.mark_label = OnscreenText(text="", pos=(0, 0), scale=0.038, fg=GOLD,
                                       font=hud.font, align=TextNode.ACenter,
                                       parent=self.root, mayChange=True,
                                       shadow=(0, 0, 0, 0.85))
        self.mark_label.setBin("fixed", 5)

        self.npc_marks = [
            DirectFrame(parent=self.root, frameColor=(0.85, 0.72, 1.0, 0.95),
                        frameSize=(-0.009, 0.009, -0.009, 0.009))
            for _ in range(3)]
        for m in self.npc_marks:
            m.setBin("fixed", 3)

        self.player_mark = DirectFrame(parent=self.root, frameColor=(1, 1, 1, 1),
                                       frameSize=(-0.016, 0.016, -0.016, 0.016))
        self.player_mark.setBin("fixed", 4)
        self.player_dir = DirectFrame(parent=self.root, frameColor=(1, 0.3, 0.25, 1),
                                      frameSize=(-0.007, 0.007, -0.007, 0.007))
        self.player_dir.setBin("fixed", 4)

    # ---------------------------------------------------------------- helpers

    def _to_screen(self, x: float, y: float):
        """World metres -> aspect2d coordinates on the map image."""
        u = max(-1.0, min(1.0, x / MAP_EXTENT))
        v = max(-1.0, min(1.0, y / MAP_EXTENT))
        return (-0.42 + u * self.SIZE, 0.02 + v * self.SIZE)

    # ----------------------------------------------------------------- control

    def toggle(self) -> bool:
        self.visible = not self.visible
        if self.visible:
            self.root.show()
            self.refresh()
        else:
            self.root.hide()
        return self.visible

    def close(self) -> None:
        self.visible = False
        self.root.hide()

    def move(self, delta: int) -> None:
        self.cursor = (self.cursor + delta) % len(self.landmarks)
        self.refresh()

    def selected(self):
        return self.landmarks[self.cursor]

    def arrival(self, x: float, y: float, radius: float = 0.34):
        """Somewhere beside a landmark that a person can actually stand.

        A landmark marks the thing itself — the well, the stall, the middle of
        the pond — and those are exactly the places you cannot be. Travelling
        used to drop the player inside the well's post, inside the stall, or
        three and a half metres under the surface of the pond.
        """
        ground = self.world.height_at(x, y)
        water = self.cfg.water_level

        # Out of the water first: step away from the pond until on dry land.
        if ground < water:
            px, py = POND_CENTRE
            dx, dy = x - px, y - py
            length = math.hypot(dx, dy)
            if length < 1e-3:
                dx, dy, length = 1.0, -1.0, math.sqrt(2.0)
            dx, dy = dx / length, dy / length
            for step in range(1, 80):
                cx, cy = x + dx * step * 0.5, y + dy * step * 0.5
                if self.world.height_at(cx, cy) >= water + 0.05:
                    x, y = cx, cy
                    break

        # Then out of anything solid standing there.
        z = self.world.height_at(x, y) + 0.9
        return self.world.blockers.resolve(x, y, radius, z)[:2]

    def travel_cost(self, player_pos) -> float:
        """Seconds of in-game time the walk would have taken."""
        _label, (tx, ty), _kind = self.selected()
        dist = math.hypot(tx - player_pos.x, ty - player_pos.y)
        return dist / TRAVEL_SPEED

    # ------------------------------------------------------------------ draw

    def refresh(self) -> None:
        lines = []
        for i, (label, (x, y), _kind) in enumerate(self.landmarks):
            mark = "›" if i == self.cursor else " "
            lines.append(f"{mark} {label}")
        self.legend.setText("КУДА ПОЙТИ\n\n" + "\n".join(lines))

    def update(self, player_pos, player_heading: float, villagers) -> None:
        if not self.visible:
            return
        for i, (label, (x, y), _kind) in enumerate(self.landmarks):
            sx, sy = self._to_screen(x, y)
            self.marks[i].setPos(sx, 0, sy)
            scale = 1.55 if i == self.cursor else 1.0
            self.marks[i].setScale(scale)
            if i == self.cursor:
                # Above the marker, unless that would run off the top edge.
                up = sy + 0.045 < 0.02 + self.SIZE - 0.03
                self.mark_label.setText(label)
                self.mark_label.setPos(sx, sy + (0.045 if up else -0.075))

        for i, npc in enumerate(villagers.npcs[:len(self.npc_marks)]):
            p = npc.node.getPos()
            sx, sy = self._to_screen(p.x, p.y)
            self.npc_marks[i].setPos(sx, 0, sy)

        sx, sy = self._to_screen(player_pos.x, player_pos.y)
        self.player_mark.setPos(sx, 0, sy)
        # A pip in front of the player showing which way they face.
        a = math.radians(player_heading)
        self.player_dir.setPos(sx - math.sin(a) * 0.035, 0, sy + math.cos(a) * 0.035)

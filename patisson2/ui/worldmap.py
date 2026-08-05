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

from ..world.layout import LAYOUT
from ..world.terrain import POND_CENTRE

MAP_RES = 384
# Half-width of the area drawn, in metres. The farm and its woods, not the rim.
MAP_EXTENT = 120.0

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


def build_map_texture(terrain, cfg) -> Texture:
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

    def __init__(self, base, hud, world, cfg):
        self.base = base
        self.hud = hud
        self.world = world
        self.cfg = cfg
        self.visible = False
        self.cursor = 0
        self.landmarks = _landmarks()

        self.texture = build_map_texture(world.terrain, cfg)

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
        for i, (_label, (x, y), _kind) in enumerate(self.landmarks):
            sx, sy = self._to_screen(x, y)
            self.marks[i].setPos(sx, 0, sy)
            scale = 1.55 if i == self.cursor else 1.0
            self.marks[i].setScale(scale)

        for i, npc in enumerate(villagers.npcs[:len(self.npc_marks)]):
            p = npc.node.getPos()
            sx, sy = self._to_screen(p.x, p.y)
            self.npc_marks[i].setPos(sx, 0, sy)

        sx, sy = self._to_screen(player_pos.x, player_pos.y)
        self.player_mark.setPos(sx, 0, sy)
        # A pip in front of the player showing which way they face.
        a = math.radians(player_heading)
        self.player_dir.setPos(sx - math.sin(a) * 0.035, 0, sy + math.cos(a) * 0.035)

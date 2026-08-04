"""Assembles the living world: ground, water, grass and the paint layer that
records where the player has tilled or worn a path."""

from __future__ import annotations

import numpy as np
from panda3d.core import (
    NodePath,
    SamplerState,
    Texture,
    TransparencyAttrib,
    Vec3,
    Vec4,
)

from ..config import WorldConfig
from ..engine.pipeline import MASK_REFLECT, MASK_SHADOW
from ..engine.reflection import PlanarReflection
from ..engine.shaderlib import make_shader
from .daynight import SEASON_STYLE
from .grass import build_blade_node
from .terrain import Terrain
from .water import build_water_node, water_bounds

MASK_RES = 512


class FieldMask:
    """A painted RG texture over the world: R = tilled soil, G = worn path."""

    def __init__(self, min_corner: float, size: float, res: int = MASK_RES):
        self.min = min_corner
        self.size = size
        self.res = res
        self.data = np.zeros((res, res, 4), dtype=np.uint8)
        self.data[:, :, 3] = 255
        self.tex = Texture("field-mask")
        self.tex.setup2dTexture(res, res, Texture.TUnsignedByte, Texture.FRgba)
        self.tex.setWrapU(Texture.WMClamp)
        self.tex.setWrapV(Texture.WMClamp)
        self.tex.setMinfilter(SamplerState.FT_linear)
        self.tex.setMagfilter(SamplerState.FT_linear)
        self._dirty = True
        self.commit()

    def _to_px(self, x: float, y: float) -> tuple[int, int]:
        u = (x - self.min) / self.size * (self.res - 1)
        v = (y - self.min) / self.size * (self.res - 1)
        return int(round(u)), int(round(v))

    def paint(self, x: float, y: float, radius: float, channel: int,
              value: int = 255, falloff: bool = True) -> None:
        px, py = self._to_px(x, y)
        pr = max(1, int(radius / self.size * self.res))
        x0, x1 = max(px - pr, 0), min(px + pr + 1, self.res)
        y0, y1 = max(py - pr, 0), min(py + pr + 1, self.res)
        if x0 >= x1 or y0 >= y1:
            return
        gx, gy = np.meshgrid(np.arange(x0, x1), np.arange(y0, y1), indexing="ij")
        d = np.sqrt((gx - px) ** 2 + (gy - py) ** 2) / max(pr, 1e-6)
        if falloff:
            amount = np.clip(1.0 - d, 0.0, 1.0) ** 0.6
        else:
            amount = (d <= 1.0).astype(np.float64)
        target = (amount * value).astype(np.uint8)
        # Panda's rows run v-major, so index [v, u].
        region = self.data[y0:y1, x0:x1, channel]
        self.data[y0:y1, x0:x1, channel] = np.maximum(region, target.T)
        self._dirty = True

    def clear(self, x: float, y: float, radius: float, channel: int) -> None:
        px, py = self._to_px(x, y)
        pr = max(1, int(radius / self.size * self.res))
        x0, x1 = max(px - pr, 0), min(px + pr + 1, self.res)
        y0, y1 = max(py - pr, 0), min(py + pr + 1, self.res)
        self.data[y0:y1, x0:x1, channel] = 0
        self._dirty = True

    def commit(self) -> None:
        if not self._dirty:
            return
        self.tex.setRamImage(np.ascontiguousarray(self.data[:, :, [2, 1, 0, 3]]).tobytes())
        self._dirty = False


class World:
    def __init__(self, base, pipeline, cfg: WorldConfig, graphics):
        self.base = base
        self.pipeline = pipeline
        self.cfg = cfg
        self.graphics = graphics
        self.season = 1
        self.snow = 0.0
        self.wet = 0.0

        self.root = base.render.attachNewNode("world")
        self.terrain = Terrain(cfg)

        span = self.terrain.half_span
        self.bounds = Vec4(-span, -span, 1.0 / (span * 2.0), 1.0 / (span * 2.0))
        self.mask = FieldMask(-span, span * 2.0)

        self._build_terrain()
        self._build_water()
        self._build_grass()
        self.apply_season(self.season)
        # Prime every uniform before the first frame; Panda asserts otherwise.
        self.update(0.0, Vec3(0, 0, 0), Vec4(0.82, 0.57, 0.0, 0.4), 0.0)

    # ------------------------------------------------------------------ build

    def _build_terrain(self):
        node = self.terrain.build_node()
        node.reparentTo(self.root)
        node.setShader(make_shader("terrain.vert", "terrain.frag",
                                   {"NUM_LIGHTS": 1 + 4}))
        node.setShaderInput("u_skyLut", self.pipeline.skylut_tex)
        node.setShaderInput("u_fieldMask", self.mask.tex)
        node.setShaderInput("u_worldBounds", self.bounds)
        node.setShaderInput("u_waterLevel", self.cfg.water_level)
        node.setShaderInput("u_soilColor", Vec3(0.24, 0.16, 0.10))
        node.setShaderInput("u_rockColor", Vec3(0.35, 0.34, 0.33))
        node.setShaderInput("u_sandColor", Vec3(0.60, 0.53, 0.38))
        node.setShaderInput("u_snowColor", Vec3(0.90, 0.93, 0.98))
        node.setShaderInput("u_snowAmount", 0.0)
        self.terrain_np = node

    def _build_water(self):
        from .terrain import POND_CENTRE, POND_RADIUS
        self.pond_centre = POND_CENTRE
        self.pond_radius = POND_RADIUS
        self.reflection = PlanarReflection(self.base, self.cfg.water_level)
        bounds = water_bounds(self.terrain)
        if bounds is None:
            self.water_np = None
            return
        node = build_water_node(bounds, self.cfg.water_level)
        node.reparentTo(self.root)
        node.setShader(make_shader("water.vert", "water.frag", {"NUM_LIGHTS": 1 + 4}))
        node.setShaderInput("u_skyLut", self.pipeline.skylut_tex)
        node.setShaderInput("u_heightMap", self.terrain.height_tex)
        node.setShaderInput("u_terrainBounds", self.bounds)
        node.setShaderInput("u_waterLevel", self.cfg.water_level)
        node.setShaderInput("u_waveAmp", 1.0)
        node.setShaderInput("u_shallowColor", Vec3(0.30, 0.62, 0.60))
        node.setShaderInput("u_deepColor", Vec3(0.045, 0.16, 0.22))
        node.setShaderInput("u_foamWidth", 0.42)
        node.setShaderInput("u_reflection", self.reflection.texture)
        node.setShaderInput("u_reflectStrength", 0.0)
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.setBin("transparent", 20)
        node.setDepthWrite(False)
        node.hide(MASK_SHADOW)
        # The water must not appear in its own reflection.
        node.hide(MASK_REFLECT)
        self.water_np = node
        self.water_bounds = bounds

    def _build_grass(self):
        node = build_blade_node(self.graphics.grass_density)
        node.reparentTo(self.root)
        node.setShader(make_shader("grass.vert", "grass.frag", {"NUM_LIGHTS": 1 + 4}))
        node.setShaderInput("u_skyLut", self.pipeline.skylut_tex)
        node.setShaderInput("u_heightMap", self.terrain.height_tex)
        node.setShaderInput("u_fieldMask", self.mask.tex)
        node.setShaderInput("u_terrainBounds", self.bounds)
        node.setShaderInput("u_center", Vec3(0, 0, 0).xy)
        node.setShaderInput("u_radius", self.graphics.grass_radius)
        node.setShaderInput("u_waterLevel", self.cfg.water_level)
        node.setShaderInput("u_heightScale", 0.42)
        node.hide(MASK_SHADOW)
        # Grass is the most expensive thing on screen and reads as a green
        # smear at reflection resolution; the terrain under it is enough.
        node.hide(MASK_REFLECT)
        self.grass_np = node

    # ----------------------------------------------------------------- season

    def apply_season(self, season: int) -> None:
        self.season = season
        grass_col, tree_col, _cover, _label = SEASON_STYLE[season]
        dry = Vec3(grass_col[0] * 1.35 + 0.10, grass_col[1] * 0.92, grass_col[2] * 0.75)
        self.terrain_np.setShaderInput("u_grassColor", grass_col * 0.55)
        self.terrain_np.setShaderInput("u_grassColorDry", dry * 0.5)
        self.snow = 1.0 if season == 3 else 0.0
        self.terrain_np.setShaderInput("u_snowAmount", self.snow)
        if hasattr(self, "grass_np"):
            self.grass_np.setShaderInput("u_colorA", grass_col * 0.85)
            self.grass_np.setShaderInput("u_colorB", dry * 0.75)
            self.grass_np.setShaderInput("u_heightScale",
                                         0.22 if season == 3 else 0.42)

    # ----------------------------------------------------------------- update

    def update(self, dt: float, player_pos: Vec3, wind: Vec4, time: float) -> None:
        self.mask.commit()
        if self.water_np is not None:
            self.water_np.setShaderInput("u_time", time)
            self.reflection.update(player_pos, self.pond_centre, self.pond_radius)
            self.water_np.setShaderInput(
                "u_reflectStrength", 0.85 if self.reflection.active else 0.0)
        self.grass_np.setShaderInput("u_center", Vec3(player_pos.x, player_pos.y, 0).xy)
        self.grass_np.setShaderInput("u_time", time)
        self.grass_np.setShaderInput("u_wind", wind)

    # ------------------------------------------------------------------ query

    def height_at(self, x: float, y: float) -> float:
        return self.terrain.height_at(x, y)

    def can_till(self, x: float, y: float) -> bool:
        return (self.terrain.height_at(x, y) > self.cfg.water_level + 0.4
                and self.terrain.slope_at(x, y) < 0.14)

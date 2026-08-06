"""Procedural terrain: heightfield, mesh, and the queries gameplay needs.

The farm sits in a flat basin; hills rise towards the rim so the world never
shows a visible edge. The mesh grid is warped so triangles bunch up near the
middle where the player actually walks.
"""

from __future__ import annotations


import numpy as np
from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    SamplerState,
    Texture,
    Vec3,
)

from ..config import WorldConfig
from .heightfield import (FARM_FALLOFF, FARM_RADIUS, POND_CENTRE,
                          POND_DEPTH, POND_RADIUS, HeightField)

class Terrain:
    """The drawn ground: the shared height field plus the mesh and the
    texture the shaders read. All the arithmetic lives in HeightField so a
    server with no graphics can answer the same questions."""

    def __init__(self, cfg: WorldConfig):
        self.cfg = cfg
        self.field = HeightField(cfg)
        self.half_span = self.field.half_span
        self.water_level = cfg.water_level
        self._build_height_texture()

    # --- everything about where the ground is, answered by the field ---
    def raw_height(self, x, y, pads: bool = True):
        return self.field.raw_height(x, y, pads=pads)

    _raw_height = raw_height          # kept: older callers used the private name

    @property
    def heights(self):
        return self.field.heights

    @property
    def lut_res(self):
        return self.field.lut_res

    @property
    def lut_min(self):
        return self.field.lut_min

    @property
    def lut_size(self):
        return self.field.lut_size

    def height_at(self, x: float, y: float) -> float:
        return self.field.height_at(x, y)

    def normal_at(self, x: float, y: float, eps: float = 0.6) -> Vec3:
        return Vec3(*self.field.normal_tuple(x, y, eps))

    def slope_at(self, x: float, y: float) -> float:
        return self.field.slope_at(x, y)

    def is_water(self, x: float, y: float) -> bool:
        return self.field.is_water(x, y)

    def _build_height_texture(self):
        """Hand the baked grid to the shaders."""
        res = self.field.lut_res
        tex = Texture("terrain-height")
        tex.setup2dTexture(res, res, Texture.TFloat, Texture.FR32)
        # Panda expects rows bottom-up; our grid is indexed [x][y] so transpose.
        tex.setRamImage(np.ascontiguousarray(self.field.heights.T).tobytes())
        tex.setWrapU(Texture.WMClamp)
        tex.setWrapV(Texture.WMClamp)
        tex.setMinfilter(SamplerState.FT_linear)
        tex.setMagfilter(SamplerState.FT_linear)
        self.height_tex = tex

    # ------------------------------------------------------------------- mesh

    @staticmethod
    def _warp(u: np.ndarray) -> np.ndarray:
        """Concentrate mesh density near the origin. u in [-1, 1] -> [-1, 1].

        The farm and pond sit inside ~50 m and get roughly metre-scale
        triangles; the rim hills are only ever seen as a silhouette.
        """
        a = np.abs(u)
        return np.sign(u) * (0.28 * a + 0.72 * a ** 4)

    def build_node(self, name: str = "terrain") -> NodePath:
        res = self.cfg.terrain_res
        u = np.linspace(-1.0, 1.0, res)
        coords = self._warp(u) * self.half_span
        xx, yy = np.meshgrid(coords, coords, indexing="ij")
        zz = self._raw_height(xx, yy)

        # Normals must be sampled at the scale the triangles actually resolve.
        # Using a fixed small epsilon on a grid that coarsens towards the rim
        # produces normals the geometry doesn't have, which shows up as huge
        # patches of shadow acne under a low sun.
        spacing = np.gradient(coords)
        eps_x = np.clip(np.abs(spacing) * 0.6, 0.35, 40.0)
        ex = eps_x[:, None] * np.ones((1, res))
        ey = eps_x[None, :] * np.ones((res, 1))
        hx = self._raw_height(xx + ex, yy) - self._raw_height(xx - ex, yy)
        hy = self._raw_height(xx, yy + ey) - self._raw_height(xx, yy - ey)
        nx = -hx / (2.0 * ex)
        ny = -hy / (2.0 * ey)
        nz = np.ones_like(hx)
        nlen = np.sqrt(nx * nx + ny * ny + nz * nz)
        nx, ny, nz = nx / nlen, ny / nlen, nz / nlen

        fmt = GeomVertexFormat.getV3n3t2()
        vdata = GeomVertexData(name, fmt, Geom.UHStatic)
        vdata.setNumRows(res * res)
        vw = GeomVertexWriter(vdata, "vertex")
        nw = GeomVertexWriter(vdata, "normal")
        tw = GeomVertexWriter(vdata, "texcoord")

        flat_x = xx.ravel()
        flat_y = yy.ravel()
        flat_z = zz.ravel()
        fnx, fny, fnz = nx.ravel(), ny.ravel(), nz.ravel()
        inv = 1.0 / (self.half_span * 2.0)
        for i in range(flat_x.size):
            vw.addData3(float(flat_x[i]), float(flat_y[i]), float(flat_z[i]))
            nw.addData3(float(fnx[i]), float(fny[i]), float(fnz[i]))
            tw.addData2(float((flat_x[i] + self.half_span) * inv),
                        float((flat_y[i] + self.half_span) * inv))

        tris = GeomTriangles(Geom.UHStatic)
        for i in range(res - 1):
            base = i * res
            nxt = (i + 1) * res
            for j in range(res - 1):
                a, b = base + j, base + j + 1
                c, d = nxt + j, nxt + j + 1
                tris.addVertices(a, c, b)
                tris.addVertices(b, c, d)

        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode(name)
        node.addGeom(geom)
        return NodePath(node)

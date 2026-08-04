"""Procedural terrain: heightfield, mesh, and the queries gameplay needs.

The farm sits in a flat basin; hills rise towards the rim so the world never
shows a visible edge. The mesh grid is warped so triangles bunch up near the
middle where the player actually walks.
"""

from __future__ import annotations

import math

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

# Everything inside this radius is flattened to farm level.
FARM_RADIUS = 46.0
FARM_FALLOFF = 34.0

POND_CENTRE = (-30.0, 24.0)
POND_RADIUS = 15.0
POND_DEPTH = 3.4


def _fbm(x: np.ndarray, y: np.ndarray, seed: int, octaves: int = 5,
         lacunarity: float = 2.03, gain: float = 0.5) -> np.ndarray:
    """Value-noise fBm evaluated on arbitrary coordinate arrays."""
    total = np.zeros_like(x, dtype=np.float64)
    amp = 1.0
    norm = 0.0
    freq = 1.0
    for o in range(octaves):
        total += amp * _value_noise(x * freq, y * freq, seed + o * 1013)
        norm += amp
        amp *= gain
        freq *= lacunarity
    return total / norm


_U64 = np.uint64


def _hash2(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    """Integer hash -> [0, 1). All arithmetic stays in uint64 so it wraps
    instead of overflowing into Python bignums."""
    with np.errstate(over="ignore"):
        a = ix.astype(np.int64).astype(_U64) * _U64(0x9E3779B97F4A7C15)
        b = iy.astype(np.int64).astype(_U64) * _U64(0xC2B2AE3D27D4EB4F)
        h = a + b + _U64(seed & 0xFFFFFFFF) * _U64(0x165667B19E3779F9)
        h ^= np.right_shift(h, _U64(29))
        h *= _U64(0xBF58476D1CE4E5B9)
        h ^= np.right_shift(h, _U64(32))
        h *= _U64(0x94D049BB133111EB)
        h ^= np.right_shift(h, _U64(31))
    return (h >> _U64(40)).astype(np.float64) / float(1 << 24)


def _value_noise(x: np.ndarray, y: np.ndarray, seed: int) -> np.ndarray:
    ix = np.floor(x)
    iy = np.floor(y)
    fx = x - ix
    fy = y - iy
    ux = fx * fx * (3.0 - 2.0 * fx)
    uy = fy * fy * (3.0 - 2.0 * fy)
    n00 = _hash2(ix, iy, seed)
    n10 = _hash2(ix + 1, iy, seed)
    n01 = _hash2(ix, iy + 1, seed)
    n11 = _hash2(ix + 1, iy + 1, seed)
    a = n00 + (n10 - n00) * ux
    b = n01 + (n11 - n01) * ux
    return a + (b - a) * uy


class Terrain:
    def __init__(self, cfg: WorldConfig):
        self.cfg = cfg
        self.half_span = cfg.size * 1.18      # mesh reaches well past the farm
        self.water_level = cfg.water_level
        self._build_lookup()

    # ------------------------------------------------------------ height field

    def _raw_height(self, x, y):
        """Analytic terrain height. Works on scalars or numpy arrays."""
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        seed = self.cfg.seed

        # Rolling base landscape.
        h = _fbm(x * 0.0042, y * 0.0042, seed, octaves=5) - 0.5
        h *= self.cfg.max_height * 2.6
        # Ridged detail for the hillsides.
        ridge = 1.0 - np.abs(_fbm(x * 0.011, y * 0.011, seed + 77, octaves=3) - 0.5) * 2.0
        h += ridge * 2.4
        # Fine bumpiness.
        h += (_fbm(x * 0.075, y * 0.075, seed + 311, octaves=3) - 0.5) * 0.85

        dist = np.sqrt(x * x + y * y)

        # Rim hills so the world has no visible edge.
        rim = np.clip((dist - self.cfg.size * 0.52) / (self.cfg.size * 0.45), 0.0, 1.0)
        h += rim * rim * 46.0

        # Flatten the farm basin.
        flat = 1.0 - np.clip((dist - FARM_RADIUS) / FARM_FALLOFF, 0.0, 1.0)
        flat = flat * flat * (3.0 - 2.0 * flat)
        farm_level = 0.0 + (_fbm(x * 0.03, y * 0.03, seed + 5) - 0.5) * 0.55
        h = h * (1.0 - flat) + farm_level * flat

        # Pond basin.
        px, py = POND_CENTRE
        pd = np.sqrt((x - px) ** 2 + (y - py) ** 2)
        bowl = np.clip(1.0 - pd / POND_RADIUS, 0.0, 1.0)
        bowl = bowl * bowl * (3.0 - 2.0 * bowl)
        h -= bowl * POND_DEPTH

        return h

    def _build_lookup(self):
        """Bake a regular grid for fast queries and for the shaders."""
        res = 513
        self.lut_res = res
        span = self.half_span
        self.lut_min = -span
        self.lut_size = span * 2.0
        gx = np.linspace(-span, span, res)
        xx, yy = np.meshgrid(gx, gx, indexing="ij")
        self.heights = self._raw_height(xx, yy).astype(np.float32)

        tex = Texture("terrain-height")
        tex.setup2dTexture(res, res, Texture.TFloat, Texture.FR32)
        # Panda expects rows bottom-up; our grid is indexed [x][y] so transpose.
        tex.setRamImage(np.ascontiguousarray(self.heights.T).tobytes())
        tex.setWrapU(Texture.WMClamp)
        tex.setWrapV(Texture.WMClamp)
        tex.setMinfilter(SamplerState.FT_linear)
        tex.setMagfilter(SamplerState.FT_linear)
        self.height_tex = tex

    def height_at(self, x: float, y: float) -> float:
        """Bilinear lookup — matches what the shaders see."""
        res = self.lut_res
        u = (x - self.lut_min) / self.lut_size * (res - 1)
        v = (y - self.lut_min) / self.lut_size * (res - 1)
        u = min(max(u, 0.0), res - 1.001)
        v = min(max(v, 0.0), res - 1.001)
        i, j = int(u), int(v)
        fu, fv = u - i, v - j
        h = self.heights
        return float(
            h[i, j] * (1 - fu) * (1 - fv)
            + h[i + 1, j] * fu * (1 - fv)
            + h[i, j + 1] * (1 - fu) * fv
            + h[i + 1, j + 1] * fu * fv
        )

    def normal_at(self, x: float, y: float, eps: float = 0.6) -> Vec3:
        hx = self.height_at(x + eps, y) - self.height_at(x - eps, y)
        hy = self.height_at(x, y + eps) - self.height_at(x, y - eps)
        n = Vec3(-hx, -hy, 2.0 * eps)
        n.normalize()
        return n

    def slope_at(self, x: float, y: float) -> float:
        return 1.0 - self.normal_at(x, y).z

    def is_water(self, x: float, y: float) -> bool:
        return self.height_at(x, y) < self.water_level

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

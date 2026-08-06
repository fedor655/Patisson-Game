"""The shape of the ground, computed without a renderer.

The farm sits in a flat basin; hills rise towards the rim so the world
never shows a visible edge, and a bowl is scooped out for the pond.

This lives apart from `terrain.py` because more than one thing needs to
know where the ground is and only one of them draws it. The desktop game
builds a mesh and a height texture out of this; a dedicated server needs
the same numbers to tell a player whether they may till a spot and how
high a plot sits, and it has no graphics library at all. Sharing the
arithmetic is what keeps a hosted farm identical to the one on screen —
two implementations would drift, and the beds would end up in the air.

Everything here is numpy and nothing else.
"""

from __future__ import annotations

import numpy as np

from ..config import WorldConfig
from .layout import building_pads

# Everything inside this radius is flattened to farm level.
FARM_RADIUS = 46.0
FARM_FALLOFF = 34.0

POND_CENTRE = (-30.0, 24.0)
POND_RADIUS = 15.0
POND_DEPTH = 3.4

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


class HeightField:
    """The ground: an analytic height plus a baked grid for fast queries."""

    def __init__(self, cfg: WorldConfig):
        self.cfg = cfg
        self.half_span = cfg.size * 1.18      # reaches well past the farm
        self.water_level = cfg.water_level
        self._pads = None
        self._build_lookup()

    def _pad_levels(self):
        """Ground height at each building centre, before flattening."""
        if self._pads is None:
            self._pads = [(px, py, r, blend,
                           float(self.raw_height(px, py, pads=False)))
                          for px, py, r, blend in building_pads()]
        return self._pads

    def raw_height(self, x, y, pads: bool = True):
        """Analytic terrain height. Works on scalars or numpy arrays."""
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        seed = self.cfg.seed

        # Rolling base landscape.
        h = _fbm(x * 0.0042, y * 0.0042, seed, octaves=5) - 0.5
        h *= self.cfg.max_height * 2.6
        # Ridged detail for the hillsides.
        ridge = 1.0 - np.abs(_fbm(x * 0.011, y * 0.011, seed + 77,
                                  octaves=3) - 0.5) * 2.0
        h += ridge * 2.4
        # Fine bumpiness.
        h += (_fbm(x * 0.075, y * 0.075, seed + 311, octaves=3) - 0.5) * 0.85

        dist = np.sqrt(x * x + y * y)

        # Rim hills so the world has no visible edge.
        rim = np.clip((dist - self.cfg.size * 0.52) / (self.cfg.size * 0.45),
                      0.0, 1.0)
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

        if pads:
            # Buildings need level ground: a floor laid across a metre of
            # slope leaves the terrain poking up through it.
            for px, py, radius, blend, level in self._pad_levels():
                pd = np.sqrt((x - px) ** 2 + (y - py) ** 2)
                t = np.clip(1.0 - (pd - radius) / blend, 0.0, 1.0)
                t = t * t * (3.0 - 2.0 * t)
                h = h * (1.0 - t) + level * t

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
        self.heights = self.raw_height(xx, yy).astype(np.float32)

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

    def normal_tuple(self, x: float, y: float, eps: float = 0.6):
        """Unit ground normal as a plain (x, y, z) — no engine types."""
        hx = self.height_at(x + eps, y) - self.height_at(x - eps, y)
        hy = self.height_at(x, y + eps) - self.height_at(x, y - eps)
        nx, ny, nz = -hx, -hy, 2.0 * eps
        n = (nx * nx + ny * ny + nz * nz) ** 0.5
        return (nx / n, ny / n, nz / n) if n else (0.0, 0.0, 1.0)

    def slope_at(self, x: float, y: float) -> float:
        return 1.0 - self.normal_tuple(x, y)[2]

    def is_water(self, x: float, y: float) -> bool:
        return self.height_at(x, y) < self.water_level

    def can_till(self, x: float, y: float) -> bool:
        return (self.height_at(x, y) > self.water_level + 0.4
                and self.slope_at(x, y) < 0.14)

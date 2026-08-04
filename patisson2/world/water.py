"""The pond surface: a tessellated plane that only draws where the bed is
below the waterline."""

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
)


def water_bounds(terrain, margin: float = 6.0):
    """Axis-aligned box covering everything below the waterline."""
    below = terrain.heights < terrain.water_level + 0.25
    if not below.any():
        return None
    idx = np.argwhere(below)
    step = terrain.lut_size / (terrain.lut_res - 1)
    xs = terrain.lut_min + idx[:, 0] * step
    ys = terrain.lut_min + idx[:, 1] * step
    return (float(xs.min() - margin), float(ys.min() - margin),
            float(xs.max() + margin), float(ys.max() + margin))


def build_water_node(bounds, level: float, res: int = 120,
                     name: str = "water") -> NodePath:
    x0, y0, x1, y1 = bounds
    xs = np.linspace(x0, x1, res)
    ys = np.linspace(y0, y1, res)

    fmt = GeomVertexFormat.getV3()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vdata.setNumRows(res * res)
    vw = GeomVertexWriter(vdata, "vertex")
    for i in range(res):
        for j in range(res):
            vw.addData3(float(xs[i]), float(ys[j]), level)

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

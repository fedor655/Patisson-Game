"""Instanced grass field. One blade mesh, hundreds of thousands of instances,
all placement decided on the GPU from the instance id."""

from __future__ import annotations

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTristrips,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    OmniBoundingVolume,
)

# (across, along) pairs forming a tapering blade as one triangle strip.
BLADE = [
    (-1.0, 0.00), (1.0, 0.00),
    (-0.85, 0.36), (0.85, 0.36),
    (-0.55, 0.70), (0.55, 0.70),
    (0.0, 1.00),
]


def build_blade_node(instances: int, name: str = "grass") -> NodePath:
    fmt = GeomVertexFormat.getV3()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vdata.setNumRows(len(BLADE))
    vw = GeomVertexWriter(vdata, "vertex")
    for across, along in BLADE:
        # x carries the across-blade parameter, z the along-blade parameter;
        # the vertex shader rebuilds real positions from these.
        vw.addData3(across, 0.0, along)

    strip = GeomTristrips(Geom.UHStatic)
    for i in range(len(BLADE)):
        strip.addVertex(i)
    strip.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(strip)
    node = GeomNode(name)
    node.addGeom(geom)

    np_ = NodePath(node)
    np_.setInstanceCount(instances)
    # Instances are placed in the shader, so Panda can't know the real extent.
    np_.node().setBounds(OmniBoundingVolume())
    np_.node().setFinal(True)
    np_.setTwoSided(True)
    return np_

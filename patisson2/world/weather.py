"""Visible weather: instanced rain and snow that follow the camera."""

from __future__ import annotations

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    OmniBoundingVolume,
    TransparencyAttrib,
    Vec2,
    Vec3,
    Vec4,
)

from ..engine.pipeline import MASK_SHADOW
from ..engine.shaderlib import make_shader


from .weatherstate import WeatherState  # noqa: F401  (re-exported)


# (instances, box, particle size, fall speed, sway, tint, opacity, round?)
PRESETS = {
    "rain": dict(count=64_000, box=Vec3(40.0, 40.0, 22.0), size=Vec2(0.017, 1.15),
                 fall=18.0, sway=0.0, tint=Vec3(0.74, 0.82, 0.94), opacity=0.34,
                 round=0.0, ground_fade=0.5, boost=0.85),
    "snow": dict(count=38_000, box=Vec3(36.0, 36.0, 20.0), size=Vec2(0.070, 0.070),
                 fall=1.4, sway=0.60, tint=Vec3(1.0, 1.0, 1.05), opacity=0.92,
                 round=1.0, ground_fade=0.25, boost=1.9),
}


def _quad_node(instances: int, name: str) -> NodePath:
    """A unit quad in the XZ plane, instanced. The vertex shader does the rest."""
    fmt = GeomVertexFormat.getV3()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vdata.setNumRows(4)
    vw = GeomVertexWriter(vdata, "vertex")
    for x, z in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
        vw.addData3(x, 0.0, z)

    tris = GeomTriangles(Geom.UHStatic)
    tris.addVertices(0, 1, 2)
    tris.addVertices(0, 2, 3)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)

    np_ = NodePath(node)
    np_.setInstanceCount(instances)
    # Placement happens on the GPU, so Panda can't derive real bounds.
    np_.node().setBounds(OmniBoundingVolume())
    np_.node().setFinal(True)
    np_.setTwoSided(True)
    return np_


class Precipitation:
    """Owns one rain layer and one snow layer, cross-fading on the weather."""

    def __init__(self, base, world, pipeline):
        self.base = base
        self.world = world
        self.pipeline = pipeline
        self.layers: dict[str, NodePath] = {}
        self.intensity: dict[str, float] = {"rain": 0.0, "snow": 0.0}
        self.target: dict[str, float] = {"rain": 0.0, "snow": 0.0}
        self.root = world.root.attachNewNode("precipitation")

        shader = make_shader("precip.vert", "precip.frag")
        for kind, cfg in PRESETS.items():
            np_ = _quad_node(cfg["count"], kind)
            np_.reparentTo(self.root)
            np_.setShader(shader)
            np_.setShaderInput("u_skyLut", pipeline.skylut_tex)
            np_.setShaderInput("u_heightMap", world.terrain.height_tex)
            np_.setShaderInput("u_terrainBounds", world.bounds)
            np_.setShaderInput("u_box", cfg["box"])
            np_.setShaderInput("u_size", cfg["size"])
            np_.setShaderInput("u_fallSpeed", cfg["fall"])
            np_.setShaderInput("u_sway", cfg["sway"])
            np_.setShaderInput("u_tint", cfg["tint"])
            np_.setShaderInput("u_opacity", cfg["opacity"])
            np_.setShaderInput("u_round", cfg["round"])
            np_.setShaderInput("u_groundFade", cfg["ground_fade"])
            np_.setShaderInput("u_boost", cfg["boost"])
            np_.setShaderInput("u_camera", Vec3(0, 0, 0))
            np_.setShaderInput("u_wind", Vec3(0, 0, 0))
            np_.setShaderInput("u_time", 0.0)
            np_.setShaderInput("u_intensity", 0.0)
            np_.setTransparency(TransparencyAttrib.MAlpha)
            np_.setBin("transparent", 40)
            np_.setDepthWrite(False)
            np_.hide(MASK_SHADOW)
            np_.stash()                     # nothing to draw until it rains
            self.layers[kind] = np_

    def set_weather(self, weather: str) -> None:
        self.target["rain"] = 1.0 if weather == "rain" else 0.0
        self.target["snow"] = 1.0 if weather == "snow" else 0.0

    def snap(self) -> None:
        """Jump straight to the target intensity — for scene cuts and captures."""
        self.intensity.update(self.target)

    def update(self, dt: float, camera_pos: Vec3, time: float, wind: Vec3) -> None:
        for kind, np_ in self.layers.items():
            level = self.intensity[kind]
            level += (self.target[kind] - level) * min(dt * 0.55, 1.0)
            self.intensity[kind] = level

            if level < 0.004:
                if not np_.isStashed():
                    np_.stash()
                continue
            if np_.isStashed():
                np_.unstash()

            drift = Vec3(wind.x * (0.9 if kind == "rain" else 0.45),
                         wind.y * (0.9 if kind == "rain" else 0.45), 0.0)
            np_.setShaderInput("u_camera", camera_pos)
            np_.setShaderInput("u_time", time)
            np_.setShaderInput("u_wind", drift)
            np_.setShaderInput("u_intensity", level)

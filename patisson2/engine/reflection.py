"""Planar reflection for the pond.

The water is a flat plane at a known height, so the cheapest correct reflection
is a second render from a camera mirrored through that plane. The water shader
then samples the result at the fragment's own screen position — which is
exactly where the mirrored camera drew it — nudged by the wave normal.

The pass is only alive while the player is near enough to see the pond, so most
of the time it costs nothing at all.
"""

from __future__ import annotations

from panda3d.core import (
    CullFaceAttrib,
    FrameBufferProperties,
    NodePath,
    Plane,
    Point3,
    RenderState,
    SamplerState,
    Texture,
    Vec3,
    Vec4,
)

from .pipeline import MASK_REFLECT


class PlanarReflection:
    def __init__(self, base, level: float, resolution_div: int = 2):
        self.base = base
        self.level = level
        self.active = False

        w = max(base.win.getXSize() // resolution_div, 64)
        h = max(base.win.getYSize() // resolution_div, 64)

        self.texture = Texture("reflection")
        self.texture.setWrapU(Texture.WMClamp)
        self.texture.setWrapV(Texture.WMClamp)
        self.texture.setMinfilter(SamplerState.FT_linear)
        self.texture.setMagfilter(SamplerState.FT_linear)

        props = FrameBufferProperties()
        props.setFloatColor(True)
        props.setRgbaBits(16, 16, 16, 16)
        props.setDepthBits(24)

        self.buffer = base.win.makeTextureBuffer(
            "reflection-buffer", w, h, self.texture, False, props)
        # Just after the sky table, well before the scene buffer.
        self.buffer.setSort(-3500)
        self.buffer.setClearColor(Vec4(0, 0, 0, 1))
        self.buffer.setActive(False)

        self.camera = base.makeCamera(self.buffer)
        self.camera.reparentTo(base.render)
        self.camera.node().setLens(base.camLens)
        self.camera.node().setCameraMask(MASK_REFLECT)
        # Mirroring flips triangle winding, so back faces become front faces.
        self.camera.node().setInitialState(
            RenderState.make(CullFaceAttrib.makeReverse()))

        self._plane = Plane(Vec3(0, 0, 1), Point3(0, 0, level))
        self._mirror = self._plane.getReflectionMat()

    def set_active(self, active: bool) -> None:
        if active == self.active:
            return
        self.active = active
        self.buffer.setActive(active)

    def update(self, player_pos: Vec3, water_centre, radius: float) -> None:
        """Mirror the main camera, and only run the pass when it can be seen."""
        dx = player_pos.x - water_centre[0]
        dy = player_pos.y - water_centre[1]
        near = (dx * dx + dy * dy) < (radius + 32.0) ** 2
        self.set_active(near)
        if not near:
            return
        cam = self.base.cam
        self.camera.setMat(self.base.render,
                           cam.getMat(self.base.render) * self._mirror)

"""The Patisson 2.0 render pipeline.

Scene renders into an HDR buffer with a physically-motivated PBR shader, lit by
a shadow-casting sun plus a handful of point lights. A small equirectangular sky
table is re-integrated every frame and feeds both ambient light and aerial
perspective, so shading always agrees with the sky you can see. Post: SSAO,
bloom, screen-space god rays, ACES tonemap, grade, FXAA.
"""

from __future__ import annotations

import math

from direct.filter.FilterManager import FilterManager
from panda3d.core import (
    BitMask32,
    CardMaker,
    DirectionalLight,
    FrameBufferProperties,
    GraphicsOutput,
    LMatrix4,
    LVector3,
    NodePath,
    OmniBoundingVolume,
    PointLight,
    PTA_LVecBase3f,
    PTA_float,
    Point2,
    Point3,
    SamplerState,
    Texture,
    Vec3,
    Vec4,
    WindowProperties,
)

from ..config import GraphicsConfig
from .shaderlib import make_shader

MASK_SHADOW = BitMask32.bit(1)
MASK_REFLECT = BitMask32.bit(2)

NUM_POINT_LIGHTS = 4
SKYLUT_W, SKYLUT_H = 128, 64


def _hdr_fbprops(alpha_bits: int = 16) -> FrameBufferProperties:
    props = FrameBufferProperties()
    props.setFloatColor(True)
    props.setRgbaBits(16, 16, 16, alpha_bits)
    props.setSrgbColor(False)
    return props


class RenderPipeline:
    def __init__(self, base, cfg: GraphicsConfig):
        self.base = base
        self.cfg = cfg
        self.time = 0.0
        # sun_dir drives the sky; light_dir drives the shadow-casting light
        # (they part company after sunset, when the moon takes over).
        self.sun_dir = Vec3(0.3, 0.4, 0.86).normalized()
        self.light_dir = Vec3(0.3, 0.4, 0.86).normalized()
        self.sun_color = Vec3(1.0, 0.96, 0.90) * 24.0
        self.cloud_cover = 0.42
        self.sky_intensity = 55.0
        self.fog_tint = Vec3(1.0, 1.0, 1.0)
        self.exposure_target = cfg.exposure
        self._exposure = cfg.exposure
        self._sun_colour_key = None
        self._sun_focus_key = None
        self._size_key = None

        base.render.setShaderAuto(False)
        base.render.setAntialias(0)

        self._make_default_textures()
        self._make_lights()
        self._make_skylut()
        self._make_sky_dome()
        self._make_filter_chain()
        self._make_global_inputs()
        self.apply_scene_shader(base.render)
        # Panda3D asserts on any declared uniform that has never been given a
        # value, so prime the whole chain before the first frame is drawn.
        self.update(0.0, Vec3(0, 0, 0), Vec3(0, 0, 0))

    # ------------------------------------------------------------------ setup

    def _make_default_textures(self):
        white = Texture("white")
        white.setup2dTexture(1, 1, Texture.TUnsignedByte, Texture.FRgba)
        white.setRamImage(bytes([255, 255, 255, 255]))
        white.setMagfilter(SamplerState.FT_nearest)
        self.white_tex = white

    def _make_lights(self):
        self.sun = DirectionalLight("sun")
        # Direction and shadow lens must agree; +Y is the lens forward axis.
        self.sun.setDirection(LVector3(0, 1, 0))
        self.sun.setColor(Vec4(*self.sun_color, 1.0))
        self.sun.setCameraMask(MASK_SHADOW)
        self.sun_np = self.base.render.attachNewNode(self.sun)
        # A very low sort makes the shadow map render before the scene buffer.
        self.sun.setShadowCaster(True, self.cfg.shadow_size, self.cfg.shadow_size, -3000)
        lens = self.sun.getLens()
        e = self.cfg.shadow_extent
        lens.setFilmSize(e * 2, e * 2)
        lens.setNearFar(1.0, 480.0)
        self.base.render.setLight(self.sun_np)

        self._light_state: dict[int, tuple] = {}
        self.point_lights = []
        for i in range(NUM_POINT_LIGHTS):
            pl = PointLight(f"point{i}")
            pl.setColor(Vec4(0, 0, 0, 1))
            pl.setAttenuation(Vec3(1.0, 0.09, 0.045))
            np_ = self.base.render.attachNewNode(pl)
            np_.setPos(0, 0, -1000)
            self.base.render.setLight(np_)
            self.point_lights.append(np_)

    def _make_skylut(self):
        tex = Texture("skylut")
        tex.setup2dTexture(SKYLUT_W, SKYLUT_H, Texture.TFloat, Texture.FRgba16)
        tex.setWrapU(Texture.WMRepeat)
        tex.setWrapV(Texture.WMClamp)
        tex.setMinfilter(SamplerState.FT_linear)
        tex.setMagfilter(SamplerState.FT_linear)
        self.skylut_tex = tex

        buff = self.base.win.makeTextureBuffer(
            "skylut-buffer", SKYLUT_W, SKYLUT_H, tex, False, _hdr_fbprops()
        )
        buff.setSort(-4000)
        buff.setClearColor(Vec4(0, 0, 0, 1))
        self.skylut_buffer = buff

        cam = self.base.makeCamera2d(buff)
        scene = NodePath("skylut-scene")
        cam.reparentTo(scene)
        cm = CardMaker("quad")
        cm.setFrameFullscreenQuad()
        quad = scene.attachNewNode(cm.generate())
        quad.setDepthTest(False)
        quad.setDepthWrite(False)
        quad.setShader(make_shader("fullscreen.vert", "skylut.frag"))
        self.skylut_quad = quad
        self.skylut_scene = scene

    def _make_sky_dome(self):
        cm = CardMaker("sky")
        cm.setFrameFullscreenQuad()
        sky = self.base.render.attachNewNode(cm.generate())
        sky.setBin("background", 0)
        sky.setDepthTest(False)
        sky.setDepthWrite(False)
        sky.setLightOff(1)
        sky.setMaterialOff(1)
        sky.setTextureOff(1)
        sky.node().setBounds(OmniBoundingVolume())
        sky.node().setFinal(True)
        sky.hide(MASK_SHADOW)
        sky.setShader(make_shader("sky.vert", "sky.frag"), 10)
        self.sky = sky

    def _make_filter_chain(self):
        base, cfg = self.base, self.cfg
        self.manager = FilterManager(base.win, base.cam)

        self.scene_color = Texture("scene-color")
        self.scene_depth = Texture("scene-depth")
        self.final_quad = self.manager.renderSceneInto(
            colortex=self.scene_color, depthtex=self.scene_depth, fbprops=_hdr_fbprops()
        )
        for t in (self.scene_color,):
            t.setWrapU(Texture.WMClamp)
            t.setWrapV(Texture.WMClamp)

        # --- SSAO ---------------------------------------------------------
        self.ao_tex = Texture("ao")
        if cfg.ssao:
            quad = self.manager.renderQuadInto("ssao", colortex=self.ao_tex, div=2)
            quad.setShader(make_shader("fullscreen.vert", "ssao.frag"))
            quad.setShaderInput("u_depth", self.scene_depth)
            quad.setShaderInput("u_radius", cfg.ssao_radius)
            quad.setShaderInput("u_intensity", cfg.ssao_intensity)
            quad.setShaderInput("u_bias", 0.022)
            self.ao_quad = quad

            self.ao_blur_tex = Texture("ao-blur")
            b1 = self.manager.renderQuadInto("ao-blur-h", colortex=self.ao_blur_tex, div=2)
            b1.setShader(make_shader("fullscreen.vert", "blur.frag"))
            b1.setShaderInput("u_source", self.ao_tex)
            self.ao_blur_h = b1

            self.ao_final = Texture("ao-final")
            b2 = self.manager.renderQuadInto("ao-blur-v", colortex=self.ao_final, div=2)
            b2.setShader(make_shader("fullscreen.vert", "blur.frag"))
            b2.setShaderInput("u_source", self.ao_blur_tex)
            self.ao_blur_v = b2
        else:
            self.ao_final = self.white_tex
            self.ao_quad = None

        # --- bloom --------------------------------------------------------
        self.bloom_levels = []
        if cfg.bloom:
            pre_tex = Texture("bloom-pre")
            pre = self.manager.renderQuadInto("bloom-pre", colortex=pre_tex, div=2,
                                              fbprops=_hdr_fbprops())
            pre.setShader(make_shader("fullscreen.vert", "bloom_prefilter.frag"))
            pre.setShaderInput("u_source", self.scene_color)
            pre.setShaderInput("u_threshold", cfg.bloom_threshold)
            pre.setShaderInput("u_knee", cfg.bloom_knee)
            self.bloom_pre = pre
            self.bloom_pre_tex = pre_tex

            source = pre_tex
            for i, div in enumerate((2, 4, 8)):
                h_tex = Texture(f"bloom{i}-h")
                h = self.manager.renderQuadInto(f"bloom{i}-h", colortex=h_tex, div=div,
                                                fbprops=_hdr_fbprops())
                h.setShader(make_shader("fullscreen.vert", "blur.frag"))
                h.setShaderInput("u_source", source)

                v_tex = Texture(f"bloom{i}-v")
                v = self.manager.renderQuadInto(f"bloom{i}-v", colortex=v_tex, div=div,
                                                fbprops=_hdr_fbprops())
                v.setShader(make_shader("fullscreen.vert", "blur.frag"))
                v.setShaderInput("u_source", h_tex)

                for t in (h_tex, v_tex):
                    t.setWrapU(Texture.WMClamp)
                    t.setWrapV(Texture.WMClamp)
                self.bloom_levels.append((h, h_tex, v, v_tex, div))
                source = v_tex
        else:
            self.bloom_levels = []

        black = Texture("black")
        black.setup2dTexture(1, 1, Texture.TUnsignedByte, Texture.FRgba)
        black.setRamImage(bytes([0, 0, 0, 255]))
        self.black_tex = black

        # --- composite ----------------------------------------------------
        self.ldr_tex = Texture("ldr")
        composite = self.manager.renderQuadInto("composite", colortex=self.ldr_tex)
        composite.setShader(make_shader("fullscreen.vert", "composite.frag"))
        composite.setShaderInput("u_color", self.scene_color)
        composite.setShaderInput("u_depth", self.scene_depth)
        composite.setShaderInput("u_ao", self.ao_final)
        for i in range(3):
            tex = self.bloom_levels[i][3] if i < len(self.bloom_levels) else black
            composite.setShaderInput(f"u_bloom{i}", tex)
        composite.setShaderInput("u_bloomStrength", cfg.bloom_strength if cfg.bloom else 0.0)
        composite.setShaderInput("u_aoStrength", 1.0 if cfg.ssao else 0.0)
        composite.setShaderInput("u_vignette", cfg.vignette)
        composite.setShaderInput("u_grain", cfg.grain)
        composite.setShaderInput("u_saturation", cfg.saturation)
        composite.setShaderInput("u_lift", Vec3(0.006, 0.004, 0.012))
        composite.setShaderInput("u_gain", Vec3(1.02, 1.0, 0.985))
        composite.setShaderInput("u_godrayStrength", cfg.godray_strength if cfg.godrays else 0.0)
        self.composite = composite

        # --- FXAA to screen ------------------------------------------------
        if cfg.fxaa:
            self.final_quad.setShader(make_shader("fullscreen.vert", "fxaa.frag"))
            self.final_quad.setShaderInput("u_source", self.ldr_tex)
        else:
            self.final_quad.setShader(make_shader("fullscreen.vert", "blit.frag"))
            self.final_quad.setShaderInput("u_source", self.ldr_tex)

    def _make_global_inputs(self):
        """Scene-wide uniforms live in arrays we mutate in place.

        Calling setShaderInput on render every frame builds a new ShaderAttrib
        and invalidates the cached render state of every node beneath it — with
        a few hundred props that costs more CPU than drawing the frame. Binding
        a PTA once and writing into it leaves the attrib untouched.
        """
        base = self.base
        self.pta_sun_dir = PTA_LVecBase3f.emptyArray(1)
        self.pta_camera = PTA_LVecBase3f.emptyArray(1)
        self.pta_fog_tint = PTA_LVecBase3f.emptyArray(1)
        self.pta_time = PTA_float.emptyArray(1)
        self.pta_ambient = PTA_float.emptyArray(1)
        self.pta_ambient[0] = 1.0
        base.render.setShaderInput("u_sunDirWorld", self.pta_sun_dir)
        base.render.setShaderInput("u_cameraWorld", self.pta_camera)
        base.render.setShaderInput("u_fogTint", self.pta_fog_tint)
        base.render.setShaderInput("u_time", self.pta_time)
        base.render.setShaderInput("u_ambientScale", self.pta_ambient)

    def set_ambient_scale(self, value: float):
        self.pta_ambient[0] = value

    # ------------------------------------------------------------- materials

    def apply_scene_shader(self, np_: NodePath, *, wind: float = 0.0,
                           wind_pivot: float = 0.0, alpha_cutoff: float = 0.0,
                           albedo_map: bool = False, micro_detail: float = 0.0,
                           priority: int = 0):
        """Attach the main PBR shader with per-node options."""
        shader = make_shader("scene.vert", "scene.frag",
                             {"NUM_LIGHTS": 1 + NUM_POINT_LIGHTS})
        np_.setShader(shader, priority)
        np_.setShaderInput("u_skyLut", self.skylut_tex)
        np_.setShaderInput("u_wind", Vec4(0.82, 0.57, 0.0, wind))
        np_.setShaderInput("u_windPivot", wind_pivot)
        np_.setShaderInput("u_alphaCutoff", alpha_cutoff)
        np_.setShaderInput("u_hasAlbedoMap", 1.0 if albedo_map else 0.0)
        np_.setShaderInput("u_microDetail", micro_detail)
        np_.setShaderInput("u_shadowTexel", 1.0 / self.cfg.shadow_size)
        np_.setShaderInput("u_shadowWorldTexel",
                           self.cfg.shadow_extent * 2.0 / self.cfg.shadow_size)
        np_.setShaderInput("u_shadowBias", self.cfg.shadow_bias)
        np_.setShaderInput("u_fogDensity", self.cfg.fog_density)
        if not albedo_map:
            np_.setShaderInput("p3d_Texture0", self.white_tex)

    def set_point_light(self, index: int, pos, color, attenuation=(1.0, 0.09, 0.045)):
        # Touching a Light rebuilds the LightAttrib and invalidates cached state
        # for the whole scene, so only write when something actually moved.
        np_ = self.point_lights[index]
        key = (round(pos[0], 2), round(pos[1], 2), round(pos[2], 2),
               round(color[0], 3), round(color[1], 3), round(color[2], 3),
               attenuation)
        if self._light_state.get(index) == key:
            return
        self._light_state[index] = key
        np_.setPos(*pos)
        np_.node().setColor(Vec4(*color, 1.0))
        np_.node().setAttenuation(Vec3(*attenuation))

    # ---------------------------------------------------------------- update

    def _snap_sun(self, focus: Vec3):
        """Position the sun's shadow frustum around the focus, snapped to texels."""
        cfg = self.cfg
        dist = 190.0
        self.sun_np.setPos(focus + self.light_dir * dist)
        self.sun_np.lookAt(focus)

        # Quantise the focus in the light's own basis to stop shadow crawl.
        light_mat = self.sun_np.getMat(self.base.render)
        inv = LMatrix4(light_mat)
        inv.invertInPlace()
        local = inv.xformPoint(Point3(focus))
        texel = (cfg.shadow_extent * 2.0) / cfg.shadow_size
        snapped = Point3(round(local.x / texel) * texel,
                         local.y,
                         round(local.z / texel) * texel)
        world = light_mat.xformPoint(snapped)
        key = (round(world[0], 3), round(world[1], 3), round(world[2], 3),
               round(self.light_dir[0], 4), round(self.light_dir[1], 4),
               round(self.light_dir[2], 4))
        if key == self._sun_focus_key:
            return
        self._sun_focus_key = key
        self.sun_np.setPos(Vec3(world) + self.light_dir * dist)
        self.sun_np.lookAt(Vec3(world))

    def update(self, dt: float, cam_pos: Vec3, focus: Vec3 | None = None):
        self.time += dt
        base = self.base

        self._snap_sun(focus if focus is not None else cam_pos)
        colour_key = (round(self.sun_color[0], 3), round(self.sun_color[1], 3),
                      round(self.sun_color[2], 3))
        if colour_key != self._sun_colour_key:
            self._sun_colour_key = colour_key
            self.sun.setColor(Vec4(*self.sun_color, 1.0))

        # Sky table.
        self.skylut_quad.setShaderInput("u_sunDirWorld", self.sun_dir)
        self.skylut_quad.setShaderInput("u_sunIntensity", self.sky_intensity)
        self.skylut_quad.setShaderInput("u_time", self.time)
        self.skylut_quad.setShaderInput("u_cloudCover", self.cloud_cover)

        self.sky.setShaderInput("u_sunDirWorld", self.sun_dir)
        self.sky.setShaderInput("u_sunIntensity", self.sky_intensity)
        self.sky.setShaderInput("u_time", self.time)
        self.sky.setShaderInput("u_cloudCover", self.cloud_cover)

        self.pta_sun_dir[0] = self.light_dir
        self.pta_camera[0] = cam_pos
        self.pta_fog_tint[0] = self.fog_tint
        self.pta_time[0] = self.time

        size_key = (base.win.getXSize(), base.win.getYSize())
        resized = size_key != self._size_key
        self._size_key = size_key

        if self.ao_quad is not None:
            lens = base.camLens
            proj = LMatrix4(lens.getProjectionMat())
            inv_proj = LMatrix4(lens.getProjectionMatInv())
            self.ao_quad.setShaderInput("u_proj", proj)
            self.ao_quad.setShaderInput("u_invProj", inv_proj)
            self.ao_quad.setShaderInput("u_time", self.time)
            if resized:
                w, h = max(size_key[0], 1), max(size_key[1], 1)
                self.ao_quad.setShaderInput("u_texel", Vec3(2.0 / w, 2.0 / h, 0.0).xy)
                self.ao_blur_h.setShaderInput("u_direction", Vec3(2.0 / w, 0.0, 0.0).xy)
                self.ao_blur_v.setShaderInput("u_direction", Vec3(0.0, 2.0 / h, 0.0).xy)

        w, h = max(size_key[0], 1), max(size_key[1], 1)
        if self.bloom_levels and resized:
            self.bloom_pre.setShaderInput("u_texel", Vec3(1.0 / w, 1.0 / h, 0).xy)
            for (hq, _ht, vq, _vt, div) in self.bloom_levels:
                hq.setShaderInput("u_direction", Vec3(float(div) / w, 0.0, 0.0).xy)
                vq.setShaderInput("u_direction", Vec3(0.0, float(div) / h, 0.0).xy)

        # Exposure eases towards the target so day/night transitions are smooth.
        self._exposure += (self.exposure_target - self._exposure) * min(dt * 0.9, 1.0)
        self.composite.setShaderInput("u_exposure", self._exposure)
        self.composite.setShaderInput("u_time", self.time)

        sun_uv, visible = self._sun_screen_pos()
        self.composite.setShaderInput("u_sunScreenPos", sun_uv)
        self.composite.setShaderInput("u_sunVisibility", visible)

        if self.cfg.fxaa and resized:
            self.final_quad.setShaderInput("u_texel", Vec3(1.0 / w, 1.0 / h, 0).xy)

    def _sun_screen_pos(self):
        """Project the sun onto the screen for the god-ray sweep."""
        base = self.base
        if self.sun_dir.z <= 0.02:
            return Vec3(0.5, 0.5, 0).xy, 0.0
        world = base.camera.getPos(base.render) + self.sun_dir * 2000.0
        p = Point2()
        if not base.camLens.project(base.cam.getRelativePoint(base.render, Point3(world)), p):
            return Vec3(0.5, 0.5, 0).xy, 0.0
        uv = Vec3(p.x * 0.5 + 0.5, p.y * 0.5 + 0.5, 0.0)
        # Fade out as the sun leaves the frame.
        edge = max(abs(uv.x - 0.5), abs(uv.y - 0.5)) * 2.0
        vis = max(0.0, 1.0 - max(0.0, edge - 0.75) / 0.55)
        vis *= min(1.0, max(0.0, self.sun_dir.z * 5.0))
        return uv.xy, vis

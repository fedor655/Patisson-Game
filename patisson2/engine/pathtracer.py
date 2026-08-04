"""Photo mode: a GPU path tracer over the scene's own geometry.

Pressing P freezes the frame, walks the scene graph into a flat triangle soup,
builds a BVH, uploads both to the GPU and then accumulates path-traced samples
until the image is clean. Everything the raster path fakes — ambient occlusion,
soft shadows, bounce light — is computed for real here.
"""

from __future__ import annotations

import time

import numpy as np
from panda3d.core import (
    CardMaker,
    GeomEnums,
    GeomVertexReader,
    Point3,
    NodePath,
    OmniBoundingVolume,
    SamplerState,
    ShaderAttrib,
    ShaderBuffer,
    Texture,
    Vec3,
    Vec4,
)

from .shaderlib import make_compute, make_shader

MAX_TRIANGLES = 260_000
LEAF_SIZE = 4
SUN_ANGULAR_RADIUS = 0.0093     # radians; the real sun is ~0.0047, softened a bit


class SceneGeometry:
    """Triangle soup + BVH pulled out of the live scene graph."""

    def __init__(self, verts: np.ndarray, colors: np.ndarray):
        self.verts = verts        # (n, 3, 3) float32 world-space
        self.colors = colors      # (n, 4) float32 rgb + emissive
        self.nodes: np.ndarray | None = None
        self.order: np.ndarray | None = None

    @property
    def count(self) -> int:
        return len(self.verts)

    def build_bvh(self) -> None:
        """Median-split BVH. Recursion is over node ranges, so the Python cost
        scales with node count rather than triangle count."""
        n = self.count
        centroids = self.verts.mean(axis=1)
        # Per-triangle bounds up front: the build then indexes (n, 3) arrays
        # instead of copying (n, 3, 3) at every node.
        tri_min = self.verts.min(axis=1)
        tri_max = self.verts.max(axis=1)
        order = np.arange(n, dtype=np.int64)

        # Each node: bmin(3), left, bmax(3), count, first, pad(3)
        nodes: list[list] = []

        def add_node() -> int:
            nodes.append([0.0] * 12)
            return len(nodes) - 1

        def build(start: int, end: int) -> int:
            idx = add_node()
            sub = order[start:end]
            bmin = tri_min[sub].min(axis=0)
            bmax = tri_max[sub].max(axis=0)
            node = nodes[idx]
            node[0:3] = bmin.tolist()
            node[4:7] = bmax.tolist()

            if end - start <= LEAF_SIZE:
                node[3] = -1.0                 # leaf marker
                node[7] = float(end - start)
                node[8] = float(start)
                return idx

            extent = bmax - bmin
            axis = int(np.argmax(extent))
            c = centroids[sub, axis]
            mid = (start + end) // 2
            part = np.argpartition(c, mid - start)
            order[start:end] = sub[part]

            left = build(start, mid)
            right = build(mid, end)
            nodes[idx][3] = float(left)
            nodes[idx][8] = float(right)
            return idx

        import sys
        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(limit, 20000))
        try:
            build(0, n)
        finally:
            sys.setrecursionlimit(limit)

        self.nodes = np.array(nodes, dtype=np.float32)
        self.order = order


# The terrain mesh carries no vertex colours — its look comes from a procedural
# shader — so the tracer needs its own approximation of that palette.
TERRAIN_ALBEDO = np.array([0.115, 0.175, 0.055], dtype=np.float32)
TERRAIN_DRY = np.array([0.19, 0.19, 0.085], dtype=np.float32)


def extract_scene(base, centre: Vec3, radius: float,
                  skip_names=("sky", "grass", "water")) -> SceneGeometry:
    """Read every visible GeomNode near ``centre`` into world-space triangles.

    Props are collected before the terrain: the ground is by far the biggest
    mesh, and if it goes first it eats the whole triangle budget and the trees
    and buildings never make it in.
    """
    verts_out: list[np.ndarray] = []
    cols_out: list[np.ndarray] = []
    r2 = radius * radius
    total = 0

    candidates = []
    for np_ in base.render.findAllMatches("**/+GeomNode"):
        if np_.isHidden():
            continue
        name = np_.getName().lower()
        parent_names = " ".join(p.getName().lower() for p in np_.getAncestors())
        if any(s in name or s in parent_names for s in skip_names):
            continue
        is_terrain = "terrain" in name or "terrain" in parent_names
        origin = np_.getMat(base.render).xformPoint(Point3(0, 0, 0))
        dist = ((origin[0] - centre.x) ** 2 + (origin[1] - centre.y) ** 2
                + (origin[2] - centre.z) ** 2)
        # Ground first — without it everything floats — then the nearest props,
        # so the triangle budget goes to what fills the frame.
        candidates.append((0 if is_terrain else 1, dist, is_terrain, np_))
    candidates.sort(key=lambda c: (c[0], c[1]))

    for _prio, _dist, is_terrain, np_ in candidates:
        if total > MAX_TRIANGLES:
            break
        mat = np_.getMat(base.render)
        node = np_.node()
        for gi in range(node.getNumGeoms()):
            geom = node.getGeom(gi).decompose()
            vdata = geom.getVertexData()
            reader = GeomVertexReader(vdata, "vertex")
            has_colour = vdata.hasColumn("color")
            creader = GeomVertexReader(vdata, "color") if has_colour else None

            positions = []
            colours = []
            while not reader.isAtEnd():
                p = reader.getData3()
                w = mat.xformPoint(p)
                positions.append((w[0], w[1], w[2]))
                if creader is not None:
                    c = creader.getData4()
                    colours.append((c[0], c[1], c[2]))
                elif is_terrain:
                    # Rough stand-in for the terrain shader's grass/soil blend.
                    t = min(max((w[2] + 1.0) * 0.10, 0.0), 1.0)
                    col = TERRAIN_ALBEDO * (1.0 - t) + TERRAIN_DRY * t
                    colours.append((col[0], col[1], col[2]))
                else:
                    colours.append((0.55, 0.52, 0.48))
            if not positions:
                continue
            positions = np.array(positions, dtype=np.float32)
            colours = np.array(colours, dtype=np.float32)

            # Material colour scales the vertex colour, same as the raster path.
            state_colour = np_.getColorScale()
            colours *= np.array([state_colour[0], state_colour[1],
                                 state_colour[2]], dtype=np.float32)

            for pi in range(geom.getNumPrimitives()):
                prim = geom.getPrimitive(pi)
                idx = np.array(prim.getVertexList(), dtype=np.int64)
                if idx.size < 3:
                    continue
                idx = idx[: (idx.size // 3) * 3].reshape(-1, 3)
                tri = positions[idx]                        # (m, 3, 3)
                centre_np = np.array([centre.x, centre.y, centre.z],
                                     dtype=np.float32)
                d = ((tri.mean(axis=1) - centre_np) ** 2).sum(axis=1)
                keep = d < r2
                if not keep.any():
                    continue
                tri = tri[keep]
                col = colours[idx[keep]].mean(axis=1)
                verts_out.append(tri)
                cols_out.append(col)
                total += len(tri)
                if total > MAX_TRIANGLES:
                    break
            if total > MAX_TRIANGLES:
                break
        if total > MAX_TRIANGLES:
            break

    if not verts_out:
        raise RuntimeError("нет геометрии для трассировки")

    verts = np.concatenate(verts_out).astype(np.float32)
    cols = np.concatenate(cols_out).astype(np.float32)
    emissive = np.zeros((len(cols), 1), dtype=np.float32)
    # Anything very bright in the palette (lantern glass) also emits.
    bright = cols.max(axis=1) > 0.92
    emissive[bright, 0] = 0.9
    return SceneGeometry(verts, np.concatenate([cols, emissive], axis=1))


class PathTracer:
    def __init__(self, base, cfg):
        self.base = base
        self.cfg = cfg
        gsg = base.win.getGsg()
        if not gsg.getSupportsComputeShaders():
            raise RuntimeError("нужны compute-шейдеры (OpenGL 4.3+)")

        self.shader = make_compute("pathtrace.comp")
        self.width = base.win.getXSize()
        self.height = base.win.getYSize()

        self.accum = Texture("pt-accum")
        self.accum.setup2dTexture(self.width, self.height, Texture.TFloat,
                                  Texture.FRgba32)
        self.accum.setClearColor(Vec4(0, 0, 0, 0))
        self.accum.setMinfilter(SamplerState.FT_linear)
        self.accum.setMagfilter(SamplerState.FT_linear)

        # Fullscreen card that resolves the accumulator over the game view.
        cm = CardMaker("pt-display")
        cm.setFrameFullscreenQuad()
        self.display = base.render2d.attachNewNode(cm.generate())
        self.display.setShader(make_shader("fullscreen.vert", "pathtrace_resolve.frag"))
        self.display.setShaderInput("u_accum", self.accum)
        self.display.setShaderInput("u_exposure", cfg.exposure)
        self.display.node().setBounds(OmniBoundingVolume())
        self.display.node().setFinal(True)
        self.display.hide()

        self.geometry: SceneGeometry | None = None
        self.tri_buffer = None
        self.node_buffer = None
        self.frame = 0
        self.samples = 0
        self.active = False
        self.build_seconds = 0.0

    # ------------------------------------------------------------------ setup

    def _upload(self, geo: SceneGeometry):
        order = geo.order
        verts = geo.verts[order]
        cols = geo.colors[order]

        n = len(verts)
        tri_data = np.zeros((n, 4, 4), dtype=np.float32)
        tri_data[:, 0, :3] = verts[:, 0]
        tri_data[:, 1, :3] = verts[:, 1]
        tri_data[:, 2, :3] = verts[:, 2]
        tri_data[:, 3, :] = cols

        self.tri_buffer = ShaderBuffer("TriBuffer", tri_data.tobytes(),
                                       GeomEnums.UH_static)
        self.node_buffer = ShaderBuffer("NodeBuffer", geo.nodes.tobytes(),
                                        GeomEnums.UH_static)

    def begin(self, player, sky):
        t0 = time.time()
        centre = player.eye
        geo = extract_scene(self.base, centre, radius=44.0)
        geo.build_bvh()
        self._upload(geo)
        self.geometry = geo
        self.build_seconds = time.time() - t0
        self.frame = 0
        self.samples = 0
        self.active = True
        self.display.show()
        print(f"[photo] {geo.count} triangles, {len(geo.nodes)} BVH nodes, "
              f"built in {self.build_seconds:.1f}s", flush=True)

    def end(self):
        self.active = False
        self.display.hide()

    # ----------------------------------------------------------------- render

    def step(self, player, sky):
        if not self.active or self.geometry is None:
            return
        if self.samples >= self.cfg.pt_target_samples:
            return

        base = self.base
        cam = base.camera
        quat = cam.getQuat(base.render)
        forward = quat.getForward()
        right = quat.getRight()
        up = quat.getUp()

        lens = base.camLens
        tan_half_v = np.tan(np.radians(lens.getVfov() * 0.5))
        tan_half_h = np.tan(np.radians(lens.getHfov() * 0.5))

        attrib = ShaderAttrib.make(self.shader)
        attrib = attrib.setShaderInput("u_accum", self.accum)
        attrib = attrib.setShaderInput("TriBuffer", self.tri_buffer)
        attrib = attrib.setShaderInput("NodeBuffer", self.node_buffer)
        attrib = attrib.setShaderInput("u_skyLut", base.pipeline.skylut_tex)
        attrib = attrib.setShaderInput("u_camPos", player.eye)
        attrib = attrib.setShaderInput("u_camForward", Vec3(forward))
        attrib = attrib.setShaderInput("u_camRight", Vec3(right))
        attrib = attrib.setShaderInput("u_camUp", Vec3(up))
        attrib = attrib.setShaderInput("u_tanHalfFov",
                                       Vec3(tan_half_h, tan_half_v, 0).xy)
        attrib = attrib.setShaderInput("u_sunDir", sky.light_dir)
        attrib = attrib.setShaderInput("u_sunColor", sky.sun_color)
        attrib = attrib.setShaderInput("u_sunAngularRadius", SUN_ANGULAR_RADIUS)
        attrib = attrib.setShaderInput("u_samples", self.cfg.pt_samples_per_frame)
        attrib = attrib.setShaderInput("u_maxBounces", self.cfg.pt_max_bounces)
        attrib = attrib.setShaderInput("u_frame", self.frame)
        attrib = attrib.setShaderInput("u_reset", 1 if self.frame == 0 else 0)
        attrib = attrib.setShaderInput("u_resolution",
                                       Vec3(self.width, self.height, 0).xy)

        gx = (self.width + 7) // 8
        gy = (self.height + 7) // 8
        base.graphicsEngine.dispatch_compute((gx, gy, 1), attrib, base.win.getGsg())

        self.frame += 1
        self.samples += self.cfg.pt_samples_per_frame
        self.display.setShaderInput("u_exposure", sky.exposure)
        self.display.setShaderInput("u_samples", float(self.samples))

    @property
    def progress(self) -> float:
        return min(1.0, self.samples / max(self.cfg.pt_target_samples, 1))

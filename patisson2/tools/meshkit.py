"""A tiny procedural modelling kit and a glTF 2.0 (.glb) writer.

Everything the game renders is built from code here and baked to .glb files that
live in the repository. That keeps the assets small, inspectable, diffable and
regenerable — no 400 MB installer needed to run from source.

Models are authored Z-up (Panda3D's convention). The writer rotates into glTF's
Y-up on the way out, so panda3d-gltf's own conversion lands them back Z-up.
"""

from __future__ import annotations

import base64
import json
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

Vec = tuple[float, float, float]


# --------------------------------------------------------------------- mesh


@dataclass
class Mesh:
    verts: list = field(default_factory=list)     # (x, y, z)
    norms: list = field(default_factory=list)
    colors: list = field(default_factory=list)    # (r, g, b)
    faces: list = field(default_factory=list)     # (i, j, k)

    def add_face(self, a: Vec, b: Vec, c: Vec, color: Vec, normal: Vec | None = None):
        if normal is None:
            normal = face_normal(a, b, c)
        base = len(self.verts)
        for p in (a, b, c):
            self.verts.append(p)
            self.norms.append(normal)
            self.colors.append(color)
        self.faces.append((base, base + 1, base + 2))

    def add_quad(self, a: Vec, b: Vec, c: Vec, d: Vec, color: Vec):
        n = face_normal(a, b, c)
        self.add_face(a, b, c, color, n)
        self.add_face(a, c, d, color, n)

    def extend(self, other: "Mesh"):
        offset = len(self.verts)
        self.verts.extend(other.verts)
        self.norms.extend(other.norms)
        self.colors.extend(other.colors)
        self.faces.extend([(i + offset, j + offset, k + offset) for i, j, k in other.faces])
        return self

    # ---- transforms (all return self so they chain) ----

    def _apply(self, fn, fn_normal=None):
        self.verts = [fn(p) for p in self.verts]
        if fn_normal is not None:
            self.norms = [normalize(fn_normal(n)) for n in self.norms]
        return self

    def translate(self, dx=0.0, dy=0.0, dz=0.0):
        return self._apply(lambda p: (p[0] + dx, p[1] + dy, p[2] + dz))

    def scale(self, sx=1.0, sy=None, sz=None):
        sy = sx if sy is None else sy
        sz = sx if sz is None else sz
        self._apply(lambda p: (p[0] * sx, p[1] * sy, p[2] * sz),
                    lambda n: (n[0] / sx, n[1] / sy, n[2] / sz))
        return self

    def rotate_z(self, deg: float):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        f = lambda p: (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])
        return self._apply(f, f)

    def rotate_x(self, deg: float):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        f = lambda p: (p[0], p[1] * c - p[2] * s, p[1] * s + p[2] * c)
        return self._apply(f, f)

    def rotate_y(self, deg: float):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        f = lambda p: (p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c)
        return self._apply(f, f)

    def tint(self, color: Vec, amount: float = 1.0):
        self.colors = [lerp3(c, color, amount) for c in self.colors]
        return self

    def jitter_colors(self, amount: float, seed: int = 0):
        rng = np.random.default_rng(seed)
        out = []
        for c in self.colors:
            k = 1.0 + float(rng.uniform(-amount, amount))
            out.append((min(c[0] * k, 1.0), min(c[1] * k, 1.0), min(c[2] * k, 1.0)))
        self.colors = out
        return self

    def smooth(self, angle_deg: float = 62.0):
        """Average normals between faces that meet at a shallow angle."""
        key_map: dict[tuple, list[int]] = {}
        for i, p in enumerate(self.verts):
            key = (round(p[0], 4), round(p[1], 4), round(p[2], 4))
            key_map.setdefault(key, []).append(i)
        limit = math.cos(math.radians(angle_deg))
        new = list(self.norms)
        for idxs in key_map.values():
            if len(idxs) < 2:
                continue
            for i in idxs:
                acc = [0.0, 0.0, 0.0]
                for j in idxs:
                    if dot(self.norms[i], self.norms[j]) >= limit:
                        acc[0] += self.norms[j][0]
                        acc[1] += self.norms[j][1]
                        acc[2] += self.norms[j][2]
                if acc != [0.0, 0.0, 0.0]:
                    new[i] = normalize(tuple(acc))
        self.norms = new
        return self

    def bounds(self):
        a = np.array(self.verts, dtype=np.float64)
        return a.min(axis=0), a.max(axis=0)

    @property
    def tri_count(self) -> int:
        return len(self.faces)


# ------------------------------------------------------------------- vector


def face_normal(a: Vec, b: Vec, c: Vec) -> Vec:
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    return normalize((u[1] * v[2] - u[2] * v[1],
                      u[2] * v[0] - u[0] * v[2],
                      u[0] * v[1] - u[1] * v[0]))


def normalize(v: Vec) -> Vec:
    n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if n < 1e-12:
        return (0.0, 0.0, 1.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def lerp3(a: Vec, b: Vec, t: float) -> Vec:
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


# --------------------------------------------------------------- primitives


def box(sx: float, sy: float, sz: float, color: Vec,
        origin: str = "center") -> Mesh:
    """Axis-aligned box.

    ``origin`` only controls the Z axis: "center" straddles z=0, "base" sits on
    it. X and Y are *always* centred — the old name for "base" was "corner",
    which read as if it moved all three axes and led to walls being built half a
    width out of place.
    """
    m = Mesh()
    hx, hy = sx / 2, sy / 2
    z0, z1 = (-sz / 2, sz / 2) if origin == "center" else (0.0, sz)
    p = [(-hx, -hy, z0), (hx, -hy, z0), (hx, hy, z0), (-hx, hy, z0),
         (-hx, -hy, z1), (hx, -hy, z1), (hx, hy, z1), (-hx, hy, z1)]
    m.add_quad(p[3], p[2], p[1], p[0], color)     # bottom
    m.add_quad(p[4], p[5], p[6], p[7], color)     # top
    m.add_quad(p[0], p[1], p[5], p[4], color)
    m.add_quad(p[1], p[2], p[6], p[5], color)
    m.add_quad(p[2], p[3], p[7], p[6], color)
    m.add_quad(p[3], p[0], p[4], p[7], color)
    return m


def revolve(profile: list[tuple[float, float]], segments: int, color: Vec,
            close_bottom: bool = True, close_top: bool = True,
            twist: float = 0.0, lobes: int = 0, lobe_depth: float = 0.0) -> Mesh:
    """Spin a (radius, z) profile around the Z axis.

    ``lobes`` adds a cosine ripple to the radius, which is how the patisson gets
    its scalloped edge.
    """
    m = Mesh()
    rings = []
    for k, (r, z) in enumerate(profile):
        ring = []
        for i in range(segments):
            t = i / segments * math.tau + math.radians(twist) * (k / max(len(profile) - 1, 1))
            rr = r
            if lobes:
                rr = r * (1.0 + lobe_depth * math.cos(t * lobes))
            ring.append((rr * math.cos(t), rr * math.sin(t), z))
        rings.append(ring)

    for k in range(len(rings) - 1):
        lo, hi = rings[k], rings[k + 1]
        for i in range(segments):
            j = (i + 1) % segments
            m.add_quad(lo[i], lo[j], hi[j], hi[i], color)

    if close_bottom and profile[0][0] > 1e-6:
        c = (0.0, 0.0, profile[0][1])
        ring = rings[0]
        for i in range(segments):
            j = (i + 1) % segments
            m.add_face(c, ring[j], ring[i], color)
    if close_top and profile[-1][0] > 1e-6:
        c = (0.0, 0.0, profile[-1][1])
        ring = rings[-1]
        for i in range(segments):
            j = (i + 1) % segments
            m.add_face(c, ring[i], ring[j], color)
    return m


def cylinder(radius: float, height: float, color: Vec, segments: int = 16,
             radius_top: float | None = None) -> Mesh:
    rt = radius if radius_top is None else radius_top
    return revolve([(radius, 0.0), (rt, height)], segments, color)


def cone(radius: float, height: float, color: Vec, segments: int = 16) -> Mesh:
    return revolve([(radius, 0.0), (0.0001, height)], segments, color)


def sphere(radius: float, color: Vec, segments: int = 20, rings: int = 12,
           squash: float = 1.0) -> Mesh:
    profile = []
    for i in range(rings + 1):
        a = i / rings * math.pi
        profile.append((radius * math.sin(a), -radius * math.cos(a) * squash))
    return revolve(profile, segments, color, close_bottom=False, close_top=False).smooth(85)


def capsule(radius: float, height: float, color: Vec, segments: int = 14) -> Mesh:
    profile = [(0.0001, 0.0)]
    for i in range(1, 7):
        a = i / 6 * math.pi / 2
        profile.append((radius * math.sin(a), radius * (1 - math.cos(a))))
    profile.append((radius, height - radius))
    for i in range(1, 7):
        a = i / 6 * math.pi / 2
        profile.append((radius * math.cos(a), height - radius + radius * math.sin(a)))
    return revolve(profile, segments, color).smooth(85)


def tube(path: list[Vec], radii: list[float], color: Vec, segments: int = 8) -> Mesh:
    """Sweep a circle along a polyline — branches, ropes, handles, stems."""
    m = Mesh()
    rings = []
    for i, p in enumerate(path):
        if i == 0:
            d = sub(path[1], path[0])
        elif i == len(path) - 1:
            d = sub(path[-1], path[-2])
        else:
            d = sub(path[i + 1], path[i - 1])
        d = normalize(d)
        up = (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 else (1.0, 0.0, 0.0)
        right = normalize(cross(up, d))
        realup = cross(d, right)
        ring = []
        for s in range(segments):
            t = s / segments * math.tau
            c, sn = math.cos(t), math.sin(t)
            r = radii[i]
            ring.append((p[0] + (right[0] * c + realup[0] * sn) * r,
                         p[1] + (right[1] * c + realup[1] * sn) * r,
                         p[2] + (right[2] * c + realup[2] * sn) * r))
        rings.append(ring)
    for k in range(len(rings) - 1):
        lo, hi = rings[k], rings[k + 1]
        for i in range(segments):
            j = (i + 1) % segments
            m.add_quad(lo[i], lo[j], hi[j], hi[i], color)
    return m.smooth(70)


def leaf(length: float, width: float, color: Vec, curl: float = 0.25,
         segments: int = 6) -> Mesh:
    """A single flat leaf blade lying along +X, hinged at the origin."""
    m = Mesh()
    pts = []
    for i in range(segments + 1):
        t = i / segments
        w = width * math.sin(t * math.pi) ** 0.7
        z = curl * length * (t ** 2)
        pts.append(((t * length, -w / 2, z), (t * length, w / 2, z)))
    for i in range(segments):
        a, b = pts[i]
        c, d = pts[i + 1]
        m.add_quad(a, c, d, b, color)
    return m.smooth(90)


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


# ---------------------------------------------------------------- glb writer


@dataclass
class Part:
    mesh: Mesh
    name: str = "part"
    roughness: float = 0.85
    metallic: float = 0.0
    emissive: Vec = (0.0, 0.0, 0.0)
    double_sided: bool = False
    alpha_mode: str = "OPAQUE"


def _pad4(b: bytes, fill: bytes = b"\0") -> bytes:
    """Chunks must be 4-byte aligned. The spec requires JSON padded with spaces
    and binary padded with zeros — nulls in the JSON chunk make strict parsers
    fail with "Extra data"."""
    return b + fill * (-len(b) % 4)


def write_glb(path: str | Path, parts: list[Part], name: str = "model") -> Path:
    """Write parts as a single-node .glb. Positions convert Z-up -> Y-up."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    bin_chunks: list[bytes] = []
    buffer_views = []
    accessors = []
    meshes_prims = []
    materials = []
    offset = 0

    def push(data: bytes, target: int | None) -> int:
        nonlocal offset
        data = _pad4(data)
        bin_chunks.append(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        buffer_views.append(view)
        offset += len(data)
        return len(buffer_views) - 1

    for part in parts:
        m = part.mesh
        if not m.faces:
            continue
        # Z-up -> Y-up: (x, y, z) -> (x, z, -y)
        pos = np.array([(p[0], p[2], -p[1]) for p in m.verts], dtype=np.float32)
        nrm = np.array([(n[0], n[2], -n[1]) for n in m.norms], dtype=np.float32)
        col = np.array([(c[0], c[1], c[2], 1.0) for c in m.colors], dtype=np.float32)
        idx = np.array(m.faces, dtype=np.uint32).ravel()

        v_pos = push(pos.tobytes(), 34962)
        v_nrm = push(nrm.tobytes(), 34962)
        v_col = push(col.tobytes(), 34962)
        v_idx = push(idx.tobytes(), 34963)

        a_pos = len(accessors)
        accessors.append({"bufferView": v_pos, "componentType": 5126,
                          "count": len(pos), "type": "VEC3",
                          "min": pos.min(axis=0).tolist(),
                          "max": pos.max(axis=0).tolist()})
        a_nrm = len(accessors)
        accessors.append({"bufferView": v_nrm, "componentType": 5126,
                          "count": len(nrm), "type": "VEC3"})
        a_col = len(accessors)
        accessors.append({"bufferView": v_col, "componentType": 5126,
                          "count": len(col), "type": "VEC4"})
        a_idx = len(accessors)
        accessors.append({"bufferView": v_idx, "componentType": 5125,
                          "count": len(idx), "type": "SCALAR"})

        mat = {
            "name": part.name,
            "pbrMetallicRoughness": {
                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                "metallicFactor": part.metallic,
                "roughnessFactor": part.roughness,
            },
            "doubleSided": part.double_sided,
        }
        if any(part.emissive):
            mat["emissiveFactor"] = list(part.emissive)
        if part.alpha_mode != "OPAQUE":
            mat["alphaMode"] = part.alpha_mode
        materials.append(mat)

        meshes_prims.append({
            "attributes": {"POSITION": a_pos, "NORMAL": a_nrm, "COLOR_0": a_col},
            "indices": a_idx,
            "material": len(materials) - 1,
        })

    blob = b"".join(bin_chunks)
    gltf = {
        "asset": {"version": "2.0", "generator": "patisson2.meshkit"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{"name": name, "primitives": meshes_prims}],
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(blob)}],
    }

    json_chunk = _pad4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), b" ")
    bin_chunk = _pad4(blob)
    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    out = bytearray()
    out += struct.pack("<III", 0x46546C67, 2, total)
    out += struct.pack("<II", len(json_chunk), 0x4E4F534A) + json_chunk
    out += struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk
    path.write_bytes(bytes(out))
    return path

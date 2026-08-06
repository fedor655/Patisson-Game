"""Builds every 3D model the game uses and writes them to ``assets/models``.

Run with:  python -m patisson2.tools.make_assets

Each model is a few dozen lines of geometry, so the whole asset set is a couple
of megabytes of .glb that lives in git — the game runs straight from a clone.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from .meshkit import (
    Mesh,
    Part,
    box,
    capsule,
    cone,
    cylinder,
    leaf,
    revolve,
    sphere,
    tube,
    write_glb,
)

OUT_DIR = Path(__file__).resolve().parents[2] / "assets" / "models"


def srgb(r: int, g: int, b: int):
    """Colour picked in 8-bit sRGB, stored linear (glTF COLOR_0 is linear)."""
    def c(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return (c(r), c(g), c(b))


# ------------------------------------------------------------------ palette

SQUASH = srgb(240, 214, 96)
SQUASH_RIPE = srgb(246, 200, 60)
SQUASH_PALE = srgb(226, 226, 150)
STEM = srgb(122, 148, 58)
LEAF_G = srgb(86, 136, 46)
LEAF_DARK = srgb(62, 104, 38)
WOOD = srgb(134, 96, 58)
WOOD_DARK = srgb(96, 66, 40)
WOOD_LIGHT = srgb(178, 140, 92)
PLANK = srgb(158, 118, 74)
ROOF_RED = srgb(150, 68, 52)
ROOF_SLATE = srgb(84, 88, 100)
STONE = srgb(122, 120, 116)
STONE_DARK = srgb(88, 86, 84)
METAL = srgb(150, 154, 160)
IRON = srgb(78, 80, 86)
WHITE = srgb(236, 236, 232)
CLOTH_RED = srgb(186, 76, 66)
CLOTH_BLUE = srgb(74, 112, 158)
CLOTH_CREAM = srgb(228, 214, 182)
SOIL = srgb(96, 68, 46)
BARK = srgb(104, 78, 56)
BARK_BIRCH = srgb(224, 220, 208)
FOLIAGE = srgb(74, 122, 48)
FOLIAGE_2 = srgb(94, 142, 58)
PINE = srgb(50, 92, 56)
ROCK = srgb(128, 126, 122)
SKIN = srgb(226, 178, 142)
HAIR = srgb(86, 60, 42)
CHICKEN = srgb(238, 234, 224)
COMB = srgb(198, 62, 52)
BEAK = srgb(226, 168, 62)
COW_W = srgb(240, 238, 232)
COW_B = srgb(58, 54, 52)
CAT = srgb(196, 138, 74)
FISH = srgb(140, 162, 178)
FLOWER_Y = srgb(236, 206, 82)
FLOWER_P = srgb(196, 112, 176)
FLOWER_W = srgb(238, 238, 230)
GOLD = srgb(224, 178, 62)
WATER_CAN = srgb(72, 132, 118)
LAMP_GLASS = srgb(252, 226, 158)


def _rng(seed):
    return random.Random(seed)


# ------------------------------------------------------------------- crops


def patisson_body(size: float, colour, ripeness: float) -> Mesh:
    """The scalloped pattypan squash — the game's namesake."""
    profile = []
    steps = 14
    for i in range(steps + 1):
        t = i / steps
        a = t * math.pi
        # Flattened sphere, slightly wider below the equator.
        r = math.sin(a) ** 0.78
        z = -math.cos(a) * 0.46
        r *= 1.0 + 0.10 * math.sin(a * 1.6)
        profile.append((r * size, z * size))
    m = revolve(profile, 30, colour, close_bottom=False, close_top=False,
                lobes=8, lobe_depth=0.055 + 0.045 * ripeness)
    m.smooth(70)
    # A dimple at the blossom end.
    m.extend(sphere(size * 0.16, colour).scale(1.0, 1.0, 0.5)
             .translate(0, 0, -size * 0.44))
    return m


def make_patisson(stage: int):
    """stage 0..3 — sprout, young, swelling, ripe."""
    parts: list[Part] = []
    body = Mesh()
    leaves = Mesh()

    if stage == 0:
        # Two seed leaves on a thin stem.
        body.extend(tube([(0, 0, 0), (0, 0, 0.09), (0.01, 0, 0.17)],
                         [0.014, 0.012, 0.010], STEM, 6))
        for ang in (20, 200):
            lf = leaf(0.13, 0.085, LEAF_G, curl=0.22, segments=5)
            lf.rotate_y(-18).rotate_z(ang).translate(0, 0, 0.16)
            leaves.extend(lf)
        size = 0.0
    else:
        size = {1: 0.10, 2: 0.17, 3: 0.26}[stage]
        ripeness = {1: 0.15, 2: 0.55, 3: 1.0}[stage]
        colour = {1: SQUASH_PALE, 2: SQUASH, 3: SQUASH_RIPE}[stage]
        b = patisson_body(size, colour, ripeness)
        b.translate(0, 0, size * 0.50)
        body.extend(b)
        # Stalk.
        body.extend(tube([(0, 0, size * 0.92), (0.01, 0.01, size * 1.05),
                          (0.03, 0.02, size * 1.16)],
                         [size * 0.10, size * 0.075, size * 0.05], STEM, 7))
        # Ground leaves fanning out.
        r = _rng(stage * 17 + 3)
        count = 3 + stage
        for i in range(count):
            ang = 360.0 * i / count + r.uniform(-18, 18)
            ln = size * (2.1 + r.uniform(-0.3, 0.5))
            lf = leaf(ln, ln * 0.72, LEAF_G if i % 2 else LEAF_DARK,
                      curl=0.18, segments=6)
            lf.rotate_y(-12 - r.uniform(0, 10)).rotate_z(ang)
            lf.translate(0, 0, 0.035 + size * 0.10)
            leaves.extend(lf)
            leaves.extend(tube([(0, 0, 0.03),
                                (math.cos(math.radians(ang)) * ln * 0.4,
                                 math.sin(math.radians(ang)) * ln * 0.4,
                                 0.03 + size * 0.10)],
                               [0.012, 0.009], STEM, 5))

    if body.faces:
        parts.append(Part(body, "patisson", roughness=0.58))
    parts.append(Part(leaves, "leaves", roughness=0.80, double_sided=True))
    return parts


def make_carrot():
    body = Mesh()
    profile = [(0.001, 0.0)]
    for i in range(1, 9):
        t = i / 8
        profile.append((0.055 * (t ** 0.55), t * 0.22))
    body.extend(revolve(profile, 12, srgb(224, 126, 46)).smooth(75))
    tops = Mesh()
    r = _rng(9)
    for i in range(7):
        ang = 360 * i / 7 + r.uniform(-20, 20)
        lf = leaf(0.20, 0.055, LEAF_G, curl=-0.45, segments=5)
        lf.rotate_y(-64 - r.uniform(0, 14)).rotate_z(ang).translate(0, 0, 0.21)
        tops.extend(lf)
    return [Part(body, "carrot", roughness=0.60),
            Part(tops, "tops", roughness=0.82, double_sided=True)]


def make_tomato_bush():
    stems = Mesh()
    fruit = Mesh()
    foliage = Mesh()
    r = _rng(21)
    stems.extend(tube([(0, 0, 0), (0.01, 0.01, 0.22), (0.0, 0.02, 0.42)],
                      [0.018, 0.014, 0.010], STEM, 6))
    for i in range(6):
        ang = 360 * i / 6 + r.uniform(-25, 25)
        h = 0.10 + r.uniform(0, 0.26)
        lf = leaf(0.16, 0.11, LEAF_G if i % 2 else LEAF_DARK, curl=0.2, segments=5)
        lf.rotate_y(-25).rotate_z(ang).translate(0, 0, h)
        foliage.extend(lf)
    for i in range(4):
        ang = math.radians(70 * i + r.uniform(-30, 30))
        d = 0.09 + r.uniform(0, 0.05)
        h = 0.16 + r.uniform(0, 0.18)
        fruit.extend(sphere(0.045 + r.uniform(0, 0.012), srgb(206, 60, 48))
                     .scale(1.0, 1.0, 0.9)
                     .translate(math.cos(ang) * d, math.sin(ang) * d, h))
    return [Part(stems, "stem", roughness=0.8),
            Part(foliage, "leaves", roughness=0.82, double_sided=True),
            Part(fruit, "tomato", roughness=0.42)]


def make_wheat():
    m = Mesh()
    r = _rng(33)
    gold = srgb(214, 184, 96)
    for i in range(9):
        ang = r.uniform(0, 360)
        d = r.uniform(0.0, 0.075)
        h = 0.42 + r.uniform(0, 0.16)
        lean = r.uniform(0.02, 0.07)
        x, y = math.cos(math.radians(ang)) * d, math.sin(math.radians(ang)) * d
        path = [(x, y, 0), (x + lean * 0.4, y, h * 0.6), (x + lean, y, h)]
        m.extend(tube(path, [0.007, 0.006, 0.005], srgb(190, 176, 110), 5))
        # Ear.
        ear = revolve([(0.001, 0.0), (0.022, 0.03), (0.024, 0.09), (0.001, 0.14)],
                      8, gold, lobes=5, lobe_depth=0.35)
        ear.translate(x + lean, y, h)
        m.extend(ear)
    return [Part(m, "wheat", roughness=0.86, double_sided=True)]


def make_pumpkin():
    body = revolve(
        [(0.001, -0.16)] +
        [(0.22 * math.sin(i / 10 * math.pi) ** 0.85, -math.cos(i / 10 * math.pi) * 0.17)
         for i in range(11)] +
        [(0.001, 0.16)],
        26, srgb(226, 132, 44), lobes=9, lobe_depth=0.075)
    body.smooth(70).translate(0, 0, 0.17)
    stalk = tube([(0, 0, 0.30), (0.01, 0.01, 0.38), (0.03, 0.0, 0.44)],
                 [0.032, 0.026, 0.020], srgb(112, 132, 62), 7)
    leaves = Mesh()
    for i in range(3):
        lf = leaf(0.30, 0.24, LEAF_DARK, curl=0.16, segments=5)
        lf.rotate_y(-10).rotate_z(120 * i + 25).translate(0, 0, 0.05)
        leaves.extend(lf)
    return [Part(body, "pumpkin", roughness=0.55),
            Part(stalk, "stalk", roughness=0.8),
            Part(leaves, "leaves", roughness=0.82, double_sided=True)]


# --------------------------------------------------------------- buildings


def plank_wall(w: float, h: float, colour, planks: int = 7, thick=0.06) -> Mesh:
    m = Mesh()
    step = h / planks
    for i in range(planks):
        shade = 1.0 - 0.06 * (i % 3)
        c = (colour[0] * shade, colour[1] * shade, colour[2] * shade)
        m.extend(box(w, thick, step * 0.94, c, origin="base")
                 .translate(0, 0, i * step))
    return m


def gable_roof(w: float, d: float, h: float, colour, overhang=0.35) -> Mesh:
    """Two slopes meeting at a ridge along Y, with gable ends.

    Winding matters: faces wound the other way point their normals into the
    building and get backface-culled, which reads as a roof with half of it
    missing.
    """
    m = Mesh()
    hw, hd = w / 2 + overhang, d / 2 + overhang
    apex_f = (0.0, -hd, h)
    apex_b = (0.0, hd, h)
    fl, fr = (-hw, -hd, 0.0), (hw, -hd, 0.0)
    bl, br = (-hw, hd, 0.0), (hw, hd, 0.0)
    dark = (colour[0] * 0.82, colour[1] * 0.82, colour[2] * 0.82)
    gable = (colour[0] * 0.7, colour[1] * 0.7, colour[2] * 0.7)
    m.add_quad(fl, apex_f, apex_b, bl, colour)      # left slope, normal -X +Z
    m.add_quad(fr, br, apex_b, apex_f, dark)        # right slope, normal +X +Z
    m.add_face(fl, fr, apex_f, gable)               # front gable, normal -Y
    m.add_face(bl, apex_b, br, gable)               # back gable, normal +Y
    return m


# House footprint, shared with the collision blockers in world/props.py.
HOUSE_W, HOUSE_D, HOUSE_H = 6.4, 7.8, 3.2
HOUSE_DOOR_W = 1.5
BARN_W, BARN_D, BARN_H = 8.0, 10.0, 3.8
BARN_DOOR_W = 3.0


def wall_with_gap(width: float, height: float, colour, gap: float,
                  gap_height: float, planks: int = 8) -> Mesh:
    """A plank wall with a doorway cut out of the middle."""
    m = Mesh()
    side = (width - gap) / 2.0
    if side > 0.02:
        for sx in (-1, 1):
            piece = plank_wall(side, height, colour, planks)
            m.extend(piece.translate(sx * (gap + side) / 2.0, 0, 0))
    # Lintel over the opening.
    lintel = height - gap_height
    if lintel > 0.05:
        m.extend(plank_wall(gap, lintel, colour, max(2, planks // 3))
                 .translate(0, 0, gap_height))
    return m


def make_bed(sheet=srgb(196, 206, 214), frame=WOOD_DARK):
    m = Mesh()
    m.extend(box(1.15, 2.05, 0.28, frame, origin="base"))
    m.extend(box(1.05, 1.95, 0.20, sheet, origin="base").translate(0, 0, 0.28))
    m.extend(box(0.60, 0.34, 0.14, srgb(238, 238, 232), origin="base")
             .translate(0, -0.74, 0.46))
    for sy in (-1.02, 1.02):
        m.extend(box(1.15, 0.10, 0.55 if sy < 0 else 0.36, frame, origin="base")
                 .translate(0, sy, 0))
    return m


def make_table_and_stools():
    m = Mesh()
    m.extend(box(1.5, 0.9, 0.09, PLANK, origin="base").translate(0, 0, 0.72))
    for sx in (-0.62, 0.62):
        for sy in (-0.32, 0.32):
            m.extend(box(0.09, 0.09, 0.72, WOOD_DARK, origin="base")
                     .translate(sx, sy, 0))
    for sy in (-0.85, 0.85):
        m.extend(cylinder(0.19, 0.06, PLANK, 10).translate(0, sy, 0.44))
        for a in (0, 120, 240):
            ang = math.radians(a)
            m.extend(box(0.055, 0.055, 0.44, WOOD_DARK, origin="base")
                     .translate(math.cos(ang) * 0.12 + 0, math.sin(ang) * 0.12 + sy, 0))
    return m


def make_shelf():
    m = Mesh()
    for z in (0.85, 1.35):
        m.extend(box(1.4, 0.32, 0.055, PLANK, origin="base").translate(0, 0, z))
    for sx in (-0.66, 0.66):
        m.extend(box(0.06, 0.32, 1.40, WOOD_DARK, origin="base").translate(sx, 0, 0))
    r = _rng(88)
    for i in range(7):
        x = -0.55 + i * 0.18
        z = 0.905 if i % 2 else 1.405
        m.extend(cylinder(0.055, r.uniform(0.14, 0.22),
                          r.choice([srgb(168, 132, 90), srgb(126, 148, 96),
                                    srgb(180, 96, 78)]), 8).translate(x, 0, z))
    return m


def make_hearth():
    stone = Mesh()
    fire = Mesh()
    stone.extend(box(1.7, 0.7, 0.35, STONE, origin="base"))
    stone.extend(box(1.7, 0.7, 1.9, STONE, origin="base").translate(0, 0.22, 0))
    stone.extend(box(1.25, 0.30, 1.05, srgb(28, 24, 22), origin="base")
                 .translate(0, -0.05, 0.32))
    r = _rng(91)
    for i in range(6):
        fire.extend(box(0.16, 0.10, 0.07, srgb(232, 122, 44), origin="base")
                    .rotate_z(r.uniform(0, 180))
                    .translate(r.uniform(-0.35, 0.35), -0.02, 0.36 + i * 0.03))
    for i in range(3):
        stone.extend(box(0.62, 0.11, 0.11, WOOD_DARK, origin="center")
                     .rotate_z(r.uniform(-25, 25))
                     .translate(r.uniform(-0.2, 0.2), -0.02, 0.42 + i * 0.09))
    return stone, fire


def make_house():
    body = Mesh()
    trim = Mesh()
    roof = Mesh()
    glass = Mesh()
    fire = Mesh()

    W, D, H = HOUSE_W, HOUSE_D, HOUSE_H

    # Front wall carries the doorway; the rest are solid.
    body.extend(wall_with_gap(W, H, PLANK, HOUSE_DOOR_W, 2.15)
                .translate(0, -D / 2, 0))
    body.extend(plank_wall(W, H, PLANK, 8).translate(0, D / 2, 0))
    for sx in (-W / 2, W / 2):
        body.extend(plank_wall(D, H, PLANK, 8).rotate_z(90).translate(sx, 0, 0))
    for sy in (-D / 2, D / 2):
        g = Mesh()
        g.add_face((-W / 2, sy, H), (W / 2, sy, H), (0, sy, H + 1.7), PLANK)
        body.extend(g)

    # Floor and a ceiling, so the inside is a room rather than a shell.
    # Deep enough that sloping ground can never poke through it.
    body.extend(box(W + 0.34, D + 0.34, 0.9, srgb(150, 116, 78), origin="base")
                .translate(0, 0, -0.84))
    body.extend(box(W - 0.2, D - 0.2, 0.10, WOOD_DARK, origin="base")
                .translate(0, 0, H - 0.10))
    for i in range(5):
        trim.extend(box(0.13, D - 0.3, 0.16, WOOD_DARK, origin="base")
                    .translate(-2.2 + i * 1.1, 0, H - 0.26))

    roof.extend(gable_roof(W, D, 1.7, ROOF_RED).translate(0, 0, H))
    trim.extend(box(0.14, D + 0.9, 0.14, WOOD_DARK).translate(0, 0, H + 1.72))
    for sx in (-W / 2, W / 2):
        for sy in (-D / 2, D / 2):
            trim.extend(box(0.20, 0.20, H, WOOD_DARK, origin="base")
                        .translate(sx, sy, 0))

    # Door frame and an open door swung inwards.
    for sx in (-1, 1):
        trim.extend(box(0.16, 0.22, 2.25, WOOD_DARK, origin="base")
                    .translate(sx * (HOUSE_DOOR_W / 2 + 0.08), -D / 2, 0))
    trim.extend(box(HOUSE_DOOR_W + 0.32, 0.22, 0.16, WOOD_DARK, origin="base")
                .translate(0, -D / 2, 2.25))
    door = box(1.42, 0.09, 2.1, WOOD_DARK, origin="base")
    door.rotate_z(-72).translate(-HOUSE_DOOR_W / 2, -D / 2 + 0.1, 0)
    trim.extend(door)
    trim.extend(sphere(0.05, GOLD).translate(-1.9, -D / 2 + 1.3, 1.05))

    for pos in ((-2.3, -D / 2), (2.3, -D / 2), (-W / 2, -1.4), (-W / 2, 1.4),
                (W / 2, 0.0)):
        x, y = pos
        along_y = abs(x) == W / 2
        fw, fd = (0.12, 1.1) if along_y else (1.1, 0.12)
        ox = 0.09 if x > 0 else -0.09
        trim.extend(box(fw + 0.16, fd + 0.16, 1.06, WOOD_LIGHT)
                    .translate(x + (ox if along_y else 0),
                               y + (0 if along_y else (-0.09 if y < 0 else 0.09)), 1.75))
        glass.extend(box(fw, fd, 0.88, srgb(150, 186, 200))
                     .translate(x + (ox * 1.3 if along_y else 0),
                                y + (0 if along_y else (-0.12 if y < 0 else 0.12)), 1.75))

    trim.extend(box(0.62, 0.62, 2.2, STONE, origin="base").translate(1.6, 1.2, H - 0.2))
    trim.extend(box(1.9, 0.7, 0.16, STONE, origin="base")
                .translate(0, -D / 2 - 0.75, 0))

    # --- furniture -------------------------------------------------------
    trim.extend(make_bed().translate(-1.55, 2.05, 0.0))
    trim.extend(make_table_and_stools().translate(1.35, -0.55, 0.0))
    trim.extend(make_shelf().translate(0, D / 2 - 0.25, 0.0))
    hearth_stone, hearth_fire = make_hearth()
    trim.extend(hearth_stone.rotate_z(-90).translate(W / 2 - 0.42, 1.2, 0.0))
    fire.extend(hearth_fire.rotate_z(-90).translate(W / 2 - 0.42, 1.2, 0.0))
    trim.extend(box(0.9, 0.6, 0.6, WOOD_DARK, origin="base")
                .translate(-W / 2 + 0.62, -2.5, 0))

    return [Part(body, "walls", roughness=0.88),
            Part(trim, "trim", roughness=0.82),
            Part(roof, "roof", roughness=0.90),
            Part(glass, "glass", roughness=0.14, metallic=0.0),
            Part(fire, "fire", roughness=0.7, emissive=(1.0, 0.44, 0.14))]


def make_barn():
    body = Mesh()
    trim = Mesh()
    roof = Mesh()
    hay = Mesh()
    W, D, H = 7.2, 9.0, 4.0
    red = srgb(150, 62, 52)
    door_w = 2.8

    body.extend(wall_with_gap(W, H, red, door_w, 3.0, 9).translate(0, -D / 2, 0))
    body.extend(plank_wall(W, H, red, 9).translate(0, D / 2, 0))
    for sx in (-W / 2, W / 2):
        body.extend(plank_wall(D, H, red, 9).rotate_z(90).translate(sx, 0, 0))
    for sy in (-D / 2, D / 2):
        g = Mesh()
        g.add_face((-W / 2, sy, H), (W / 2, sy, H), (0, sy, H + 2.3), red)
        body.extend(g)

    # Packed-earth floor and the loft above.
    body.extend(box(W + 0.34, D + 0.34, 0.9, srgb(104, 84, 62), origin="base")
                .translate(0, 0, -0.85))
    body.extend(box(W - 0.3, 2.6, 0.12, PLANK, origin="base")
                .translate(0, D / 2 - 1.4, H - 1.1))
    for i in range(6):
        trim.extend(box(0.12, D - 0.3, 0.20, WOOD_DARK, origin="base")
                    .translate(-2.8 + i * 1.12, 0, H - 0.22))

    roof.extend(gable_roof(W, D, 2.3, ROOF_SLATE, overhang=0.45).translate(0, 0, H))
    for sy in (-D / 2 - 0.02, D / 2 + 0.02):
        trim.extend(box(W + 0.1, 0.09, 0.18, WHITE).translate(0, sy, H - 0.1))
    # Door frame, and both leaves swung open against the wall.
    for sx in (-1, 1):
        trim.extend(box(0.14, 0.20, 3.1, WHITE, origin="base")
                    .translate(sx * (door_w / 2 + 0.07), -D / 2, 0))
        leaf = box(1.32, 0.10, 2.95, WOOD_DARK, origin="base")
        leaf.rotate_z(sx * 74).translate(sx * (door_w / 2), -D / 2 + 0.12, 0)
        trim.extend(leaf)
    trim.extend(box(door_w + 0.3, 0.16, 0.18, WHITE, origin="base")
                .translate(0, -D / 2, 3.1))
    trim.extend(box(1.3, 0.12, 1.1, WOOD_DARK, origin="base")
                .translate(0, -D / 2 - 0.09, H + 0.35))

    # --- inside ----------------------------------------------------------
    # Stalls down the left wall.
    for i in range(3):
        y = -2.4 + i * 2.3
        trim.extend(box(2.3, 0.10, 1.15, PLANK, origin="base")
                    .translate(-W / 2 + 1.2, y - 1.1, 0))
    trim.extend(box(0.10, 6.9, 1.15, PLANK, origin="base")
                .translate(-W / 2 + 2.35, -0.2, 0))
    # Feed trough on the right.
    trim.extend(box(0.72, 3.2, 0.46, WOOD_DARK, origin="base")
                .translate(W / 2 - 0.75, -0.6, 0))
    r = _rng(97)
    for i in range(9):
        hay.extend(box(0.62, 0.62, 0.44, srgb(206, 178, 96), origin="base")
                   .rotate_z(r.uniform(0, 90))
                   .translate(W / 2 - 1.9 + r.uniform(-0.2, 0.2),
                              2.2 + (i % 3) * 0.72,
                              0.44 * (i // 3)))
    for i in range(14):
        hay.extend(box(0.30, 0.06, 0.05, srgb(214, 190, 112), origin="base")
                   .rotate_z(r.uniform(0, 180))
                   .translate(r.uniform(-2.4, 2.4), r.uniform(-3.8, 3.8), 0.02))
    trim.extend(box(0.09, 0.09, 1.85, WOOD_DARK, origin="base")
                .rotate_y(16).translate(-W / 2 + 0.5, -3.6, 0))

    return [Part(body, "walls", roughness=0.9),
            Part(trim, "trim", roughness=0.85),
            Part(roof, "roof", roughness=0.92),
            Part(hay, "hay", roughness=0.95)]


def make_well():
    stone = Mesh()
    wood = Mesh()
    metal = Mesh()
    # Round stone kerb, deliberately irregular.
    r = _rng(5)
    ring = revolve([(0.78, 0.0), (0.80, 0.30), (0.86, 0.62), (0.82, 0.74),
                    (0.68, 0.74), (0.66, 0.0)], 22, STONE)
    stone.extend(ring.smooth(46))
    for i in range(20):
        a = math.radians(360 * i / 20 + r.uniform(-6, 6))
        h = 0.10 + r.uniform(0, 0.5)
        s = 0.16 + r.uniform(0, 0.09)
        stone.extend(box(s, s * 0.7, s * 0.7, STONE_DARK)
                     .rotate_z(math.degrees(a))
                     .translate(math.cos(a) * 0.83, math.sin(a) * 0.83, h))
    # Posts and roof.
    for sx in (-0.62, 0.62):
        wood.extend(box(0.14, 0.14, 1.75, WOOD, origin="base").translate(sx, 0, 0.7))
    wood.extend(gable_roof(1.9, 1.5, 0.52, WOOD_DARK, overhang=0.22)
                .translate(0, 0, 2.45))
    # Winding drum, crank and rope.
    metal.extend(cylinder(0.10, 1.15, WOOD_LIGHT, 12).rotate_y(90).translate(-0.575, 0, 2.1))
    metal.extend(tube([(0.62, 0, 2.10), (0.86, 0, 2.10), (0.86, 0.0, 1.86),
                       (0.98, 0.0, 1.86)],
                      [0.028, 0.028, 0.026, 0.024], IRON, 7))
    metal.extend(tube([(0, 0, 2.02), (0, 0, 1.20), (0, 0, 1.05)],
                      [0.012, 0.012, 0.012], srgb(196, 176, 132), 5))
    bucket = revolve([(0.16, 0), (0.19, 0.24)], 12, WOOD_DARK)
    bucket.extend(cylinder(0.185, 0.03, IRON, 12).translate(0, 0, 0.21))
    metal.extend(bucket.translate(0, 0, 0.80))
    # Standing water just under the kerb. The shaft used to be open to the
    # terrain, so looking in showed lawn growing at the bottom of the
    # "well" — the player noticed immediately. A still dark disc with a
    # glossy surface reads as deep water without cutting a hole in the
    # ground.
    water = Mesh()
    water.extend(cylinder(0.67, 0.025, srgb(20, 38, 44), 22).translate(0, 0, 0.34))
    return [Part(stone, "stone", roughness=0.93),
            Part(wood, "wood", roughness=0.88),
            Part(metal, "metal", roughness=0.45, metallic=0.65),
            Part(water, "water", roughness=0.07)]


def make_market_stall():
    wood = Mesh()
    cloth = Mesh()
    goods = Mesh()
    W, D = 2.6, 1.5
    for sx in (-W / 2, W / 2):
        for sy in (-D / 2, D / 2):
            wood.extend(box(0.09, 0.09, 2.05, WOOD, origin="base").translate(sx, sy, 0))
    wood.extend(box(W + 0.2, D + 0.1, 0.09, PLANK).translate(0, 0, 0.95))
    wood.extend(box(W + 0.2, D + 0.1, 0.07, WOOD_DARK).translate(0, 0, 0.30))
    # Striped awning.
    stripes = 8
    for i in range(stripes):
        c = CLOTH_RED if i % 2 == 0 else CLOTH_CREAM
        x0 = -W / 2 - 0.15 + (W + 0.3) * i / stripes
        x1 = -W / 2 - 0.15 + (W + 0.3) * (i + 1) / stripes
        s = Mesh()
        s.add_quad((x0, -D / 2 - 0.35, 2.05), (x1, -D / 2 - 0.35, 2.05),
                   (x1, 0.0, 2.42), (x0, 0.0, 2.42), c)
        s.add_quad((x0, 0.0, 2.42), (x1, 0.0, 2.42),
                   (x1, D / 2 + 0.35, 2.05), (x0, D / 2 + 0.35, 2.05), c)
        cloth.extend(s)
    # Crates and produce on the counter.
    r = _rng(12)
    for i in range(3):
        x = -0.8 + i * 0.8
        goods.extend(box(0.42, 0.36, 0.20, WOOD_LIGHT, origin="base")
                     .translate(x, 0, 1.0))
        for k in range(4):
            goods.extend(sphere(0.075, [SQUASH_RIPE, srgb(206, 60, 48), srgb(224, 126, 46)][i])
                         .scale(1, 1, 0.72)
                         .translate(x + r.uniform(-0.12, 0.12),
                                    r.uniform(-0.12, 0.12), 1.24))
    return [Part(wood, "wood", roughness=0.88),
            Part(cloth, "awning", roughness=0.94, double_sided=True),
            Part(goods, "goods", roughness=0.6)]


def make_fence():
    """One 2.4 m section of post-and-rail fence."""
    m = Mesh()
    m.extend(box(0.12, 0.12, 1.15, WOOD_DARK, origin="base").translate(-1.2, 0, 0))
    m.extend(box(0.12, 0.12, 1.15, WOOD_DARK, origin="base").translate(1.2, 0, 0))
    for z in (0.42, 0.82):
        m.extend(box(2.4, 0.07, 0.13, WOOD).translate(0, 0, z))
    m.extend(box(0.09, 0.06, 1.0, WOOD).rotate_y(14).translate(0, 0.02, 0.62))
    return [Part(m, "fence", roughness=0.9)]


def make_signpost():
    m = Mesh()
    m.extend(box(0.11, 0.11, 1.85, WOOD_DARK, origin="base"))
    board = box(0.86, 0.06, 0.40, WOOD_LIGHT).translate(0.30, 0.0, 1.55)
    m.extend(board)
    m.extend(box(0.78, 0.02, 0.07, WOOD_DARK).translate(0.30, -0.035, 1.62))
    m.extend(box(0.60, 0.02, 0.07, WOOD_DARK).translate(0.22, -0.035, 1.48))
    return [Part(m, "sign", roughness=0.88)]


def make_scarecrow():
    wood = Mesh()
    cloth = Mesh()
    straw = Mesh()
    wood.extend(box(0.09, 0.09, 1.9, WOOD_DARK, origin="base"))
    wood.extend(box(1.35, 0.07, 0.07, WOOD_DARK).translate(0, 0, 1.42))
    cloth.extend(box(0.52, 0.30, 0.72, CLOTH_BLUE).translate(0, 0, 1.20))
    for sx in (-0.55, 0.55):
        cloth.extend(box(0.42, 0.16, 0.16, CLOTH_RED).translate(sx, 0, 1.42))
    head = sphere(0.20, CLOTH_CREAM).scale(1.0, 0.92, 1.05).translate(0, 0, 1.76)
    cloth.extend(head)
    # Straw hat.
    cloth.extend(revolve([(0.001, 0.0), (0.17, 0.02), (0.19, 0.14), (0.36, 0.16),
                          (0.37, 0.13)], 16, srgb(210, 180, 104))
                 .translate(0, 0, 1.88))
    r = _rng(7)
    for i in range(26):
        a = r.uniform(0, 360)
        d = r.uniform(0.0, 0.28)
        straw.extend(box(0.012, 0.012, r.uniform(0.10, 0.22), srgb(206, 182, 110),
                         origin="base")
                     .rotate_y(r.uniform(50, 110)).rotate_z(a)
                     .translate(math.cos(math.radians(a)) * d * 0.4,
                                math.sin(math.radians(a)) * d * 0.4,
                                1.55 + r.uniform(-0.06, 0.10)))
    for sx in (-0.72, 0.72):
        for i in range(5):
            straw.extend(box(0.010, 0.010, r.uniform(0.10, 0.18), srgb(206, 182, 110),
                             origin="base")
                         .rotate_y(80 + r.uniform(-25, 25)).rotate_z(r.uniform(0, 360))
                         .translate(sx, 0, 1.42))
    return [Part(wood, "post", roughness=0.9),
            Part(cloth, "cloth", roughness=0.94),
            Part(straw, "straw", roughness=0.9, double_sided=True)]


def make_cooking_pot():
    """A cauldron on a stone hearth — the farm's kitchen."""
    stone = Mesh()
    metal = Mesh()
    fire = Mesh()
    r = _rng(77)
    # Ring of hearth stones.
    for i in range(11):
        a = math.radians(360 * i / 11 + r.uniform(-8, 8))
        sz = 0.15 + r.uniform(0, 0.07)
        stone.extend(box(sz, sz * 0.8, sz * 0.75, STONE_DARK, origin="base")
                     .rotate_z(math.degrees(a))
                     .translate(math.cos(a) * 0.46, math.sin(a) * 0.46, 0.0))
    stone.extend(revolve([(0.44, 0.0), (0.46, 0.06)], 14, STONE))
    # Cauldron.
    body = revolve([(0.001, 0.30), (0.20, 0.32), (0.27, 0.46), (0.26, 0.62),
                    (0.22, 0.68)], 16, IRON).smooth(55)
    metal.extend(body)
    metal.extend(revolve([(0.275, 0.60), (0.275, 0.665)], 16, srgb(96, 98, 104),
                         close_bottom=False, close_top=False))
    # Tripod legs and a hanging bar.
    for i in range(3):
        a = math.radians(120 * i + 30)
        metal.extend(tube([(math.cos(a) * 0.40, math.sin(a) * 0.40, 0.0),
                           (math.cos(a) * 0.16, math.sin(a) * 0.16, 0.30)],
                          [0.022, 0.018], IRON, 6))
    metal.extend(tube([(-0.27, 0, 0.64), (-0.30, 0, 0.78), (0.0, 0, 0.84),
                       (0.30, 0, 0.78), (0.27, 0, 0.64)],
                      [0.016] * 5, IRON, 6))
    # Embers under the pot, emissive so they glow at night.
    for i in range(7):
        a = r.uniform(0, 360)
        d = r.uniform(0.0, 0.22)
        fire.extend(box(0.09, 0.05, 0.035, srgb(226, 108, 40), origin="base")
                    .rotate_z(a)
                    .translate(math.cos(math.radians(a)) * d,
                               math.sin(math.radians(a)) * d, 0.03))
    return [Part(stone, "hearth", roughness=0.94),
            Part(metal, "cauldron", roughness=0.46, metallic=0.72),
            Part(fire, "embers", roughness=0.7, emissive=(1.0, 0.42, 0.12))]


def make_crate():
    m = Mesh()
    m.extend(box(0.60, 0.60, 0.48, WOOD_LIGHT, origin="base"))
    for z in (0.03, 0.42):
        for ax in (0, 90):
            m.extend(box(0.64, 0.05, 0.06, WOOD_DARK).rotate_z(ax).translate(0, 0, z))
    for sx in (-0.3, 0.3):
        for sy in (-0.3, 0.3):
            m.extend(box(0.07, 0.07, 0.48, WOOD_DARK, origin="base").translate(sx, sy, 0))
    return [Part(m, "crate", roughness=0.9)]


def make_barrel():
    body = revolve([(0.22, 0.0), (0.28, 0.16), (0.30, 0.38), (0.28, 0.60), (0.22, 0.76)],
                   16, WOOD).smooth(50)
    hoops = Mesh()
    for z in (0.10, 0.37, 0.66):
        hoops.extend(revolve([(0.288, z), (0.288, z + 0.055)], 16, IRON,
                             close_bottom=False, close_top=False))
    return [Part(body, "barrel", roughness=0.88),
            Part(hoops, "hoops", roughness=0.5, metallic=0.7)]


def make_bucket():
    body = revolve([(0.13, 0.0), (0.17, 0.26)], 14, WOOD_DARK)
    handle = tube([(-0.17, 0, 0.24), (-0.12, 0, 0.38), (0.0, 0, 0.42),
                   (0.12, 0, 0.38), (0.17, 0, 0.24)],
                  [0.012] * 5, IRON, 6)
    return [Part(body, "bucket", roughness=0.86),
            Part(handle, "handle", roughness=0.42, metallic=0.75)]


def make_lantern():
    frame = Mesh()
    glassm = Mesh()
    frame.extend(revolve([(0.09, 0.0), (0.10, 0.03), (0.055, 0.05)], 10, IRON))
    for i in range(4):
        a = math.radians(90 * i + 45)
        frame.extend(box(0.014, 0.014, 0.19, IRON, origin="base")
                     .translate(math.cos(a) * 0.062, math.sin(a) * 0.062, 0.05))
    frame.extend(revolve([(0.001, 0.30), (0.10, 0.25), (0.095, 0.235)], 10, IRON))
    frame.extend(tube([(0, 0, 0.30), (0, 0, 0.36), (0.0, 0.0, 0.40)],
                      [0.010, 0.010, 0.012], IRON, 6))
    glassm.extend(revolve([(0.055, 0.055), (0.075, 0.13), (0.055, 0.225)], 10,
                          LAMP_GLASS, close_bottom=False, close_top=False))
    return [Part(frame, "frame", roughness=0.42, metallic=0.7),
            Part(glassm, "glass", roughness=0.20,
                 emissive=(1.0, 0.72, 0.34), double_sided=True)]


def make_plot_bed():
    """A tilled bed with real furrows.

    Tilled ground used to be nothing but a dark disc painted into the
    terrain mask — at the mask's resolution (about 3.5 px/m) that is a
    blurry smudge, which the player read as "низкая полигональность у
    грядок". Soil is now geometry: a low raised slab with four ridged
    furrows, jittered so no two ridges sit perfectly straight.
    """
    r = _rng(17)
    soil = Mesh()
    soil.extend(box(1.18, 1.18, 0.05, srgb(78, 55, 37), origin="base"))
    for i, rx in enumerate((-0.42, -0.14, 0.14, 0.42)):
        tint = srgb(88 + r.randint(0, 14), 62 + r.randint(0, 8),
                    40 + r.randint(0, 8))
        ridge = (box(0.11, 1.06, 0.11, tint)
                 .rotate_y(45)
                 .rotate_z(r.uniform(-3.0, 3.0))
                 .translate(rx + r.uniform(-0.015, 0.015),
                            r.uniform(-0.02, 0.02), 0.05))
        soil.extend(ridge)
    return [Part(soil, "soil", roughness=0.97)]


def make_lamppost():
    """A post with an arm to hang a lantern from.

    The yard lanterns used to be placed 1.35 m up with nothing beneath:
    lamps floating in mid-air, which the player photographed on day one.
    """
    wood = Mesh()
    iron = Mesh()
    wood.extend(revolve([(0.085, 0.0), (0.075, 0.9), (0.058, 1.60)], 8, WOOD))
    # Arm reaching out along +Y, with a small brace back to the post.
    wood.extend(box(0.055, 0.42, 0.055, WOOD_DARK, origin="base")
                .translate(0, 0.11, 1.52))
    wood.extend(box(0.04, 0.30, 0.04, WOOD_DARK, origin="base")
                .rotate_x(-45).translate(0, 0.06, 1.30))
    # Hook at the arm's end; the lantern hangs from here.
    iron.extend(tube([(0.0, 0.28, 1.52), (0.0, 0.28, 1.455)],
                     [0.012, 0.011], IRON, 6))
    return [Part(wood, "wood", roughness=0.88),
            Part(iron, "iron", roughness=0.45, metallic=0.7)]


def make_watering_can():
    body = revolve([(0.001, 0.0), (0.11, 0.0), (0.12, 0.20), (0.10, 0.24)], 14, WATER_CAN)
    spout = tube([(0.09, 0, 0.06), (0.22, 0, 0.13), (0.30, 0, 0.22)],
                 [0.028, 0.022, 0.030], WATER_CAN, 8)
    handle = tube([(-0.10, 0, 0.20), (-0.13, 0, 0.30), (-0.04, 0, 0.33)],
                  [0.014] * 3, WATER_CAN, 6)
    rose = revolve([(0.030, 0.0), (0.055, 0.03)], 10, METAL).rotate_y(38).translate(0.31, 0, 0.23)
    m = Mesh().extend(body).extend(spout).extend(handle)
    return [Part(m, "can", roughness=0.38, metallic=0.35),
            Part(rose, "rose", roughness=0.35, metallic=0.6)]


# ----------------------------------------------------------------- nature


def _leaf_clump(radius: float, colour, seed: int, squash: float = 0.84) -> Mesh:
    """One lumpy mass of foliage.

    A single smooth sphere per branch reads as a lollipop; a canopy built from
    a dozen of these overlapping, each with its own irregular silhouette, reads
    as leaves.
    """
    m = sphere(radius, colour, 6, 4).scale(1.0, 1.0, squash)
    m.warp_radial((0.0, 0.0, 0.0), 0.42, seed, freq=2.2)
    return m


def _branch(m: Mesh, start, direction, length, radius, depth, rng, colour,
            tips: list, droop: float = 0.0):
    """Recursive limb. Collects its tips so the canopy can be grown on them."""
    end = (start[0] + direction[0] * length,
           start[1] + direction[1] * length,
           start[2] + direction[2] * length - droop * length)
    mid = (start[0] + direction[0] * length * 0.5 + rng.uniform(-0.06, 0.06),
           start[1] + direction[1] * length * 0.5 + rng.uniform(-0.06, 0.06),
           start[2] + direction[2] * length * 0.5 - droop * length * 0.25)
    m.extend(tube([start, mid, end], [radius, radius * 0.72, radius * 0.48],
                  colour, 6 if depth >= 2 else 5))
    if depth <= 0:
        tips.append(end)
        return
    for _ in range(2):
        d = (direction[0] + rng.uniform(-0.75, 0.75),
             direction[1] + rng.uniform(-0.7, 0.7),
             direction[2] + rng.uniform(-0.3, 0.28))
        n = math.sqrt(sum(c * c for c in d)) or 1.0
        d = (d[0] / n, d[1] / n, d[2] / n)
        _branch(m, end, d, length * rng.uniform(0.56, 0.72), radius * 0.60,
                depth - 1, rng, colour, tips, droop)


def _grow_canopy(foliage: Mesh, tips: list, rng, palette, seed: int,
                 size=(0.40, 0.72), per_tip=(2, 3)) -> None:
    """Cluster leaf masses around every branch tip, then bake in some shading."""
    if not tips:
        return
    index = 0
    for tip in tips:
        for _ in range(rng.randint(*per_tip)):
            index += 1
            r = rng.uniform(*size)
            colour = rng.choice(palette)
            clump = _leaf_clump(r, colour, seed * 977 + index * 37)
            clump.translate(tip[0] + rng.gauss(0.0, r * 0.55),
                            tip[1] + rng.gauss(0.0, r * 0.55),
                            tip[2] + rng.gauss(0.0, r * 0.45))
            foliage.extend(clump)
    zs = [p[2] for p in foliage.verts]
    foliage.shade_by_height(min(zs), max(zs), 0.52)


def make_tree(kind: str, seed: int):
    rng = _rng(seed)
    trunk = Mesh()
    foliage = Mesh()

    if kind == "pine":
        h = rng.uniform(5.5, 7.5)
        trunk.extend(revolve([(0.30, 0.0), (0.26, 0.35), (0.16, h * 0.55),
                              (0.09, h)], 10, srgb(94, 68, 48)).smooth(45))
        tiers = 8
        for i in range(tiers):
            t = i / tiers
            z = h * (0.18 + 0.74 * t)
            r = (1.85 - 1.45 * t) * rng.uniform(0.90, 1.08)
            colour = PINE if i % 2 else srgb(58, 104, 62)
            # Lobed cones give the tiers a ragged edge instead of a clean circle.
            tier = revolve([(r, 0.0), (r * 0.55, r * 0.62), (0.001, r * 1.45)],
                           13, colour, lobes=5, lobe_depth=0.16,
                           twist=rng.uniform(-12, 12))
            foliage.extend(tier.translate(0, 0, z))
        foliage.jitter_colors(0.07, seed)
        zs = [p[2] for p in foliage.verts]
        foliage.shade_by_height(min(zs), max(zs), 0.62)
        return [Part(trunk, "trunk", roughness=0.94),
                Part(foliage, "needles", roughness=0.9)]

    birch = kind == "birch"
    bark = BARK_BIRCH if birch else BARK
    palette = ([FOLIAGE_2, srgb(120, 164, 74), srgb(96, 140, 56)] if birch
               else [FOLIAGE, FOLIAGE_2, srgb(62, 104, 40)])
    h = rng.uniform(2.8, 3.8) if birch else rng.uniform(2.2, 3.1)

    # Root flare, then a slightly leaning trunk.
    trunk.extend(revolve([(0.40, 0.0), (0.30, 0.35), (0.24, h * 0.6),
                          (0.20, h)], 10, bark).smooth(50))
    if birch:
        for _ in range(11):
            z = rng.uniform(0.3, h * 0.95)
            a = rng.uniform(0, 360)
            trunk.extend(box(0.11, 0.02, 0.045, srgb(58, 54, 50))
                         .rotate_z(a)
                         .translate(math.cos(math.radians(a)) * 0.23,
                                    math.sin(math.radians(a)) * 0.23, z))

    tips: list = []
    droop = 0.22 if birch else 0.06
    for _ in range(rng.randint(3, 4)):
        d = (rng.uniform(-0.75, 0.75), rng.uniform(-0.75, 0.75),
             rng.uniform(0.55, 1.0))
        n = math.sqrt(sum(c * c for c in d))
        d = (d[0] / n, d[1] / n, d[2] / n)
        _branch(trunk, (0, 0, h * rng.uniform(0.72, 0.95)), d,
                rng.uniform(1.0, 1.5), 0.14, 2, rng, bark, tips, droop)

    # A couple of masses over the trunk itself, so the canopy reads as one
    # crown rather than separate blobs floating on the ends of the branches.
    core = [(0.0, 0.0, h + rng.uniform(0.35, 0.75))]
    _grow_canopy(foliage, core, rng, palette, seed + 7,
                 size=(0.55, 0.85), per_tip=(2, 3))
    _grow_canopy(foliage, tips, rng, palette, seed,
                 size=(0.40, 0.70) if birch else (0.46, 0.82))
    foliage.jitter_colors(0.09, seed)
    return [Part(trunk, "trunk", roughness=0.94),
            Part(foliage, "leaves", roughness=0.88)]


def make_bush(seed: int = 4):
    rng = _rng(seed)
    m = Mesh()
    for i in range(6):
        r = rng.uniform(0.28, 0.46)
        colour = rng.choice([FOLIAGE, FOLIAGE_2, srgb(62, 104, 40)])
        m.extend(_leaf_clump(r, colour, seed * 131 + i * 17)
                 .translate(rng.uniform(-0.32, 0.32), rng.uniform(-0.32, 0.32),
                            r * 0.72 + rng.uniform(0, 0.20)))
    zs = [p[2] for p in m.verts]
    m.shade_by_height(min(zs), max(zs), 0.58)
    m.jitter_colors(0.08, seed)
    return [Part(m, "bush", roughness=0.9)]


def make_rock(size: float, seed: int):
    rng = _rng(seed)
    profile = []
    steps = 7
    for i in range(steps + 1):
        a = i / steps * math.pi
        profile.append((math.sin(a) * rng.uniform(0.78, 1.15) * size,
                        -math.cos(a) * size * 0.62))
    m = revolve(profile, 11, ROCK, close_bottom=False, close_top=False,
                twist=rng.uniform(-30, 30))
    m.translate(0, 0, size * 0.5).jitter_colors(0.12, seed)
    return [Part(m, "rock", roughness=0.92)]


def make_reed():
    rng = _rng(15)
    m = Mesh()
    for i in range(11):
        a = rng.uniform(0, 360)
        d = rng.uniform(0, 0.16)
        x, y = math.cos(math.radians(a)) * d, math.sin(math.radians(a)) * d
        h = rng.uniform(0.7, 1.35)
        lean = rng.uniform(0.05, 0.20)
        m.extend(tube([(x, y, 0), (x + lean * 0.4, y + lean * 0.2, h * 0.55),
                       (x + lean, y + lean * 0.5, h)],
                      [0.010, 0.008, 0.005], srgb(112, 142, 74), 5))
        if rng.random() < 0.45:
            m.extend(capsule(0.022, 0.13, srgb(96, 66, 44), 8)
                     .translate(x + lean, y + lean * 0.5, h - 0.02))
    return [Part(m, "reed", roughness=0.88, double_sided=True)]


def make_flowers(seed: int = 2):
    rng = _rng(seed)
    m = Mesh()
    for _ in range(6):
        x, y = rng.uniform(-0.30, 0.30), rng.uniform(-0.30, 0.30)
        h = rng.uniform(0.16, 0.30)
        m.extend(tube([(x, y, 0), (x, y, h)], [0.006, 0.005], STEM, 5))
        col = rng.choice([FLOWER_Y, FLOWER_P, FLOWER_W])
        for k in range(5):
            a = math.radians(72 * k + rng.uniform(-10, 10))
            pet = box(0.055, 0.026, 0.010, col).rotate_z(math.degrees(a))
            pet.translate(x + math.cos(a) * 0.032, y + math.sin(a) * 0.032, h)
            m.extend(pet)
        m.extend(sphere(0.018, FLOWER_Y).translate(x, y, h + 0.005))
    return [Part(m, "flowers", roughness=0.85, double_sided=True)]


def make_lilypad():
    m = Mesh()
    rng = _rng(6)
    for _ in range(4):
        x, y = rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5)
        r = rng.uniform(0.16, 0.28)
        pad = revolve([(0.001, 0.0), (r * 0.6, 0.006), (r, 0.010), (r * 0.98, 0.0)],
                      14, srgb(84, 138, 66))
        m.extend(pad.rotate_z(rng.uniform(0, 360)).translate(x, y, 0))
    m.extend(sphere(0.05, FLOWER_P).scale(1, 1, 0.7).translate(0.1, -0.1, 0.03))
    return [Part(m, "lilypad", roughness=0.7, double_sided=True)]


# ---------------------------------------------------------------- creatures


def make_chicken():
    body = Mesh()
    beak = Mesh()
    comb = Mesh()
    legs = Mesh()
    body.extend(sphere(0.16, CHICKEN, 14, 10).scale(1.25, 0.95, 1.0).translate(0, 0, 0.22))
    body.extend(sphere(0.10, CHICKEN, 12, 8).translate(0.17, 0, 0.36))
    # Tail.
    for i in range(3):
        body.extend(box(0.03, 0.10, 0.16, CHICKEN).rotate_y(-32 - i * 12)
                    .translate(-0.20 - i * 0.015, (i - 1) * 0.035, 0.32))
    # Wings.
    for sy in (-0.13, 0.13):
        body.extend(sphere(0.09, srgb(224, 218, 204), 10, 6)
                    .scale(1.35, 0.35, 0.9).translate(0.0, sy, 0.24))
    beak.extend(cone(0.035, 0.09, BEAK, 8).rotate_y(90).translate(0.26, 0, 0.35))
    comb.extend(box(0.02, 0.055, 0.055, COMB).translate(0.17, 0, 0.45))
    comb.extend(box(0.03, 0.02, 0.05, COMB).translate(0.235, 0, 0.31))
    for sy in (-0.055, 0.055):
        legs.extend(cylinder(0.014, 0.11, BEAK, 6).translate(0.02, sy, 0.0))
        legs.extend(box(0.075, 0.05, 0.014, BEAK, origin="base").translate(0.025, sy, 0))
    eyes = Mesh()
    for sy in (-0.055, 0.055):
        eyes.extend(sphere(0.017, srgb(28, 24, 22)).translate(0.215, sy, 0.385))
    return [Part(body, "body", roughness=0.86),
            Part(beak, "beak", roughness=0.6),
            Part(comb, "comb", roughness=0.7),
            Part(legs, "legs", roughness=0.7),
            Part(eyes, "eyes", roughness=0.25)]


def make_cow():
    body = Mesh()
    spots = Mesh()
    horns = Mesh()
    legs = Mesh()
    body.extend(sphere(0.52, COW_W, 16, 11).scale(1.45, 0.92, 0.95).translate(0, 0, 1.02))
    body.extend(sphere(0.30, COW_W, 14, 9).scale(1.05, 0.88, 0.92).translate(0.86, 0, 1.16))
    body.extend(sphere(0.16, srgb(230, 186, 186), 12, 8).scale(0.8, 0.85, 0.6)
                .translate(1.12, 0, 1.05))
    # Ears and tail.
    for sy in (-0.28, 0.28):
        body.extend(sphere(0.09, COW_W, 8, 6).scale(1.1, 0.5, 0.7).translate(0.80, sy, 1.34))
    body.extend(tube([(-0.72, 0, 1.24), (-0.88, 0, 0.94), (-0.90, 0, 0.66)],
                     [0.035, 0.028, 0.020], COW_W, 6))
    body.extend(sphere(0.055, COW_B).translate(-0.90, 0, 0.62))
    r = _rng(11)
    for _ in range(7):
        a = r.uniform(0, math.tau)
        u = r.uniform(-1, 1)
        rad = 0.52
        p = (math.cos(a) * math.sqrt(1 - u * u) * rad * 1.45,
             math.sin(a) * math.sqrt(1 - u * u) * rad * 0.92,
             u * rad * 0.95 + 1.02)
        spots.extend(sphere(r.uniform(0.12, 0.21), COW_B, 10, 7)
                     .scale(1.0, 1.0, 0.75).translate(*p))
    for sx, sy in ((0.42, -0.30), (0.42, 0.30), (-0.44, -0.30), (-0.44, 0.30)):
        legs.extend(cylinder(0.085, 0.72, COW_W, 8).translate(sx, sy, 0))
        legs.extend(cylinder(0.095, 0.10, COW_B, 8).translate(sx, sy, 0))
    for sy in (-0.20, 0.20):
        horns.extend(cone(0.045, 0.18, srgb(226, 214, 188), 8).rotate_x(sy * 60)
                     .translate(0.86, sy, 1.40))
    eyes = Mesh()
    for sy in (-0.19, 0.19):
        eyes.extend(sphere(0.035, srgb(28, 24, 22)).translate(1.06, sy, 1.24))
    return [Part(body, "body", roughness=0.88),
            Part(spots, "spots", roughness=0.88),
            Part(legs, "legs", roughness=0.86),
            Part(horns, "horns", roughness=0.55),
            Part(eyes, "eyes", roughness=0.25)]


def make_cat():
    body = Mesh()
    body.extend(sphere(0.13, CAT, 12, 9).scale(1.5, 0.85, 0.85).translate(0, 0, 0.20))
    body.extend(sphere(0.095, CAT, 12, 8).translate(0.19, 0, 0.28))
    for sy in (-0.055, 0.055):
        body.extend(cone(0.045, 0.075, CAT, 6).translate(0.19, sy, 0.35))
    body.extend(tube([(-0.18, 0, 0.22), (-0.27, 0.03, 0.30), (-0.28, 0.07, 0.40)],
                     [0.028, 0.024, 0.018], CAT, 6))
    for sx, sy in ((0.10, -0.07), (0.10, 0.07), (-0.10, -0.07), (-0.10, 0.07)):
        body.extend(cylinder(0.028, 0.13, CAT, 6).translate(sx, sy, 0))
    eyes = Mesh()
    for sy in (-0.045, 0.045):
        eyes.extend(sphere(0.018, srgb(126, 196, 96)).translate(0.26, sy, 0.30))
    return [Part(body, "cat", roughness=0.85),
            Part(eyes, "eyes", roughness=0.2)]


def make_crow():
    """A crow: black, hunched, and after your ripe crops."""
    body = Mesh()
    beak = Mesh()
    eye = Mesh()
    black = srgb(38, 36, 42)
    sheen = srgb(58, 56, 72)
    body.extend(sphere(0.115, black, 12, 9).scale(0.85, 1.45, 0.90)
                .translate(0, 0, 0.145))
    body.extend(sphere(0.075, black, 10, 8).translate(0, 0.135, 0.235))
    # Tail and folded wings.
    tail = box(0.075, 0.20, 0.028, sheen, origin="center")
    tail.rotate_x(-14).translate(0, -0.20, 0.145)
    body.extend(tail)
    for sx in (-1, 1):
        wing = box(0.045, 0.20, 0.075, sheen, origin="center")
        wing.rotate_y(sx * 9).translate(sx * 0.088, -0.01, 0.150)
        body.extend(wing)
    for sx in (-1, 1):
        body.extend(tube([(sx * 0.042, 0.0, 0.055), (sx * 0.042, 0.01, 0.0)],
                         [0.012, 0.010], srgb(96, 84, 62), 5))
    beak.extend(cone(0.026, 0.085, srgb(188, 168, 72), 7)
                .rotate_x(90).translate(0, 0.185, 0.238))
    for sx in (-1, 1):
        eye.extend(sphere(0.013, srgb(226, 208, 96), 6, 5)
                   .translate(sx * 0.042, 0.168, 0.262))
    return [Part(body, "crow", roughness=0.62),
            Part(beak, "beak", roughness=0.45),
            Part(eye, "eye", roughness=0.22)]


def make_weeds(seed: int = 55):
    """A tuft of weeds that sprouts on a neglected plot."""
    m = Mesh()
    r = _rng(seed)
    weedy = srgb(96, 122, 58)
    weedy2 = srgb(126, 140, 72)
    for _ in range(9):
        a = r.uniform(0, 360)
        d = r.uniform(0.0, 0.30)
        x, y = math.cos(math.radians(a)) * d, math.sin(math.radians(a)) * d
        h = r.uniform(0.14, 0.30)
        lean = r.uniform(0.03, 0.10)
        m.extend(tube([(x, y, 0), (x + lean * 0.4, y, h * 0.6),
                       (x + lean, y + lean * 0.3, h)],
                      [0.010, 0.008, 0.005], weedy if r.random() < 0.6 else weedy2, 5))
        for _ in range(2):
            lf = leaf(r.uniform(0.06, 0.11), r.uniform(0.03, 0.055),
                      weedy2, curl=0.25, segments=4)
            lf.rotate_y(-r.uniform(25, 60)).rotate_z(r.uniform(0, 360))
            lf.translate(x + lean * 0.5, y, h * r.uniform(0.35, 0.8))
            m.extend(lf)
    return [Part(m, "weeds", roughness=0.88, double_sided=True)]


def make_butterfly():
    wings = Mesh()
    body = Mesh()
    body.extend(capsule(0.012, 0.07, srgb(52, 44, 40), 6).rotate_y(90).translate(-0.035, 0, 0))
    for sy in (-1, 1):
        w = Mesh()
        w.add_quad((0.0, 0.0, 0.0), (0.05, sy * 0.075, 0.01),
                   (0.02, sy * 0.11, 0.0), (-0.03, sy * 0.05, 0.0), srgb(238, 156, 62))
        w.add_quad((-0.01, 0.0, 0.0), (-0.03, sy * 0.05, 0.0),
                   (-0.055, sy * 0.07, 0.0), (-0.06, sy * 0.02, 0.0), srgb(226, 116, 52))
        wings.extend(w)
    return [Part(body, "body", roughness=0.8),
            Part(wings, "wings", roughness=0.7, double_sided=True)]


def make_fish():
    body = revolve([(0.001, -0.14), (0.035, -0.06), (0.045, 0.03), (0.028, 0.11),
                    (0.001, 0.15)], 10, FISH).rotate_y(90).smooth(60)
    fins = Mesh()
    tail = Mesh()
    tail.add_quad((-0.15, 0, 0), (-0.24, 0, 0.07), (-0.26, 0, -0.01), (-0.22, 0, -0.06),
                  srgb(120, 146, 168))
    fins.extend(tail)
    fins.add_quad((0.0, 0, 0.04), (-0.06, 0, 0.10), (-0.09, 0, 0.03), (-0.02, 0, 0.03),
                  srgb(120, 146, 168))
    eyes = Mesh()
    for sy in (-0.028, 0.028):
        eyes.extend(sphere(0.012, srgb(28, 26, 26)).translate(0.10, sy, 0.02))
    return [Part(body, "fish", roughness=0.30),
            Part(fins, "fins", roughness=0.4, double_sided=True),
            Part(eyes, "eyes", roughness=0.2)]


EYE_WHITE = srgb(244, 244, 240)
EYE_DARK = srgb(38, 32, 28)
MOUTH = srgb(150, 80, 72)

# The rig, in metres. Parts are modelled around their own pivot so the runtime
# can just rotate them: the hip carries the torso, the shoulders carry arms, the
# hips carry legs.
HIP_Z = 0.86
SHOULDER_Z = 0.42        # above the hip
SHOULDER_Y = 0.235
HEAD_Z = 0.48            # above the hip
LEG_Y = 0.115
LEG_LEN = 0.46
ARM_LEN = 0.50


def make_villager_body(shirt, trousers):
    """Torso and pelvis, pivoting at the hip. Forward is +Y."""
    cloth = Mesh()
    # Torso, tapering to the shoulders.
    cloth.extend(revolve([(0.185, -0.02), (0.215, 0.16), (0.205, 0.34),
                          (0.175, 0.46)], 14, shirt).smooth(50))
    # Pelvis.
    cloth.extend(revolve([(0.185, -0.20), (0.205, -0.10), (0.190, -0.01)],
                         12, trousers).smooth(50))
    # A collar so the neck join is not a hard edge.
    cloth.extend(revolve([(0.115, 0.44), (0.098, 0.49)], 12, shirt))
    return [Part(cloth, "clothes", roughness=0.92)]


def make_villager_head(hair_col, seed: int = 1):
    """Head pivoting at the neck, face on +Y."""
    rng = _rng(seed)
    skin = Mesh()
    hair = Mesh()
    eyes = Mesh()
    dark = Mesh()

    skin.extend(cylinder(0.058, 0.07, SKIN, 10).translate(0, 0, -0.01))
    head = sphere(0.148, SKIN, 16, 12).scale(0.94, 0.98, 1.06).translate(0, 0, 0.20)
    skin.extend(head)
    # Ears.
    for sx in (-1, 1):
        skin.extend(sphere(0.036, SKIN, 8, 6).scale(0.5, 0.9, 1.1)
                    .translate(sx * 0.138, 0.0, 0.20))
    # Nose.
    skin.extend(sphere(0.030, SKIN, 8, 6).scale(0.8, 1.25, 0.8)
                .translate(0.0, 0.140, 0.192))

    # Eyes: white, then a dark iris set slightly proud of it.
    for sx in (-0.058, 0.058):
        eyes.extend(sphere(0.030, EYE_WHITE, 10, 8).scale(1.0, 0.55, 1.0)
                    .translate(sx, 0.118, 0.235))
        dark.extend(sphere(0.0155, EYE_DARK, 8, 6).scale(1.0, 0.6, 1.0)
                    .translate(sx, 0.138, 0.233))
    # Brows.
    for sx in (-0.058, 0.058):
        dark.extend(box(0.055, 0.018, 0.014, hair_col, origin="center")
                    .rotate_y(rng.uniform(-6, 6))
                    .translate(sx, 0.128, 0.281))
    # Mouth.
    dark.extend(box(0.058, 0.016, 0.014, MOUTH, origin="center")
                .translate(0.0, 0.132, 0.148))

    # Hair: a cap plus a fringe, sitting slightly back off the face.
    hair.extend(sphere(0.156, hair_col, 14, 10).scale(0.96, 1.0, 0.92)
                .translate(0, -0.012, 0.225))
    hair.extend(sphere(0.10, hair_col, 10, 8).scale(1.25, 0.7, 0.55)
                .translate(0, -0.085, 0.185))
    return [Part(skin, "skin", roughness=0.72),
            Part(hair, "hair", roughness=0.86),
            Part(eyes, "eyes", roughness=0.22),
            Part(dark, "features", roughness=0.35)]


def make_villager_arm(shirt):
    """Arm pivoting at the shoulder, hanging down -Z."""
    cloth = Mesh()
    skin = Mesh()
    cloth.extend(tube([(0, 0, 0.03), (0, 0.01, -0.20), (0, 0.02, -0.38)],
                      [0.068, 0.058, 0.050], shirt, 8))
    skin.extend(sphere(0.052, SKIN, 10, 8).translate(0, 0.025, -0.44))
    return [Part(cloth, "clothes", roughness=0.92),
            Part(skin, "skin", roughness=0.72)]


def make_villager_leg(trousers):
    """Leg pivoting at the hip, hanging down -Z, boot at the bottom."""
    cloth = Mesh()
    boots = Mesh()
    cloth.extend(tube([(0, 0, 0.02), (0, 0, -0.22), (0, 0, -0.40)],
                      [0.082, 0.070, 0.062], trousers, 8))
    boots.extend(box(0.13, 0.21, 0.10, srgb(72, 54, 42), origin="base")
                 .translate(0, 0.025, -LEG_LEN))
    return [Part(cloth, "clothes", roughness=0.92),
            Part(boots, "boots", roughness=0.80)]


# ------------------------------------------------------------------ driver

MODELS = {
    "patisson_0": lambda: make_patisson(0),
    "patisson_1": lambda: make_patisson(1),
    "patisson_2": lambda: make_patisson(2),
    "patisson_3": lambda: make_patisson(3),
    "carrot": make_carrot,
    "tomato": make_tomato_bush,
    "wheat": make_wheat,
    "pumpkin": make_pumpkin,
    "house": make_house,
    "barn": make_barn,
    "well": make_well,
    "market_stall": make_market_stall,
    "fence": make_fence,
    "signpost": make_signpost,
    "scarecrow": make_scarecrow,
    "cooking_pot": make_cooking_pot,
    "lamppost": make_lamppost,
    "plot_bed": make_plot_bed,
    "crate": make_crate,
    "barrel": make_barrel,
    "bucket": make_bucket,
    "lantern": make_lantern,
    "watering_can": make_watering_can,
    "tree_oak": lambda: make_tree("oak", 101),
    "tree_oak2": lambda: make_tree("oak", 207),
    "tree_birch": lambda: make_tree("birch", 313),
    "tree_pine": lambda: make_tree("pine", 419),
    "bush": lambda: make_bush(523),
    "rock_small": lambda: make_rock(0.35, 631),
    "rock_large": lambda: make_rock(0.95, 733),
    "reed": make_reed,
    "flowers": lambda: make_flowers(829),
    "lilypad": make_lilypad,
    "chicken": make_chicken,
    "cow": make_cow,
    "cat": make_cat,
    "butterfly": make_butterfly,
    "crow": make_crow,
    "weeds": make_weeds,
    "fish": make_fish,
}

# Villagers are assembled at runtime from these parts so they can be posed.
VILLAGERS = {
    "bogdan": (CLOTH_BLUE, srgb(78, 68, 60), HAIR, 1),
    "marina": (CLOTH_RED, srgb(64, 74, 96), srgb(158, 108, 52), 2),
    "pyotr": (srgb(104, 132, 88), srgb(84, 72, 58), srgb(196, 190, 178), 3),
}
for _key, (_shirt, _trousers, _hair, _seed) in VILLAGERS.items():
    MODELS[f"villager_{_key}_body"] = (
        lambda sh=_shirt, tr=_trousers: make_villager_body(sh, tr))
    MODELS[f"villager_{_key}_head"] = (
        lambda hc=_hair, sd=_seed: make_villager_head(hc, sd))
    MODELS[f"villager_{_key}_arm"] = (lambda sh=_shirt: make_villager_arm(sh))
    MODELS[f"villager_{_key}_leg"] = (lambda tr=_trousers: make_villager_leg(tr))


def build_all(out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    total_tris = 0
    total_bytes = 0
    for name, fn in sorted(MODELS.items()):
        parts = fn()
        tris = sum(p.mesh.tri_count for p in parts)
        path = write_glb(out_dir / f"{name}.glb", parts, name)
        size = path.stat().st_size
        total_tris += tris
        total_bytes += size
        print(f"{name:20s} {tris:6d} tris  {size/1024:7.1f} KB")
    print(f"{'TOTAL':20s} {total_tris:6d} tris  {total_bytes/1024/1024:7.2f} MB")


if __name__ == "__main__":
    build_all()

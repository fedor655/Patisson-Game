"""Villagers: a daily routine, a walk cycle of sorts, and things to say."""

from __future__ import annotations

import math
import random

from panda3d.core import Vec3

from ..world.props import place

# Each entry: (hour, (x, y), what they're doing)
SCHEDULES = {
    "bogdan": [
        (6.0, (2.5, 3.0), "работает на грядках"),
        (11.0, (7.5, 7.0), "набирает воду"),
        (14.0, (-13.9, -3.1), "стоит за прилавком"),
        (19.0, (16.0, -13.0), "идёт домой"),
        (22.0, (16.0, -13.0), "спит"),
    ],
    "marina": [
        (7.0, (-14.1, -2.6), "открывает лавку"),
        (13.0, (-30.0, 24.0), "рыбачит у пруда"),
        (17.0, (-14.1, -2.6), "торгует"),
        (21.0, (-19.0, -16.0), "проверяет амбар"),
    ],
    "pyotr": [
        (8.0, (-19.0, -16.0), "кормит кур"),
        (12.0, (-26.0, -4.0), "пасёт коров"),
        (16.0, (-4.5, 12.0), "поправляет пугало"),
        (20.0, (2.0, -8.5), "курит у столба"),
    ],
}

DIALOGUE = {
    "bogdan": [
        "Вот и дождались! Ферма снова живая.",
        "Патиссон любит воду. Не забывай поливать.",
        "Колодец у дома — набирай сколько нужно.",
        "Осенью тыква идёт лучше всего. Проверено.",
        "В игре могут быть баги. Веселись!",
    ],
    "marina": [
        "Свежая рыба! Ну, почти свежая.",
        "Продавай урожай у прилавка — я хорошо плачу.",
        "Золотая лейка дорогая, но воду носить перестанешь.",
        "Ночью на ферме красиво. И тихо.",
    ],
    "pyotr": [
        "Куры опять разбежались. Как всегда.",
        "Дождь будет — грядки польются сами.",
        "Земля тут добрая, если за ней ходить.",
        "Зимой ничего не растёт. Отдыхай.",
    ],
}

NAMES = {"bogdan": "Богдан", "marina": "Марина", "pyotr": "Пётр"}


# Rig dimensions, mirrored from tools/make_assets.py.
HIP_Z = 0.86
SHOULDER_Z = 0.42
SHOULDER_X = 0.235
HEAD_Z = 0.48
LEG_X = 0.115


class NPC:
    """A villager with a small procedural rig: hips, head, two arms, two legs."""

    def __init__(self, key: str, node, world, seed: int = 0):
        self.key = key
        self.name = NAMES[key]
        self.node = node
        self.world = world
        self.schedule = SCHEDULES[key]
        self.rng = random.Random(seed)
        self.line_index = self.rng.randrange(len(DIALOGUE[key]))
        self.activity = self.schedule[0][2]
        self.speed = 1.9
        self.target = Vec3(*self.schedule[0][1], 0)
        self.phase = self.rng.uniform(0, 6.28)
        self.swing = 0.0             # 0 idle .. 1 full stride
        self._idle = self.rng.uniform(0, 10.0)
        self._glance = self.rng.uniform(3.0, 9.0)
        self._glance_yaw = 0.0
        self.parts = {}

    # ------------------------------------------------------------------ rig

    def build(self, place_fn, parent):
        """Assemble the body. Each part is modelled around its own joint, so
        posing is just a rotation on the node that carries it."""
        key = self.key
        hip = parent.attachNewNode("hip")
        hip.setZ(HIP_Z)
        place_fn(hip, "villager_" + key + "_body", (0, 0, 0))

        head = hip.attachNewNode("head")
        head.setZ(HEAD_Z)
        place_fn(head, "villager_" + key + "_head", (0, 0, 0))

        parts = {"hip": hip, "head": head}
        for side, sx in (("l", -1.0), ("r", 1.0)):
            sh = hip.attachNewNode("arm_" + side)
            sh.setPos(sx * SHOULDER_X, 0, SHOULDER_Z)
            place_fn(sh, "villager_" + key + "_arm", (0, 0, 0))
            parts["arm_" + side] = sh

            lg = hip.attachNewNode("leg_" + side)
            lg.setPos(sx * LEG_X, 0, 0)
            place_fn(lg, "villager_" + key + "_leg", (0, 0, 0))
            parts["leg_" + side] = lg
        self.parts = parts

    # -------------------------------------------------------------- schedule

    def destination(self, hour: float):
        best = self.schedule[-1]
        for entry in self.schedule:
            if hour >= entry[0]:
                best = entry
        return best

    def talk(self) -> str:
        lines = DIALOGUE[self.key]
        line = lines[self.line_index % len(lines)]
        self.line_index += 1
        return line

    # ---------------------------------------------------------------- update

    def update(self, dt: float, hour: float, time: float, look_at=None):
        _h, (tx, ty), activity = self.destination(hour)
        self.activity = activity
        p = self.node.getPos()
        dx, dy = tx - p.x, ty - p.y
        dist = math.hypot(dx, dy)
        moving = dist > 0.4

        step = 0.0
        if moving:
            step = min(self.speed * dt, dist)
            p.x += dx / dist * step
            p.y += dy / dist * step
            want = math.degrees(math.atan2(dy, dx)) - 90.0
            delta = (want - self.node.getH() + 180) % 360 - 180
            self.node.setH(self.node.getH() + delta * min(dt * 3.5, 1.0))
        self.node.setPos(p.x, p.y, self.world.height_at(p.x, p.y))

        # Drive the stride from distance covered rather than wall time, so the
        # feet keep pace with the body instead of skating.
        self.phase += step * 3.1
        self.swing += ((1.0 if moving else 0.0) - self.swing) * min(dt * 6.0, 1.0)
        self._animate(dt, look_at)

    # Activities where the villager should be bent over their work. The
    # schedule labels are the display strings, so match on their stems.
    STOOPING = ("грядк", "кормит", "поправляет", "воду", "амбар")

    def _stooping(self) -> bool:
        return self.swing < 0.2 and any(w in self.activity for w in self.STOOPING)

    def _animate(self, dt: float, look_at):
        parts = self.parts
        if not parts:
            return
        s = self.swing
        sin_p = math.sin(self.phase)
        cos_2p = math.cos(self.phase * 2.0)

        leg = 34.0 * s
        arm = 26.0 * s
        parts["leg_l"].setP(sin_p * leg)
        parts["leg_r"].setP(-sin_p * leg)
        # Arms counter-swing, with a small rest angle so they never clip in.
        parts["arm_l"].setHpr(0, -sin_p * arm, -6.0 - 4.0 * s)
        parts["arm_r"].setHpr(0, sin_p * arm, 6.0 + 4.0 * s)

        # Hips lift on each step and roll into it; standing still gets a breath.
        self._idle += dt
        breathe = math.sin(self._idle * 1.5) * 0.006 * (1.0 - s)
        parts["hip"].setZ(HIP_Z + abs(sin_p) * 0.030 * s + breathe)
        parts["hip"].setR(-cos_2p * 2.6 * s)
        parts["hip"].setP(-3.5 * s + (9.0 if self._stooping() else 0.0))

        # The head tracks the player when they are close, and drifts otherwise.
        yaw, pitch = 0.0, 0.0
        if look_at is not None:
            here = self.node.getPos()
            dx, dy = look_at.x - here.x, look_at.y - here.y
            if dx * dx + dy * dy < 42.0:
                world_yaw = math.degrees(math.atan2(dy, dx)) - 90.0
                yaw = (world_yaw - self.node.getH() + 180) % 360 - 180
                yaw = max(-62.0, min(62.0, yaw))
                dz = look_at.z - (here.z + HIP_Z + HEAD_Z + 0.2)
                pitch = max(-22.0, min(22.0, math.degrees(
                    math.atan2(dz, max(math.hypot(dx, dy), 0.3)))))
            else:
                look_at = None
        if look_at is None:
            self._glance -= dt
            if self._glance <= 0.0:
                self._glance = self.rng.uniform(4.0, 11.0)
                self._glance_yaw = self.rng.uniform(-38.0, 38.0)
            yaw = self._glance_yaw
        head = parts["head"]
        k = min(dt * 4.5, 1.0)
        head.setHpr(head.getH() + (yaw - head.getH()) * k,
                    head.getP() + (pitch - head.getP()) * k,
                    sin_p * 1.8 * s)


class Villagers:
    def __init__(self, base, world, props):
        self.world = world
        self.npcs: list[NPC] = []
        root = world.root.attachNewNode("npcs")
        props.pipeline.apply_scene_shader(root, micro_detail=0.05)
        for i, key in enumerate(("bogdan", "marina", "pyotr")):
            x, y = SCHEDULES[key][0][1]
            node = root.attachNewNode(f"villager_{key}")
            node.setPos(x, y, world.height_at(x, y))
            npc = NPC(key, node, world, seed=i * 31)
            npc.build(place, node)
            self.npcs.append(npc)

    def update(self, dt: float, hour: float, time: float, look_at=None):
        for npc in self.npcs:
            npc.update(dt, hour, time, look_at)

    def nearest(self, pos: Vec3, radius: float = 3.2) -> NPC | None:
        best, best_d = None, radius * radius
        for npc in self.npcs:
            p = npc.node.getPos()
            d = (p.x - pos.x) ** 2 + (p.y - pos.y) ** 2
            if d < best_d:
                best, best_d = npc, d
        return best

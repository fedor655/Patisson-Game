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
        (14.0, (-13.0, -2.0), "стоит за прилавком"),
        (19.0, (16.0, -13.0), "идёт домой"),
        (22.0, (16.0, -13.0), "спит"),
    ],
    "marina": [
        (7.0, (-13.0, -2.0), "открывает лавку"),
        (13.0, (-30.0, 24.0), "рыбачит у пруда"),
        (17.0, (-13.0, -2.0), "торгует"),
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


class NPC:
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
        self._bob = self.rng.uniform(0, 6.0)

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

    def update(self, dt: float, hour: float, time: float):
        _h, (tx, ty), activity = self.destination(hour)
        self.activity = activity
        p = self.node.getPos()
        dx, dy = tx - p.x, ty - p.y
        dist = math.hypot(dx, dy)
        moving = dist > 0.4
        if moving:
            step = min(self.speed * dt, dist)
            p.x += dx / dist * step
            p.y += dy / dist * step
            want = math.degrees(math.atan2(dy, dx)) - 90.0
            delta = (want - self.node.getH() + 180) % 360 - 180
            self.node.setH(self.node.getH() + delta * min(dt * 3.5, 1.0))
        z = self.world.height_at(p.x, p.y)
        if moving:
            # A gentle two-step bounce reads as walking without a skeleton.
            z += abs(math.sin((time + self._bob) * 6.5)) * 0.055
            self.node.setR(math.sin((time + self._bob) * 6.5) * 2.2)
        else:
            self.node.setR(0)
        self.node.setPos(p.x, p.y, z)


class Villagers:
    def __init__(self, base, world, props):
        self.world = world
        self.npcs: list[NPC] = []
        root = world.root.attachNewNode("npcs")
        props.pipeline.apply_scene_shader(root, micro_detail=0.05)
        for i, key in enumerate(("bogdan", "marina", "pyotr")):
            x, y = SCHEDULES[key][0][1]
            node = place(root, f"villager_{key}", (x, y, world.height_at(x, y)), 0)
            self.npcs.append(NPC(key, node, world, seed=i * 31))

    def update(self, dt: float, hour: float, time: float):
        for npc in self.npcs:
            npc.update(dt, hour, time)

    def nearest(self, pos: Vec3, radius: float = 3.2) -> NPC | None:
        best, best_d = None, radius * radius
        for npc in self.npcs:
            p = npc.node.getPos()
            d = (p.x - pos.x) ** 2 + (p.y - pos.y) ** 2
            if d < best_d:
                best, best_d = npc, d
        return best

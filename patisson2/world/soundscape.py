"""Which animal is heard, from where, and how loud the place itself is.

Until now the world sounded the same everywhere: one day bed, one night bed,
plus a cluck or a moo from whichever farm animal happened to be near. Standing
at the pond at dusk sounded exactly like standing in the woods at dusk.

This module answers two questions each frame or so:

  * *beds* — how loud the pond and the trees should be, from where the player
    is standing. These crossfade; they are places, not events.
  * *pick* — which single creature pipes up next, out of which actual tree or
    stretch of water, given the hour, the season and the weather.

It holds no Panda objects and no audio objects, so it can be tested headlessly.
"""

from __future__ import annotations

import math
import random

# How far each voice carries, in metres.
FALLOFF = {
    "bird1": 34.0, "bird2": 34.0, "bird3": 34.0,
    "frog": 30.0,
    "owl": 60.0,
    "caw": 40.0,
    "cluck": 20.0,
    "moo": 34.0,
}

# Beyond this the pond is inaudible; at the shore it is at full strength.
WATER_NEAR = 6.0
WATER_FAR = 34.0

# Leaf rustle rises with how many trees stand within this radius.
LEAF_RADIUS = 22.0
LEAF_FULL = 7          # trees within LEAF_RADIUS for the bed to reach full


class Soundscape:
    """Positional wildlife, built once from the world and then queried."""

    def __init__(self, trees, pond_centre, pond_radius, seed: int = 5150):
        self.trees = list(trees)
        self.pond_centre = (float(pond_centre[0]), float(pond_centre[1]))
        self.pond_radius = float(pond_radius)
        self.rng = random.Random(seed)

    # ------------------------------------------------------------- geometry

    def pond_distance(self, x: float, y: float) -> float:
        """Distance to the water's edge; 0 while standing over the pond."""
        d = math.hypot(x - self.pond_centre[0], y - self.pond_centre[1])
        return max(0.0, d - self.pond_radius)

    def trees_near(self, x: float, y: float, radius: float = LEAF_RADIUS) -> list:
        r2 = radius * radius
        return [t for t in self.trees
                if (t[0] - x) ** 2 + (t[1] - y) ** 2 < r2]

    # ---------------------------------------------------------------- beds

    def beds(self, x: float, y: float, indoors: bool = False) -> dict:
        """Target volumes for the place-based ambience layers."""
        if indoors:
            return {"amb_water": 0.0, "amb_leaves": 0.0}
        d = self.pond_distance(x, y)
        if d >= WATER_FAR:
            water = 0.0
        elif d <= WATER_NEAR:
            water = 1.0
        else:
            water = 1.0 - (d - WATER_NEAR) / (WATER_FAR - WATER_NEAR)
        leaves = min(1.0, len(self.trees_near(x, y)) / float(LEAF_FULL))
        return {"amb_water": water * 0.85, "amb_leaves": leaves * 0.7}

    # -------------------------------------------------------------- voices

    def pick(self, x: float, y: float, hour: float, season: int,
             weather: str = "clear"):
        """Choose the next wildlife one-shot, or None if nothing fits.

        Returns ``(sound, (x, y, z), falloff, volume)``.
        """
        night = hour < 5.0 or hour >= 21.0
        dusk = 18.5 <= hour < 21.0 or 4.5 <= hour < 6.5
        winter = season == 3

        # Silence competes for the slot like anything else. Without it the
        # weights below would be meaningless whenever only one voice fits, and
        # a winter noon would sound exactly as busy as a summer one.
        options = [(3.0, "silence", None)]

        # Birds: daytime, from a tree in earshot, and not in the rain.
        if not night and weather != "rain":
            near_trees = self.trees_near(x, y, FALLOFF["bird1"])
            if near_trees:
                weight = 5.0 if not winter else 1.0
                if dusk:
                    weight *= 0.5
                options.append((weight, "bird", near_trees))

        # Owls: night, and they want to be in the woods too.
        if night:
            far_trees = self.trees_near(x, y, FALLOFF["owl"])
            if far_trees:
                options.append((2.0 if not winter else 0.7, "owl", far_trees))

        # Frogs: near the water, from dusk into the night, and not in winter
        # when the pond is frozen over as far as the player is concerned.
        if not winter and (night or dusk) and self.pond_distance(x, y) < FALLOFF["frog"]:
            options.append((4.0, "frog", None))

        total = sum(w for w, _k, _d in options)
        roll = self.rng.uniform(0.0, total)
        for weight, kind, data in options:
            roll -= weight
            if roll > 0.0:
                continue
            if kind == "silence":
                return None
            if kind == "bird":
                tree = self.rng.choice(data)
                name = self.rng.choice(("bird1", "bird2", "bird3"))
                return name, tree, FALLOFF[name], self.rng.uniform(0.5, 0.85)
            if kind == "owl":
                tree = self.rng.choice(data)
                return "owl", tree, FALLOFF["owl"], self.rng.uniform(0.45, 0.7)
            # Frog: somewhere along the shore, on the side the player is on.
            angle = math.atan2(y - self.pond_centre[1], x - self.pond_centre[0])
            angle += self.rng.uniform(-1.1, 1.1)
            r = self.pond_radius * self.rng.uniform(0.85, 1.05)
            pos = (self.pond_centre[0] + math.cos(angle) * r,
                   self.pond_centre[1] + math.sin(angle) * r,
                   0.4)
            return "frog", pos, FALLOFF["frog"], self.rng.uniform(0.5, 0.9)
        return None

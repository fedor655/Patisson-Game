"""Solid obstacles.

Until now the player walked through walls, trees and everything else — the only
things that stopped them were steep ground and deep water. This keeps a flat
list of blockers (upright boxes and circles) in a uniform grid and pushes the
player out of anything they end up inside.

Buildings register their walls as several boxes with a gap left for the door,
so a doorway is simply the absence of a blocker.
"""

from __future__ import annotations

import math

CELL = 6.0          # grid cell size, metres


class Box:
    """An upright box, rotated about Z. Heading is degrees, Panda-style."""

    __slots__ = ("x", "y", "hw", "hd", "cos", "sin", "top")

    def __init__(self, x: float, y: float, hw: float, hd: float,
                 heading: float = 0.0, top: float = 9.0):
        self.x = x
        self.y = y
        self.hw = hw
        self.hd = hd
        a = math.radians(heading)
        self.cos = math.cos(a)
        self.sin = math.sin(a)
        self.top = top

    def reach(self) -> float:
        return math.hypot(self.hw, self.hd)

    def push_out(self, px: float, py: float, r: float):
        """Return a corrected (x, y) if the circle overlaps, else None."""
        dx = px - self.x
        dy = py - self.y
        # Into the box's own frame.
        lx = dx * self.cos + dy * self.sin
        ly = -dx * self.sin + dy * self.cos

        cx = max(-self.hw, min(self.hw, lx))
        cy = max(-self.hd, min(self.hd, ly))
        ox = lx - cx
        oy = ly - cy
        dist2 = ox * ox + oy * oy

        if dist2 > r * r:
            return None

        if dist2 > 1e-9:
            dist = math.sqrt(dist2)
            nx, ny = ox / dist, oy / dist
            push = r - dist
        else:
            # Centre is inside: escape through the nearest face.
            left = self.hw + lx
            right = self.hw - lx
            back = self.hd + ly
            front = self.hd - ly
            m = min(left, right, back, front)
            if m == right:
                nx, ny, push = 1.0, 0.0, right + r
            elif m == left:
                nx, ny, push = -1.0, 0.0, left + r
            elif m == front:
                nx, ny, push = 0.0, 1.0, front + r
            else:
                nx, ny, push = 0.0, -1.0, back + r

        lx += nx * push
        ly += ny * push
        return (self.x + lx * self.cos - ly * self.sin,
                self.y + lx * self.sin + ly * self.cos)


class Blockers:
    def __init__(self):
        self.grid: dict[tuple[int, int], list[Box]] = {}
        self.count = 0

    def add(self, box: Box) -> None:
        self.count += 1
        reach = box.reach()
        x0 = int(math.floor((box.x - reach) / CELL))
        x1 = int(math.floor((box.x + reach) / CELL))
        y0 = int(math.floor((box.y - reach) / CELL))
        y1 = int(math.floor((box.y + reach) / CELL))
        for i in range(x0, x1 + 1):
            for j in range(y0, y1 + 1):
                self.grid.setdefault((i, j), []).append(box)

    def add_box(self, x, y, hw, hd, heading=0.0, top=9.0) -> None:
        self.add(Box(x, y, hw, hd, heading, top))

    def add_post(self, x, y, radius, top=9.0) -> None:
        """A round obstacle, approximated by its bounding square."""
        self.add(Box(x, y, radius, radius, 0.0, top))

    def add_walls(self, cx, cy, heading, width, depth, thickness=0.28,
                  door_side="front", door_width=1.5, door_offset=0.0,
                  top=9.0) -> None:
        """Four walls of a building, with a gap left in one of them.

        Coordinates are the building's own: +Y is the far side, -Y the near
        ("front") side, before the heading rotation is applied.
        """
        hw, hd = width / 2.0, depth / 2.0
        t = thickness / 2.0
        a = math.radians(heading)
        ca, sa = math.cos(a), math.sin(a)

        def place(lx, ly, lhw, lhd):
            self.add_box(cx + lx * ca - ly * sa, cy + lx * sa + ly * ca,
                         lhw, lhd, heading, top)

        sides = {
            "front": (0.0, -hd, hw, t, True),
            "back": (0.0, hd, hw, t, True),
            "left": (-hw, 0.0, t, hd, False),
            "right": (hw, 0.0, t, hd, False),
        }
        for name, (lx, ly, lhw, lhd, along_x) in sides.items():
            if name != door_side:
                place(lx, ly, lhw, lhd)
                continue
            # Split the wall either side of the doorway.
            half = door_width / 2.0
            span = lhw if along_x else lhd
            lo_end = -span
            gap_lo = door_offset - half
            gap_hi = door_offset + half
            hi_end = span
            for a0, a1 in ((lo_end, gap_lo), (gap_hi, hi_end)):
                if a1 - a0 <= 0.02:
                    continue
                mid = (a0 + a1) / 2.0
                seg = (a1 - a0) / 2.0
                if along_x:
                    place(lx + mid, ly, seg, lhd)
                else:
                    place(lx, ly + mid, lhw, seg)

    def resolve(self, x: float, y: float, radius: float, z: float = 0.0):
        """Push a circle out of every blocker it overlaps."""
        if not self.grid:
            return x, y
        for _ in range(3):          # a couple of passes settles corners
            moved = False
            gx = int(math.floor(x / CELL))
            gy = int(math.floor(y / CELL))
            for i in (gx - 1, gx, gx + 1):
                for j in (gy - 1, gy, gy + 1):
                    for box in self.grid.get((i, j), ()):
                        if z > box.top:
                            continue
                        hit = box.push_out(x, y, radius)
                        if hit is not None:
                            x, y = hit
                            moved = True
            if not moved:
                break
        return x, y

"""Where things stand in the world.

Both the terrain (which flattens a pad under each building) and the props
(which place them) need these, so they live apart from either.
"""

from __future__ import annotations

LAYOUT = {
    "house": (16.0, -13.0, 205.0),
    "barn": (-19.0, -16.0, 62.0),
    "well": (7.5, 7.0, 0.0),
    "market_stall": (-13.0, -2.0, 108.0),
    "signpost": (2.0, -8.5, 24.0),
    "scarecrow": (-4.5, 12.0, 200.0),
    "cooking_pot": (13.4, -8.4, 30.0),
}

# Footprints, matching tools/make_assets.py: (width, depth, door width).
BUILDING_SHAPES = {
    "house": (6.4, 7.8, 1.5),
    "barn": (7.2, 9.0, 2.8),
}

# The tilled plots the player starts with.
PLOT_ORIGIN = (-3.0, 1.0)
PLOT_COLS, PLOT_ROWS = 6, 4
PLOT_SPACING = 1.5


def plot_positions():
    ox, oy = PLOT_ORIGIN
    for j in range(PLOT_ROWS):
        for i in range(PLOT_COLS):
            yield (ox + i * PLOT_SPACING, oy + j * PLOT_SPACING)


def building_pads():
    """(x, y, flat radius, blend distance) for every walled building."""
    for name, (w, d, _door) in BUILDING_SHAPES.items():
        x, y, _h = LAYOUT[name]
        yield x, y, max(w, d) * 0.62, 4.0


def indoors_at(x: float, y: float) -> str | None:
    """Which building the point is inside, if any.

    Buildings are rotated, so the test is done in each one's own frame — the
    same transform the props use to put furniture in place.
    """
    import math
    for name, (w, d, _door) in BUILDING_SHAPES.items():
        bx, by, bh = LAYOUT[name]
        a = math.radians(-bh)
        dx, dy = x - bx, y - by
        lx = dx * math.cos(a) - dy * math.sin(a)
        ly = dx * math.sin(a) + dy * math.cos(a)
        if abs(lx) < w / 2 - 0.2 and abs(ly) < d / 2 - 0.2:
            return name
    return None

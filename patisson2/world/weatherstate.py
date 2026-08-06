"""What the sky is doing — the part with no graphics in it.

Kept apart from the particle systems in `weather.py` because a
dedicated server decides the weather for everyone on the farm and
has nothing to draw it with. The rule for changing it lives here
too, so a hosted game and a local one get the same seasons.
"""

from __future__ import annotations


class WeatherState:
    """What the sky is doing, and how long until it changes its mind.

    Kept as an object rather than two attributes on the app so it can be saved
    with everything else: a game saved in the rain used to load into sunshine,
    which also sent the villagers back out from under their roofs.
    """

    def __init__(self, kind: str = "clear", timer: float = 40.0):
        self.kind = kind
        self.timer = timer

    def to_dict(self) -> dict:
        return {"kind": self.kind, "timer": self.timer}

    def from_dict(self, data: dict) -> None:
        from ..game.state import as_dict, as_float

        data = as_dict(data)
        kind = data.get("kind", "clear")
        self.kind = kind if kind in ("clear", "cloudy", "rain", "snow") else "clear"
        self.timer = max(1.0, as_float(data.get("timer"), 40.0))

    def roll(self, dt: float, season: int, rng) -> str | None:
        """Let the sky change its mind. Returns the new weather, or None.

        The rule lives here rather than in the app because a hosted farm
        decides the weather for everyone on it, and a server has no app.
        Snow instead of rain in winter; autumn is the wettest season.
        """
        self.timer -= dt
        if self.timer > 0.0:
            return None
        self.timer = rng.uniform(70.0, 190.0)
        if season == 3:
            choices, weights = ("clear", "cloudy", "snow"), (2, 3, 3)
        elif season == 2:
            choices, weights = ("clear", "cloudy", "rain"), (3, 3, 3)
        else:
            choices, weights = ("clear", "cloudy", "rain"), (5, 3, 2)
        self.kind = rng.choices(choices, weights=weights)[0]
        return self.kind

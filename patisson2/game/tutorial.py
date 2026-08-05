"""A tutorial that watches what the player does rather than lecturing them.

Each step names an event the game already fires when something real happens —
a plot tilled, a fish landed, the shop opened — so the checklist advances by
playing, never by dismissing a box.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    event: str
    title: str
    hint: str


STEPS: tuple[Step, ...] = (
    Step("move", "Осмотритесь на ферме",
         "W A S D — идти, мышь — смотреть, Shift — бегом"),
    Step("till", "Вскопайте грядку мотыгой",
         "1 — мотыга, наведитесь на землю у забора и нажмите E"),
    Step("plant", "Посадите семена",
         "3 — семена, Q меняет культуру, E — посадить"),
    Step("fill", "Наберите воды",
         "2 — лейка, подойдите к колодцу или пруду и нажмите E"),
    Step("water", "Полейте грядку",
         "С лейкой в руках наведитесь на грядку и нажмите E"),
    Step("weed", "Прополите заросшую грядку",
         "Сорняки лезут за полдня. Возьмите мотыгу (1) и нажмите E"),
    Step("harvest", "Соберите урожай",
         "5 — корзина. Спелое можно снимать"),
    Step("sell", "Продайте урожай у прилавка",
         "Прилавок к западу от грядок. Встаньте рядом и нажмите F"),
    Step("shop", "Загляните в лавку",
         "T — купить семена, удобрение и улучшения инструментов"),
    Step("map", "Откройте карту",
         "Tab — карта фермы, оттуда же можно перейти к любому месту"),
)

DONE_TITLE = "Ферма ваша"
DONE_HINT = "Дальше — как захотите. J — задания и достижения"


class Tutorial:
    """Tracks which step is current. Fires once per event, in order."""

    def __init__(self, active: bool = True):
        self.index = 0
        self.active = active
        self.just_completed = False

    @property
    def finished(self) -> bool:
        return self.index >= len(STEPS)

    @property
    def current(self) -> Step | None:
        if not self.active or self.finished:
            return None
        return STEPS[self.index]

    def record(self, event: str) -> Step | None:
        """Advance if this is the event the current step is waiting for."""
        step = self.current
        if step is None or step.event != event:
            return None
        self.index += 1
        self.just_completed = True
        return step

    def skip(self) -> None:
        self.index = len(STEPS)
        self.active = False

    def progress(self) -> tuple[int, int]:
        return min(self.index, len(STEPS)), len(STEPS)

    def to_dict(self) -> dict:
        return {"index": self.index, "active": self.active}

    def from_dict(self, data: dict) -> None:
        from .state import as_dict, as_int

        data = as_dict(data)
        self.index = min(len(STEPS), max(0, as_int(data.get("index"), len(STEPS))))
        self.active = bool(data.get("active", False))

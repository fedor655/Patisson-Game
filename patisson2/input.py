"""Input: named actions, rebindable keys, and an optional gamepad.

Nothing in the game accepts a raw key any more — it asks for an action, and this
decides what produces it. Keys live in the settings file, so a rebind survives a
restart.
"""

from __future__ import annotations

# (action, label shown in the UI, default key, rebindable?)
ACTIONS: tuple[tuple[str, str, str, bool], ...] = (
    ("forward", "Вперёд", "w", True),
    ("back", "Назад", "s", True),
    ("left", "Влево", "a", True),
    ("right", "Вправо", "d", True),
    ("sprint", "Бег", "shift", True),
    ("jump", "Прыжок", "space", True),
    ("interact", "Действие инструментом", "e", True),
    ("secondary", "Удобрить / лечить", "mouse3", True),
    ("sell", "Продать всё", "f", True),
    ("cycle_seed", "Сменить культуру", "q", True),
    ("shop", "Лавка", "t", True),
    ("kitchen", "Котёл", "k", True),
    ("journal", "Журнал", "j", True),
    ("map", "Карта", "tab", True),
    ("options", "Настройки", "o", True),
    ("photo", "Фоторежим", "p", True),
    ("save", "Сохранить", "f5", True),
    ("load", "Загрузить", "f9", True),
)

MOVEMENT = ("forward", "back", "left", "right", "sprint")
DEFAULTS = {a: key for a, _label, key, _rebind in ACTIONS}
LABELS = {a: label for a, label, _key, _rebind in ACTIONS}

# Keys the game needs for itself; rebinding onto them would strand the player.
RESERVED = {"escape", "enter", "arrow_up", "arrow_down", "arrow_left",
            "arrow_right", "1", "2", "3", "4", "5"}

# Panda spells a few keys unhelpfully; show something a person recognises.
KEY_NAMES = {
    "mouse1": "ЛКМ", "mouse2": "СКМ", "mouse3": "ПКМ",
    "space": "Пробел", "shift": "Shift", "control": "Ctrl", "alt": "Alt",
    "tab": "Tab", "escape": "Esc", "enter": "Enter", "backspace": "Backspace",
    "arrow_up": "↑", "arrow_down": "↓", "arrow_left": "←", "arrow_right": "→",
    "minus": "-", "equal": "=",
}


def key_label(key: str) -> str:
    if key in KEY_NAMES:
        return KEY_NAMES[key]
    if len(key) == 1:
        return key.upper()
    if key[0] == "f" and key[1:].isdigit():      # f5 -> F5
        return key.upper()
    return key


class Bindings:
    """Action -> key, with the stored overrides folded in."""

    def __init__(self, stored: dict | None = None):
        self.keys = dict(DEFAULTS)
        for action, key in (stored or {}).items():
            if action in DEFAULTS and isinstance(key, str):
                self.keys[action] = key

    def key_for(self, action: str) -> str:
        return self.keys.get(action, DEFAULTS.get(action, ""))

    def action_for(self, key: str) -> str | None:
        for action, bound in self.keys.items():
            if bound == key:
                return action
        return None

    def rebind(self, action: str, key: str) -> str | None:
        """Point an action at a key. Returns an error message, or None."""
        if key in RESERVED:
            return f"Клавиша {key_label(key)} занята интерфейсом"
        clash = self.action_for(key)
        if clash and clash != action:
            # Swap rather than leaving two actions on one key.
            self.keys[clash] = self.keys[action]
        self.keys[action] = key
        return None

    def reset(self) -> None:
        self.keys = dict(DEFAULTS)

    def to_dict(self) -> dict:
        return {a: k for a, k in self.keys.items() if k != DEFAULTS[a]}


# --------------------------------------------------------------- gamepad

# Fixed layout — a controller's face buttons are already named by convention,
# so there is nothing useful to rebind. Sticks are read per frame, not evented.
PAD_BUTTONS = {
    "face_a": "jump",
    "face_b": "interact",
    "face_x": "secondary",
    "face_y": "cycle_seed",
    "rshoulder": "interact",
    "lshoulder": "cycle_seed",
    "start": "pause",
    "back": "map",
    "dpad_up": "panel_up",
    "dpad_down": "panel_down",
    "dpad_left": "panel_left",
    "dpad_right": "panel_right",
}

PAD_DEADZONE = 0.22


class Gamepad:
    """Wraps the first connected gamepad, if there is one.

    NOTE: written against Panda's InputDevice API but not verified against
    physical hardware — no controller was attached to the machine this was
    developed on. Everything is guarded so its absence changes nothing.
    """

    def __init__(self, base):
        self.base = base
        self.device = None
        self.axes = {}
        try:
            from panda3d.core import InputDevice
            self._InputDevice = InputDevice
            pads = base.devices.getDevices(InputDevice.DeviceClass.gamepad)
        except Exception:
            self._InputDevice = None
            return
        if not pads:
            return
        self.device = pads[0]
        try:
            base.attachInputDevice(self.device, prefix="gp")
        except Exception:
            self.device = None

    @property
    def connected(self) -> bool:
        return self.device is not None

    def name(self) -> str:
        return str(self.device.name) if self.device else "нет"

    def _axis(self, which) -> float:
        if not self.device:
            return 0.0
        try:
            value = self.device.findAxis(which).value
        except Exception:
            return 0.0
        if abs(value) < PAD_DEADZONE:
            return 0.0
        # Rescale so the stick still reaches 1.0 outside the dead zone.
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - PAD_DEADZONE) / (1.0 - PAD_DEADZONE)

    def sticks(self):
        """(move_x, move_y, look_x, look_y), each -1..1."""
        if not self.device or self._InputDevice is None:
            return 0.0, 0.0, 0.0, 0.0
        A = self._InputDevice.Axis
        return (self._axis(A.left_x), self._axis(A.left_y),
                self._axis(A.right_x), self._axis(A.right_y))

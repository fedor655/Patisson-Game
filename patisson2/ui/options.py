"""In-game settings screen, driven by the keyboard like the rest of the panels.

Everything here takes effect immediately — the point of a settings screen is to
see what you changed. The values are written to disk as soon as they change, so
the next launch starts the way the player left it.
"""

from __future__ import annotations

from direct.gui.DirectGui import DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode

from .. import settings as S
from ..input import ACTIONS, key_label

INK = (0.96, 0.96, 0.94, 1)
DIM = (0.78, 0.80, 0.78, 1)
GOLD = (1.0, 0.85, 0.42, 1)

PRESET_ORDER = ("low", "medium", "high", "ultra")
SHADOW_SIZES = (1024, 2048, 4096)
GRASS_SCALES = (0.25, 0.5, 1.0, 2.0)


def _cycle(values, current, delta):
    try:
        i = values.index(current)
    except ValueError:
        i = 0
    return values[(i + delta) % len(values)]


class OptionsScreen:
    """A list of settings. Up/down to choose, left/right to change."""

    def __init__(self, base, hud):
        self.base = base
        self.hud = hud
        self.visible = False
        self.cursor = 0
        self.page = "main"          # main | keys
        self.capturing = None       # action awaiting a keypress
        self.data = base.settings

        self.root = base.aspect2d.attachNewNode("options")
        self.root.hide()
        self.backdrop = DirectFrame(parent=self.root,
                                    frameColor=(0.05, 0.05, 0.06, 0.92),
                                    frameSize=(-1.78, 1.78, -1.0, 1.0))
        self.backdrop.setBin("fixed", 0)
        self.title = OnscreenText(text="Настройки", pos=(0, 0.72), scale=0.075,
                                  fg=GOLD, font=hud.font, align=TextNode.ACenter,
                                  parent=self.root, mayChange=True)
        self.title.setBin("fixed", 2)
        # Two columns rather than padded text: the font is proportional, so
        # spaces would never line the values up.
        self.body = OnscreenText(text="", pos=(-0.72, 0.50), scale=0.052, fg=INK,
                                 font=hud.font, align=TextNode.ALeft,
                                 parent=self.root, mayChange=True)
        self.body.setBin("fixed", 2)
        self.values = OnscreenText(text="", pos=(0.62, 0.50), scale=0.052, fg=GOLD,
                                   font=hud.font, align=TextNode.ARight,
                                   parent=self.root, mayChange=True)
        self.values.setBin("fixed", 2)
        self.note = OnscreenText(
            text="Разрешение задаётся при запуске:  python -m patisson2 --fullscreen",
            pos=(-0.72, -0.14), scale=0.040, fg=DIM, font=hud.font,
            align=TextNode.ALeft, parent=self.root, mayChange=True)
        self.note.setBin("fixed", 2)
        self.hint = OnscreenText(
            text="↑↓ — пункт · ←→ — изменить · Esc — назад",
            pos=(0, -0.78), scale=0.042, fg=DIM, font=hud.font,
            align=TextNode.ACenter, parent=self.root, mayChange=True)
        self.hint.setBin("fixed", 2)

    # ------------------------------------------------------------------ rows

    def rows(self):
        d = self.data
        vol = lambda k: f"{int(round(d[k] * 100))}%"
        return [
            ("Качество", S.PRESET_NAMES.get(S.matching_preset(d), "своё")),
            ("Тени", f"{d['shadow_size']}"),
            ("Затенение (SSAO)", "вкл" if d["ssao"] else "выкл"),
            ("Свечение", "вкл" if d["bloom"] else "выкл"),
            ("Лучи солнца", "вкл" if d["godrays"] else "выкл"),
            ("Плотность травы", f"{int(d['grass_scale'] * 100)}%"),
            ("Общая громкость", vol("master_volume")),
            ("Музыка", vol("music_volume")),
            ("Звуки", vol("sfx_volume")),
            ("Управление…", "Enter"),
        ]

    def key_rows(self):
        b = self.base.bindings
        rows = [(label, key_label(b.key_for(action)))
                for action, label, _d, rebind in ACTIONS if rebind]
        rows.append(("Сбросить всё", "Enter"))
        rows.append(("Назад", "Esc"))
        return rows

    def rebindable(self):
        return [a for a, _l, _d, rebind in ACTIONS if rebind]

    def confirm(self) -> None:
        """Enter: open the key list, start a capture, or run the row's action."""
        if self.page == "main":
            if self.cursor == len(self.rows()) - 1:
                self.page = "keys"
                self.cursor = 0
                self.refresh()
            return
        rows = self.key_rows()
        if self.cursor == len(rows) - 1:
            self.back_to_main()
        elif self.cursor == len(rows) - 2:
            self.base.reset_bindings()
            self.refresh()
        else:
            self.capturing = self.rebindable()[self.cursor]
            self.base.begin_capture()
            self.refresh()

    def captured(self, key: str) -> None:
        """A key arrived while we were waiting for one."""
        action, self.capturing = self.capturing, None
        if action is None:
            return
        error = self.base.rebind(action, key)
        if error:
            self.base.state.notify(error)
        self.refresh()

    def back_to_main(self) -> None:
        self.page = "main"
        self.cursor = 0
        self.capturing = None
        self.refresh()

    def change(self, delta: int) -> None:
        if self.page == "keys":
            return
        d = self.data
        key = self.cursor
        if key >= len(self.rows()) - 1:
            return
        if key == 0:
            preset = S.matching_preset(d)
            if preset == "custom":
                preset = "high"
            S.apply_preset(d, _cycle(PRESET_ORDER, preset, delta))
        elif key == 1:
            d["shadow_size"] = _cycle(SHADOW_SIZES, d["shadow_size"], delta)
        elif key == 2:
            d["ssao"] = not d["ssao"]
        elif key == 3:
            d["bloom"] = not d["bloom"]
        elif key == 4:
            d["godrays"] = not d["godrays"]
        elif key == 5:
            d["grass_scale"] = _cycle(GRASS_SCALES, d["grass_scale"], delta)
        else:
            name = ("master_volume", "music_volume", "sfx_volume")[key - 6]
            d[name] = max(0.0, min(1.0, round(d[name] + delta * 0.1, 2)))

        if key != 0:
            d["preset"] = S.matching_preset(d)
        self.base.apply_settings()
        if getattr(self.base, "_persist_settings", True):
            S.save(d)
        self.refresh()

    def move(self, delta: int) -> None:
        if self.capturing:
            return
        rows = self.key_rows() if self.page == "keys" else self.rows()
        self.cursor = (self.cursor + delta) % len(rows)
        self.refresh()

    # --------------------------------------------------------------- control

    def open(self) -> None:
        self.visible = True
        self.root.show()
        self.refresh()

    def close(self) -> None:
        self.visible = False
        self.root.hide()

    def _layout(self, scale: float, top: float) -> None:
        """Both pages share the widgets, so re-lay them out on every switch."""
        for node, x, align in ((self.body, -0.72, None), (self.values, 0.62, None)):
            node.setScale(scale)
            node.setPos(x, top)

    def _drop_note(self, gap: float = 0.07) -> None:
        """Hang the note under the menu's measured bottom, not at a magic y.

        It used to sit at a hardcoded -0.14 while the menu's tenth row,
        at Segoe's real line height, reached -0.22: the resolution and
        gamepad lines printed straight across «Управление… Enter» —
        "немного текст пересекается", said the player. Call after the
        body text is set, because the measurement needs the rows.
        """
        tn = self.body.textNode
        scale = self.body.getScale()[0]
        top = self.body.getPos()[1]
        bottom = (top - (tn.getNumRows() - 1) * tn.getLineHeight() * scale
                  - 0.35 * scale)
        self.note.setPos(-0.72, bottom - gap)

    def refresh(self) -> None:
        if self.page == "keys":
            self._refresh_keys()
            return
        self.title.setText("Настройки")
        self._layout(scale=0.052, top=0.50)
        pad = self.base.gamepad
        self.note.setText(
            "Разрешение задаётся при запуске:  python -m patisson2 --fullscreen"
            + ("\nГеймпад: " + pad.name() if pad and pad.connected
               else "\nГеймпад не найден"))
        self.hint.setText("↑↓ — пункт · ←→ — изменить · Enter — управление · Esc — назад")
        labels, values = [], []
        for i, (label, value) in enumerate(self.rows()):
            mark = "›" if i == self.cursor else "  "
            labels.append(f"{mark} {label}")
            values.append(value)
        self.body.setText("\n".join(labels))
        self.values.setText("\n".join(values))
        self._drop_note()

    def _refresh_keys(self) -> None:
        self.title.setText("Управление")
        # Eighteen rows will not fit at the main page's size; shrink and lift.
        self._layout(scale=0.040, top=0.58)
        self.note.setText(
            "Геймпад настраивать не нужно: раскладка стандартная.\n"
            "Стики — ходьба и обзор, A — прыжок, B — действие, X — удобрить.")
        self.hint.setText("↑↓ — пункт · Enter — назначить · Esc — назад")
        labels, values = [], []
        for i, (label, value) in enumerate(self.key_rows()):
            mark = "›" if i == self.cursor else "  "
            labels.append(f"{mark} {label}")
            values.append("нажмите клавишу…" if (self.capturing and
                          i < len(self.rebindable()) and
                          self.rebindable()[i] == self.capturing) else value)
        self.body.setText("\n".join(labels))
        self.values.setText("\n".join(values))
        self._drop_note()

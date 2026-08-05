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
        ]

    def change(self, delta: int) -> None:
        d = self.data
        key = self.cursor
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
        self.cursor = (self.cursor + delta) % len(self.rows())
        self.refresh()

    # --------------------------------------------------------------- control

    def open(self) -> None:
        self.visible = True
        self.root.show()
        self.refresh()

    def close(self) -> None:
        self.visible = False
        self.root.hide()

    def refresh(self) -> None:
        labels, values = [], []
        for i, (label, value) in enumerate(self.rows()):
            mark = "›" if i == self.cursor else "  "
            labels.append(f"{mark} {label}")
            values.append(value)
        self.body.setText("\n".join(labels))
        self.values.setText("\n".join(values))

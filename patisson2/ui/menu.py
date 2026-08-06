"""Title screen: menu over a slow cinematic pass across the farm."""

from __future__ import annotations

import math

from direct.gui.DirectGui import DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode, TransparencyAttrib, Vec3

from ..game.state import (ACHIEVEMENTS, AUTOSAVE, SLOTS, any_save, describe,
                          slot_label)
from .hud import fit_text

GOLD = (1.0, 0.86, 0.45, 1)
INK = (0.95, 0.95, 0.93, 1)
DIM = (0.74, 0.76, 0.74, 1)
BTN = (0.10, 0.13, 0.11, 0.86)
BTN_HOVER = (0.24, 0.30, 0.18, 0.95)
BTN_DOWN = (0.35, 0.42, 0.22, 0.98)
DISABLED = (0.09, 0.10, 0.10, 0.60)

# Camera keyframes the title view drifts between: (eye xy, look-at xy, height).
CINEMATIC = [
    ((31.0, -31.0), (2.0, 3.0), 9.0),
    ((-7.0, -35.0), (1.0, 6.0), 6.5),
    ((-43.0, 4.0), (-30.0, 24.0), 8.5),
    ((-6.0, 36.0), (-1.0, 5.0), 7.5),
    ((36.0, 8.0), (13.0, -9.0), 8.5),
]
LEG_SECONDS = 13.0


class MainMenu:
    """Owns the title screen and the settings/achievements panes behind it."""

    def __init__(self, app, hud):
        self.app = app
        self.hud = hud
        self.font = hud.font
        self.visible = False
        self.pane = "root"          # root | settings | achievements
        self.time = 0.0

        a2d = app.aspect2d
        self.root = a2d.attachNewNode("main-menu")
        self.root.hide()

        # A soft vertical scrim so the text stays readable over any scenery.
        self.scrim = DirectFrame(parent=self.root, frameColor=(0.02, 0.03, 0.03, 0.55),
                                 frameSize=(-0.95, 0.52, -1.0, 1.0),
                                 pos=(-0.72, 0, 0))
        self.scrim.setTransparency(TransparencyAttrib.MAlpha)

        self.title = OnscreenText(
            text="PATISSON", pos=(-1.36, 0.62), scale=0.20, fg=GOLD,
            font=self.font, align=TextNode.ALeft, parent=self.root,
            shadow=(0, 0, 0, 0.8), shadowOffset=(0.04, 0.04), mayChange=True)
        self.subtitle = OnscreenText(
            text="2.0", pos=(-1.36, 0.47), scale=0.085, fg=INK,
            font=self.font, align=TextNode.ALeft, parent=self.root,
            shadow=(0, 0, 0, 0.7), shadowOffset=(0.05, 0.05), mayChange=True)
        self.credit = OnscreenText(
            text="по игре Богдана", pos=(-1.36, 0.37), scale=0.045, fg=DIM,
            font=self.font, align=TextNode.ALeft, parent=self.root, mayChange=True)
        self.footer = OnscreenText(
            text="", pos=(-1.36, -0.92), scale=0.038, fg=DIM,
            font=self.font, align=TextNode.ALeft, parent=self.root, mayChange=True)

        self.buttons: list[DirectButton] = []
        # The achievements list is long and set small; over a sunlit field the
        # scrim alone is not enough to read it against.
        self.info_panel = DirectFrame(
            parent=self.root, frameColor=(0.05, 0.06, 0.05, 0.88),
            frameSize=(-1.42, -0.52, -0.72, 0.14))
        self.info_panel.setTransparency(TransparencyAttrib.MAlpha)
        self.info_panel.hide()
        self.info = OnscreenText(
            text="", pos=(-1.36, -0.62), scale=0.042, fg=DIM, font=self.font,
            align=TextNode.ALeft, parent=self.root, mayChange=True, wordwrap=26)

        self._build_root()

    # ------------------------------------------------------------- building

    def _clear_buttons(self):
        for b in self.buttons:
            b.destroy()
        self.buttons.clear()
        # The achievements pane moves and shrinks the info text; every other
        # pane expects it where it started.
        self.info.setPos(-1.36, -0.62)
        self.info.setScale(0.042)
        self.info["wordwrap"] = 26
        self.info.setFg(DIM)
        self.info_panel.hide()

    # Text starts at -0.52 and the frame ends at 0.56, so this much room.
    BUTTON_TEXT_WIDTH = 1.05

    def _button(self, index: int, label: str, command, enabled=True) -> DirectButton:
        b = DirectButton(
            parent=self.root, text=label, text_font=self.font,
            text_fg=INK if enabled else (0.5, 0.5, 0.5, 1),
            text_scale=0.058, text_align=TextNode.ALeft, text_pos=(-0.52, -0.020),
            frameColor=(BTN, BTN_HOVER, BTN_DOWN, DISABLED),
            frameSize=(-0.56, 0.56, -0.048, 0.058),
            relief=1, pos=(-0.80, 0, 0.20 - index * 0.135),
            command=command if enabled else None,
            state="normal" if enabled else "disabled",
        )
        # Save-slot labels carry a whole line of detail and used to run a third
        # of their length out past the frame.
        fit_text(b, self.BUTTON_TEXT_WIDTH, start=0.058, floor=0.030)
        b.setTransparency(TransparencyAttrib.MAlpha)
        self.buttons.append(b)
        return b

    def _build_root(self):
        self.pane = "root"
        self._clear_buttons()
        has_save = any_save()
        self._button(0, "  Играть", self.app.menu_new_game)
        self._button(1, "  Продолжить", self.app.menu_continue, enabled=has_save)
        self._button(2, "  Загрузить…", lambda: self._build_saves(),
                     enabled=has_save)
        self._button(3, "  Играть по сети", self.app.menu_join_server)
        self._button(4, "  Настройки", self.app.toggle_options)
        self._button(5, "  Достижения", lambda: self._build_achievements())
        self._button(6, "  Выход", self.app.userExit)
        self.info.setText("" if has_save else "Сохранения пока нет — начните новую игру.")
        self.footer.setText("Panda3D · всё сгенерировано кодом")

    def _build_saves(self):
        """List every slot with what is actually in it."""
        self.app.sound("click", 0.5)
        self.pane = "saves"
        self._clear_buttons()
        slots = [AUTOSAVE] + list(SLOTS)
        for i, slot in enumerate(slots):
            text = f"  {slot_label(slot)} — {describe(slot)}"
            self._button(i, text, lambda s=slot: self.app.menu_load_slot(s),
                         enabled=describe(slot) != "пусто")
        self._button(len(slots), "  Назад", lambda: (self.app.sound("click", 0.5),
                                                     self._build_root()))
        self.info.setText("Автосохранение пишется каждые две минуты,\n"
                          "на рассвете и при выходе в меню.")

    def _build_settings(self):
        self.app.sound("click", 0.5)
        self.pane = "settings"
        self._clear_buttons()
        audio = self.app.audio

        def bump(kind, delta):
            self.app.sound("click", 0.4)
            if audio:
                if kind == "master":
                    audio.nudge_master(delta)
                else:
                    audio.nudge_music(delta)
            self._refresh_settings()

        self._button(0, "  Громкость  −", lambda: bump("master", -0.1))
        self._button(1, "  Громкость  +", lambda: bump("master", 0.1))
        self._button(2, "  Музыка  −", lambda: bump("music", -0.1))
        self._button(3, "  Музыка  +", lambda: bump("music", 0.1))
        self._button(4, "  Назад", lambda: (self.app.sound("click", 0.5),
                                            self._build_root()))
        self._refresh_settings()

    def _refresh_settings(self):
        audio = self.app.audio
        if audio and audio.enabled:
            music = "готова" if audio.music else "генерируется…"
            self.info.setText(
                f"Общая громкость: {audio.master * 100:.0f}%\n"
                f"Музыка: {audio.music_volume * 100:.0f}%  ({music})\n\n"
                "Качество задаётся ключом запуска:\n"
                "--low  ·  --medium  ·  --ultra")
        else:
            self.info.setText("Звук недоступен на этой системе.")

    def _build_achievements(self):
        self.app.sound("click", 0.5)
        self.pane = "achievements"
        self._clear_buttons()
        self._button(0, "  Назад", lambda: (self.app.sound("click", 0.5),
                                            self._build_root()))
        got = self.app.state.achievements
        from .hud import MARK
        lines = [f"{MARK if k in got else '·'}  {v}" for k, v in ACHIEVEMENTS.items()]
        # Eighteen achievements at the usual size ran off the bottom of the
        # screen: only the first six were ever visible. Start under the one
        # button this pane has, and size the list to the room left.
        top, scale = 0.04, 0.032
        self.info.setPos(-1.36, top)
        self.info.setScale(scale)
        self.info["wordwrap"] = 40
        self.info.setFg(INK)
        text = f"Открыто {len(got)} из {len(ACHIEVEMENTS)}\n\n" + "\n".join(lines)
        self.info.setText(text)
        # Size the backing panel to the text rather than to a guess: the list
        # grows every time an achievement is added.
        rows = text.count("\n") + 1
        bottom = top - rows * scale * 1.22 - 0.03
        self.info_panel["frameSize"] = (-1.42, -0.52, bottom, top + 0.10)
        self.info_panel.show()

    # -------------------------------------------------------------- control

    def show(self):
        self.visible = True
        self._build_root()
        self.root.show()

    def hide(self):
        self.visible = False
        self.root.hide()

    def back(self) -> bool:
        """Escape handler. Returns True if it consumed the key."""
        if self.pane != "root":
            self._build_root()
            return True
        return False

    def update(self, dt: float, camera, world):
        """Drift the camera along the cinematic path, easing between legs."""
        self.time += dt
        n = len(CINEMATIC)
        t = self.time / LEG_SECONDS
        i = int(t) % n
        f = t - int(t)
        f = f * f * (3.0 - 2.0 * f)          # smoothstep between keyframes

        (ex0, ey0), (lx0, ly0), h0 = CINEMATIC[i]
        (ex1, ey1), (lx1, ly1), h1 = CINEMATIC[(i + 1) % n]
        ex = ex0 + (ex1 - ex0) * f
        ey = ey0 + (ey1 - ey0) * f
        lx = lx0 + (lx1 - lx0) * f
        ly = ly0 + (ly1 - ly0) * f
        h = h0 + (h1 - h0) * f

        # A slow circling drift on top so the shot is never quite still.
        swing = math.sin(self.time * 0.09) * 2.4
        ex += swing
        ey += math.cos(self.time * 0.07) * 1.8

        eye = Vec3(ex, ey, world.height_at(ex, ey) + h)
        camera.setPos(eye)
        camera.lookAt(lx, ly, world.height_at(lx, ly) + 1.2)
        return eye

"""Heads-up display, shop, journal, dialogue and pause menu."""

from __future__ import annotations

from pathlib import Path

from direct.gui.DirectGui import DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import CardMaker, NodePath, TextNode, TransparencyAttrib, Vec4

from ..game.farming import CROPS, CROP_ORDER
from ..game.state import ACHIEVEMENTS, SHOP_ITEMS, TOOL_NAMES, TOOLS

# Panda's built-in font has no Cyrillic; fall back through the usual suspects.
FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

INK = (0.96, 0.96, 0.94, 1)
DIM = (0.80, 0.82, 0.80, 1)
GOLD = (1.0, 0.85, 0.42, 1)
GREEN = (0.66, 0.92, 0.60, 1)
RED = (1.0, 0.55, 0.48, 1)
PANEL = (0.07, 0.08, 0.09, 0.90)


def _load_font(loader):
    from panda3d.core import Filename
    for path in FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            # Panda needs its own path flavour ("/c/Windows/..."), not the OS one.
            font = loader.loadFont(Filename.fromOsSpecific(path).getFullpath())
        except OSError:
            continue
        if font is not None and font.isValid():
            font.setPixelsPerUnit(64)
            font.setPageSize(1024, 1024)
            return font
    return None


class HUD:
    def __init__(self, base, state, cfg):
        self.base = base
        self.state = state
        self.cfg = cfg
        self.font = _load_font(base.loader)
        self.visible = True
        self.panel_mode: str | None = None      # None | shop | journal | pause
        self.dialogue: tuple[str, str] | None = None
        self.shop_index = 0
        self._last: dict[int, str] = {}
        self._stamina_step = -1
        self.panel_buttons: list = []

        a2d = base.aspect2d
        self.root = a2d.attachNewNode("hud")

        def text(pos, scale=0.048, align=TextNode.ALeft, fg=INK, parent=None):
            return OnscreenText(text="", pos=pos, scale=scale, align=align,
                                fg=fg, font=self.font, mayChange=True,
                                parent=parent or self.root,
                                shadow=(0, 0, 0, 0.55), shadowOffset=(0.05, 0.05))

        self.clock_text = text((-1.72, 0.90), 0.052)
        self.season_text = text((-1.72, 0.835), 0.042, fg=DIM)
        self.weather_text = text((-1.72, 0.775), 0.040, fg=DIM)

        self.coins_text = text((1.72, 0.90), 0.055, TextNode.ARight, GOLD)
        self.fish_text = text((1.72, 0.835), 0.044, TextNode.ARight, DIM)
        self.water_text = text((1.72, 0.775), 0.044, TextNode.ARight, (0.62, 0.84, 1.0, 1))

        self.prompt = text((0, -0.30), 0.052, TextNode.ACenter, GREEN)
        self.tooltip = text((0, -0.38), 0.040, TextNode.ACenter, DIM)

        self.notif = [text((-1.72, -0.55 + i * 0.062), 0.040, fg=(1, 1, 1, 1))
                      for i in range(5)]

        self.tool_labels = []
        for i in range(len(TOOLS)):
            self.tool_labels.append(
                text((-0.62 + i * 0.31, -0.90), 0.040, TextNode.ACenter, DIM))
        self.tool_slot_bg = []
        cm = CardMaker("slot")
        cm.setFrame(-0.13, 0.13, -0.055, 0.075)
        for i in range(len(TOOLS)):
            np_ = self.root.attachNewNode(cm.generate())
            np_.setPos(-0.62 + i * 0.31, 0, -0.885)
            np_.setColor(0.05, 0.06, 0.07, 0.55)
            np_.setTransparency(TransparencyAttrib.MAlpha)
            np_.setBin("fixed", 10)
            self.tool_slot_bg.append(np_)

        self.crosshair = OnscreenText(text="+", pos=(0, -0.012), scale=0.055,
                                      fg=(1, 1, 1, 0.55), font=self.font,
                                      align=TextNode.ACenter, parent=self.root)

        self.stamina = DirectFrame(parent=self.root, frameColor=(0.4, 0.9, 0.5, 0.75),
                                   frameSize=(0, 0.5, 0, 0.014),
                                   pos=(-0.25, 0, -0.955))
        self.stamina_bg = DirectFrame(parent=self.root, frameColor=(0, 0, 0, 0.4),
                                      frameSize=(0, 0.5, 0, 0.014),
                                      pos=(-0.25, 0, -0.955))
        self.stamina_bg.setBin("fixed", 5)
        self.stamina.setBin("fixed", 6)

        # Overlay panel used for the shop, journal, pause menu and dialogue.
        self.panel = DirectFrame(parent=a2d, frameColor=PANEL,
                                 frameSize=(-1.05, 1.05, -0.72, 0.72))
        self.panel.hide()
        self.panel_title = OnscreenText(text="", pos=(0, 0.60), scale=0.075,
                                        fg=GOLD, font=self.font, mayChange=True,
                                        align=TextNode.ACenter, parent=self.panel)
        self.panel_body = OnscreenText(text="", pos=(-0.95, 0.44), scale=0.047,
                                       fg=INK, font=self.font, mayChange=True,
                                       align=TextNode.ALeft, parent=self.panel)
        self.panel_hint = OnscreenText(text="", pos=(0, -0.64), scale=0.040,
                                       fg=DIM, font=self.font, mayChange=True,
                                       align=TextNode.ACenter, parent=self.panel)

        self.dialog_frame = DirectFrame(parent=a2d, frameColor=(0.06, 0.07, 0.08, 0.88),
                                        frameSize=(-1.0, 1.0, -0.20, 0.16),
                                        pos=(0, 0, -0.60))
        self.dialog_frame.hide()
        self.dialog_name = OnscreenText(text="", pos=(-0.94, 0.06), scale=0.055,
                                        fg=GOLD, font=self.font, mayChange=True,
                                        align=TextNode.ALeft, parent=self.dialog_frame)
        self.dialog_text = OnscreenText(text="", pos=(-0.94, -0.03), scale=0.047,
                                        fg=INK, font=self.font, mayChange=True,
                                        align=TextNode.ALeft, parent=self.dialog_frame,
                                        wordwrap=38)

    # ------------------------------------------------------------------ show

    def toggle(self):
        self.visible = not self.visible
        if self.visible:
            self.root.show()
        else:
            self.root.hide()

    def set_prompt(self, text: str, tip: str = ""):
        self._set(self.prompt, text)
        self._set(self.tooltip, tip)

    def show_dialogue(self, name: str, line: str):
        self.dialogue = (name, line)
        self.dialog_name.setText(name)
        self.dialog_text.setText(line)
        self.dialog_frame.show()

    def hide_dialogue(self):
        self.dialogue = None
        self.dialog_frame.hide()

    # ---------------------------------------------------------------- panels

    def open_panel(self, mode: str):
        self.panel_mode = mode
        self.panel.show()
        self.refresh_panel()
        if mode == "pause":
            self._build_pause_buttons()

    def close_panel(self):
        self.panel_mode = None
        self.panel.hide()
        for b in self.panel_buttons:
            b.destroy()
        self.panel_buttons.clear()

    def _build_pause_buttons(self):
        """Pause needs a way out that is not just Esc."""
        from direct.gui.DirectGui import DirectButton
        app = self.base
        entries = [
            ("Продолжить", app.on_escape),
            ("Сохранить", app.on_save),
            ("В главное меню", app.open_main_menu),
            ("Выход", app.userExit),
        ]
        for i, (label, cmd) in enumerate(entries):
            b = DirectButton(
                parent=self.panel, text=label, text_font=self.font,
                text_fg=INK, text_scale=0.045, text_pos=(0, -0.015),
                frameColor=((0.12, 0.14, 0.12, 0.9), (0.26, 0.32, 0.18, 0.95),
                            (0.34, 0.42, 0.22, 1.0), (0.1, 0.1, 0.1, 0.6)),
                frameSize=(-0.24, 0.24, -0.042, 0.052), relief=1,
                pos=(-0.75 + i * 0.50, 0, -0.52), command=cmd)
            b.setTransparency(TransparencyAttrib.MAlpha)
            self.panel_buttons.append(b)

    def refresh_panel(self):
        if self.panel_mode == "shop":
            self.panel_title.setText("Лавка")
            lines = []
            for i, (key, name, price, desc) in enumerate(SHOP_ITEMS):
                owned = ""
                if key in ("golden_can", "enchanted_rod", "lantern_oil"):
                    if getattr(self.state.upgrades, key):
                        owned = "  [куплено]"
                cursor = ">" if i == self.shop_index else " "
                lines.append(f"{cursor} {name:<24} {price:>4} мон.{owned}")
                if i == self.shop_index:
                    lines.append(f"    {desc}")
            self.panel_body.setText("\n".join(lines))
            self.panel_hint.setText(
                f"Монет: {self.state.coins}    "
                "↑/↓ выбор   Enter купить   F продать всё   Esc выход")
        elif self.panel_mode == "journal":
            self.panel_title.setText("Журнал")
            lines = ["ЗАДАНИЯ", ""]
            for q in self.state.quests:
                mark = "✔" if q.done else " "
                lines.append(f" [{mark}] {q.title}  ({min(q.progress, q.goal)}/{q.goal})")
                lines.append(f"      {q.detail}")
            lines += ["", "ДОСТИЖЕНИЯ", ""]
            for key, desc in ACHIEVEMENTS.items():
                mark = "✔" if key in self.state.achievements else " "
                lines.append(f" [{mark}] {desc}")
            self.panel_body.setText("\n".join(lines))
            self.panel_hint.setText("J или Esc — закрыть")
        elif self.panel_mode == "pause":
            self.panel_title.setText("Пауза")
            inv = []
            for key in CROP_ORDER:
                n = self.state.count(key)
                if n:
                    inv.append(f"  {CROPS[key].name}: {n}")
            seeds = []
            for key in CROP_ORDER:
                n = self.state.count(f"seed_{key}")
                if n:
                    seeds.append(f"  Семена «{CROPS[key].name}»: {n}")
            lines = ["УПРАВЛЕНИЕ", "",
                     "  WASD — движение,  Shift — бег,  Space — прыжок",
                     "  ЛКМ / E — действие инструментом",
                     "  1..5 — инструменты,  Q/колесо — выбор семян",
                     "  T — магазин,  J — журнал,  F5 — сохранить,  F9 — загрузить",
                     "  P — фотореж. (трассировка лучей),  F1 — интерфейс",
                     "  M — звук вкл/выкл,  - / = — громкость",
                     "  F — продать всё у прилавка,  Esc — пауза",
                     "", "В СУМКЕ", ""]
            lines += inv or ["  (пусто)"]
            lines += [""] + (seeds or ["  Семян нет"])
            lines += ["", f"  Рыба: {self.state.fish}",
                      f"  Монеты: {self.state.coins}"]
            audio = getattr(self.base, "audio", None)
            if audio is not None and audio.enabled:
                lines += ["", "ЗВУК", "",
                          f"  Громкость: {audio.master * 100:.0f}%",
                          f"  Музыка: {audio.music_volume * 100:.0f}%"]
                if not audio.music:
                    lines.append("  (музыка ещё генерируется…)")
            self.panel_body.setText("\n".join(lines))
            self.panel_hint.setText("")

    def move_shop_cursor(self, delta: int):
        self.shop_index = (self.shop_index + delta) % len(SHOP_ITEMS)
        self.refresh_panel()

    @property
    def shop_key(self) -> str:
        return SHOP_ITEMS[self.shop_index][0]

    # ---------------------------------------------------------------- update

    def _set(self, node, value: str):
        if self._last.get(id(node)) != value:
            self._last[id(node)] = value
            node.setText(value)

    def update(self, cycle, state, weather: str):
        self._set(self.clock_text, f"{cycle.clock_string()}   День {cycle.day + 1}")
        self._set(self.season_text, cycle.season_name)
        self._set(self.weather_text, weather)
        self._set(self.coins_text, f"{state.coins} мон.")
        self._set(self.fish_text, f"Рыба: {state.fish}")
        cap = state.upgrades.can_capacity
        self._set(self.water_text, f"Вода: {state.water:.0f}/{cap:.0f}")

        for i, key in enumerate(TOOLS):
            label = TOOL_NAMES[key]
            if key == "seeds":
                crop = CROPS[state.seed_key]
                have = state.count(f"seed_{state.seed_key}")
                label = f"{crop.name} x{have}"
            selected = (i == state.tool_index)
            self._set(self.tool_labels[i], f"{i+1} {label}")
            self.tool_labels[i]["fg"] = GOLD if selected else DIM
            self.tool_slot_bg[i].setColor(
                (0.30, 0.26, 0.08, 0.75) if selected else (0.05, 0.06, 0.07, 0.55))

        for i, slot in enumerate(self.notif):
            if i < len(state.notifications):
                text, remaining = state.notifications[i]
                self._set(slot, text)
                slot["fg"] = (1, 1, 1, min(1.0, remaining / 0.8))
            else:
                self._set(slot, "")

        if getattr(state, "photo_progress", None) is not None:
            pct = int(state.photo_progress * 100)
            self._set(self.tooltip,
                      f"Фоторежим: трассировка лучей — {pct}%"
                      if pct < 100 else "Фоторежим: готово")

        # Assigning frameSize rebuilds the frame's geometry, so quantise it —
        # a bar that redraws every frame costs more than the rest of the HUD.
        frac = max(0.0, min(1.0, state.stamina_frac))
        step = round(frac * 40)
        if step != self._stamina_step:
            self._stamina_step = step
            self.stamina["frameSize"] = (0, 0.5 * step / 40.0, 0, 0.014)
            self.stamina["frameColor"] = ((0.95, 0.55, 0.35, 0.8) if frac < 0.3
                                          else (0.4, 0.9, 0.5, 0.75))

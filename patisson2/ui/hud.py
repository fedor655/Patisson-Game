"""Heads-up display, shop, journal, dialogue and pause menu."""

from __future__ import annotations

from pathlib import Path

from direct.gui.DirectGui import DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import CardMaker, NodePath, TextNode, TransparencyAttrib, Vec4

from ..game.farming import CROPS, CROP_ORDER
from ..game.state import (ACHIEVEMENTS, TOOL_NAMES, TOOLS, shop_entries)

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
        self._tool_index = -1
        self._notif_alpha = [-1] * 5
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

        # --- fishing reel bar -------------------------------------------
        self.fish_bar = DirectFrame(
            parent=self.root, frameColor=(0.04, 0.05, 0.06, 0.80),
            frameSize=(-0.34, 0.34, -0.030, 0.030), pos=(0, 0, -0.17))
        self.fish_zone = DirectFrame(
            parent=self.fish_bar, frameColor=(0.34, 0.86, 0.44, 0.55),
            frameSize=(-0.05, 0.05, -0.028, 0.028))
        self.fish_marker = DirectFrame(
            parent=self.fish_bar, frameColor=(1.0, 0.92, 0.55, 0.95),
            frameSize=(-0.008, 0.008, -0.036, 0.036))
        self.fish_label = OnscreenText(
            text="", pos=(0, 0.055), scale=0.042, fg=INK, font=self.font,
            align=TextNode.ACenter, parent=self.fish_bar, mayChange=True)
        self.fish_bar.hide()
        self._fish_shown = False
        self._fish_band = -1.0

        # --- tutorial checklist ------------------------------------------
        self.tutor_panel = DirectFrame(
            parent=self.root, frameColor=(0.05, 0.06, 0.07, 0.72),
            frameSize=(-0.02, 0.86, -0.20, 0.055), pos=(-1.74, 0, 0.60))
        self.tutor_panel.setBin("fixed", 8)
        self.tutor_head = OnscreenText(
            text="", pos=(0.0, 0.0), scale=0.038, fg=(0.72, 0.78, 0.72, 1),
            font=self.font, align=TextNode.ALeft, parent=self.tutor_panel,
            mayChange=True)
        self.tutor_title = OnscreenText(
            text="", pos=(0.0, -0.062), scale=0.046, fg=GOLD, font=self.font,
            align=TextNode.ALeft, parent=self.tutor_panel, mayChange=True)
        self.tutor_hint = OnscreenText(
            text="", pos=(0.0, -0.122), scale=0.036, fg=DIM, font=self.font,
            align=TextNode.ALeft, parent=self.tutor_panel, mayChange=True,
            wordwrap=24)
        self.tutor_panel.hide()
        self._tutor_shown = False

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
            ("Пропустить обучение", app.skip_tutorial),
            ("Сохранить", app.on_save),
            ("В главное меню", app.open_main_menu),
            ("Выход", app.userExit),
        ]
        for i, (label, cmd) in enumerate(entries):
            b = DirectButton(
                parent=self.panel, text=label, text_font=self.font,
                text_fg=INK, text_scale=0.036, text_pos=(0, -0.012),
                frameColor=((0.12, 0.14, 0.12, 0.9), (0.26, 0.32, 0.18, 0.95),
                            (0.34, 0.42, 0.22, 1.0), (0.1, 0.1, 0.1, 0.6)),
                frameSize=(-0.172, 0.172, -0.042, 0.052), relief=1,
                pos=(-0.86 + i * 0.36, 0, -0.615), command=cmd)
            b.setTransparency(TransparencyAttrib.MAlpha)
            self.panel_buttons.append(b)

    def refresh_panel(self):
        if self.panel_mode == "shop":
            self.panel_title.setText("Лавка")
            lines = []
            for i, (key, name, price, desc) in enumerate(shop_entries(self.state.upgrades)):
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
        elif self.panel_mode == "kitchen":
            from ..game.cooking import RECIPES, item_name
            kitchen = self.base.kitchen
            self.panel_title.setText("Котёл")
            lines = []
            for i, r in enumerate(RECIPES):
                cursor = ">" if i == kitchen.index else " "
                parts = "  ".join(f"{item_name(k)} x{v}" for k, v in r.inputs.items())
                have = self.state.count(r.key)
                stock = f"   (в сумке: {have})" if have else ""
                lines.append(f"{cursor} {r.name:<22} {r.sell_price:>4} мон.{stock}")
                lines.append(f"    {parts}")
                if i == kitchen.index:
                    missing = kitchen.missing(r)
                    if missing:
                        short = ", ".join(f"{item_name(k)} x{v}"
                                          for k, v in missing.items())
                        lines.append(f"    не хватает: {short}")
                    else:
                        lines.append(f"    можно готовить  ·  +{r.stamina:.0f} сил")
                lines.append("")
            self.panel_body.setText("\n".join(lines))
            self.panel_hint.setText(
                "↑/↓ выбор   Enter приготовить   F съесть   K или Esc выход")
        elif self.panel_mode == "journal":
            self.panel_title.setText("Журнал")
            lines = ["ЗАДАНИЯ", ""]
            for q in self.state.quests:
                mark = "✔" if q.done else " "
                lines.append(f" [{mark}] {q.title}  ({min(q.progress, q.goal)}/{q.goal})")
                lines.append(f"      {q.detail}")
            from ..game.fishing import SPECIES
            caught = self.state.fish_log
            if caught:
                lines += ["", "УЛОВ", ""]
                for sp in SPECIES:
                    entry = caught.get(sp.key)
                    if not entry:
                        continue
                    count, kilos = entry
                    biggest = kilos / max(count, 1)
                    lines.append(f"  {sp.name}: {count} шт, {kilos:.1f} кг "
                                 f"(в среднем {biggest:.1f})")
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
                     "  T — магазин,  K — котёл,  J — журнал,  Tab — карта",
                     "  F5 — сохранить,  F9 — загрузить",
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
        self.shop_index = (self.shop_index + delta) % len(shop_entries(self.state.upgrades))
        self.refresh_panel()

    @property
    def shop_key(self) -> str:
        return shop_entries(self.state.upgrades)[self.shop_index][0]

    # ---------------------------------------------------------------- update

    def _update_tutorial(self):
        """Show the current objective, or the sign-off once it is all done."""
        tut = getattr(self.base, "tutorial", None)
        if tut is None or not tut.active:
            if self._tutor_shown:
                self.tutor_panel.hide()
                self._tutor_shown = False
            return
        if not self._tutor_shown:
            self.tutor_panel.show()
            self._tutor_shown = True
        done, total = tut.progress()
        step = tut.current
        if step is None:
            from ..game.tutorial import DONE_HINT, DONE_TITLE
            self._set(self.tutor_head, f"ОБУЧЕНИЕ  {total}/{total}")
            self._set(self.tutor_title, DONE_TITLE)
            self._set(self.tutor_hint, DONE_HINT)
        else:
            self._set(self.tutor_head, f"ОБУЧЕНИЕ  {done}/{total}")
            self._set(self.tutor_title, step.title)
            self._set(self.tutor_hint, step.hint)

    def _update_fishing(self):
        """Draw the reel bar: a sweeping marker and the band to stop it in."""
        from ..game.fishing import REELING
        fishing = getattr(self.base, "fishing", None)
        fs = fishing.state if fishing else None
        if fs is None or fs.phase != REELING or fs.species is None:
            if self._fish_shown:
                self.fish_bar.hide()
                self._fish_shown = False
            return
        if not self._fish_shown:
            self.fish_bar.show()
            self._fish_shown = True

        half = 0.34
        # frameSize rebuilds the frame, so only when the species changes.
        if abs(fs.band - self._fish_band) > 1e-4:
            self._fish_band = fs.band
            zone = fs.band * half
            self.fish_zone["frameSize"] = (-zone, zone, -0.028, 0.028)
        self.fish_zone.setX(-half + fs.band_centre * half * 2.0)
        self.fish_marker.setX(-half + fs.marker * half * 2.0)
        self._set(self.fish_label,
                  f"{fs.species.name}   {fs.pulls_done}/{fs.species.pulls}"
                  f"   промахи {fs.misses}/3")

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
            self._set(self.tool_labels[i], f"{i+1} {label}")

        # Assigning to a DirectGui item calls configure(), which rebuilds the
        # widget. Doing that for every slot every frame cost more than the whole
        # rest of the frame, so only touch the two slots that actually changed.
        if state.tool_index != self._tool_index:
            for i in (self._tool_index, state.tool_index):
                if not 0 <= i < len(TOOLS):
                    continue
                selected = (i == state.tool_index)
                self.tool_labels[i]["fg"] = GOLD if selected else DIM
                self.tool_slot_bg[i].setColor(
                    (0.30, 0.26, 0.08, 0.75) if selected
                    else (0.05, 0.06, 0.07, 0.55))
            self._tool_index = state.tool_index

        for i, slot in enumerate(self.notif):
            if i < len(state.notifications):
                text, remaining = state.notifications[i]
                self._set(slot, text)
                # Quantise the fade so the widget is not rebuilt every frame.
                alpha = round(min(1.0, remaining / 0.8) * 8)
                if self._notif_alpha[i] != alpha:
                    self._notif_alpha[i] = alpha
                    slot["fg"] = (1, 1, 1, alpha / 8.0)
            else:
                self._set(slot, "")

        if getattr(state, "photo_progress", None) is not None:
            pct = int(state.photo_progress * 100)
            self._set(self.tooltip,
                      f"Фоторежим: трассировка лучей — {pct}%"
                      if pct < 100 else "Фоторежим: готово")

        # Assigning frameSize rebuilds the frame's geometry, so quantise it —
        # a bar that redraws every frame costs more than the rest of the HUD.
        self._update_fishing()
        self._update_tutorial()

        frac = max(0.0, min(1.0, state.stamina_frac))
        step = round(frac * 40)
        if step != self._stamina_step:
            self._stamina_step = step
            self.stamina["frameSize"] = (0, 0.5 * step / 40.0, 0, 0.014)
            self.stamina["frameColor"] = ((0.95, 0.55, 0.35, 0.8) if frac < 0.3
                                          else (0.4, 0.9, 0.5, 0.75))

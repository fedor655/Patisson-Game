"""Heads-up display, shop, journal, dialogue and pause menu."""

from __future__ import annotations

from pathlib import Path

from direct.gui.DirectGui import DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import CardMaker, TextNode, TransparencyAttrib

from ..game.farming import CROPS, CROP_ORDER, days_to_ripe
from ..game.state import (ACHIEVEMENTS, TOOL_NAMES, TOOLS, shop_entries)

JOURNAL_PAGES = ("задания", "справочник", "статистика")

# A tick mark would read better, but the fonts we fall back to below do not all
# carry U+2714 — Segoe UI renders it as an empty box. "x" is always there.
MARK = "x"


def fit_text(button, max_width: float, start: float, floor: float = 0.028):
    """Shrink a button's text until it fits inside the button.

    Guessing a scale that suits the longest label you happened to think of is
    how the save-slot buttons ended up with their text hanging a third of the
    way past the frame. Measure the glyphs instead.
    """
    node = button.component("text0").textNode
    width = node.getWidth()
    if width <= 0.0:
        return start
    scale = min(start, max_width / width)
    scale = max(scale, floor)
    button["text_scale"] = (scale, scale)
    return scale

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
        self.journal_page = 0
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
        # Second column, used by the journal; hidden for every other panel.
        self.panel_body2 = OnscreenText(text="", pos=(0.02, 0.44), scale=0.047,
                                        fg=INK, font=self.font, mayChange=True,
                                        align=TextNode.ALeft, parent=self.panel)
        self.panel_body2.hide()
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

    # Every journal page is two columns: nine quests plus eighteen achievements
    # do not fit down one, and neither do five crops plus seven fish.

    def _journal_quests(self):
        left = ["ЗАДАНИЯ", ""]
        for q in self.state.quests:
            mark = MARK if q.done else " "
            left.append(f" [{mark}] {q.title}  ({min(q.progress, q.goal)}/{q.goal})")
            left.append(f"      {q.detail}")
        right = ["ДОСТИЖЕНИЯ", ""]
        for key, desc in ACHIEVEMENTS.items():
            mark = MARK if key in self.state.achievements else " "
            right.append(f" [{mark}] {desc}")
        return left, right

    def _journal_almanac(self):
        """What grows when, and what bites when — the data the game already has."""
        from ..game.fishing import SPECIES
        from ..world.daynight import SEASONS
        left = ["КУЛЬТУРЫ", ""]
        for key in CROP_ORDER:
            crop = CROPS[key]
            seasons = ", ".join(SEASONS[s] for s in crop.seasons) or "круглый год"
            # Both times are integrated from the growth maths the farm runs,
            # not read off crop.grow_days: that field is the rate parameter
            # and is only reached by a bed held at full food.
            plain = days_to_ripe(crop)
            fed = days_to_ripe(crop, fertilised=True)
            left.append(f"  {crop.name} · {crop.sell_price} мон. · "
                        f"семена {crop.seed_price} мон.")
            left.append(f"      {seasons} · урожай {crop.yield_count}")
            left.append(f"      растёт {plain:.1f} дн. · "
                        f"с удобрением {fed:.1f}")
            left.append("")
        right = ["РЫБА", ""]
        for sp in SPECIES:
            if sp.key == "boot":
                continue
            if sp.hours:
                when = f"клюёт {sp.hours[0]:.0f}:00–{sp.hours[1]:.0f}:00"
            else:
                when = "клюёт в любое время"
            seasons = ", ".join(SEASONS[s] for s in sp.seasons) or "круглый год"
            mark = MARK if self.state.fish_log.get(sp.key) else " "
            right.append(f" [{mark}] {sp.name} — {sp.price} мон./кг")
            right.append(f"      {sp.size[0]:.1f}–{sp.size[1]:.1f} кг · {seasons}")
            right.append(f"      {when} · подсечек {sp.pulls}")
        return left, right

    def _journal_stats(self):
        """Labels and values as separate columns: this font is not monospaced,
        so padding with spaces would not line the numbers up."""
        from ..game.fishing import BY_KEY
        st = self.state
        cycle = self.base.cycle
        rows = [
            ("День", f"{cycle.day + 1} ({cycle.season_name})"),
            ("За игрой", f"{int(st.play_time // 60)} мин"),
            ("Монет сейчас", f"{st.coins}"),
            ("Заработано всего", f"{st.total_earned}"),
            ("", ""),
            ("Собрано урожая", f"{sum(self.base.farm.harvest_log.values())}"),
            ("Приготовлено блюд", f"{sum(st.cooked.values())}"),
            ("Поймано рыбы", "{} ({:.1f} кг)".format(
                sum(c for c, _k in st.fish_log.values()),
                sum(k for _c, k in st.fish_log.values()))),
        ]
        if st.best_fish:
            key, size = st.best_fish
            name = BY_KEY[key].name if key in BY_KEY else key
            rows.append(("Лучший улов", f"{name}, {size:.1f} кг"))
        rows.append(("", ""))
        rows.append(("Достижений",
                     f"{len(st.achievements)} из {len(ACHIEVEMENTS)}"))
        rows.append(("Заданий выполнено",
                     f"{sum(1 for q in st.quests if q.done)} из {len(st.quests)}"))
        left = ["СТАТИСТИКА", ""] + [f"  {label}:" if label else "" for label, _ in rows]
        right = ["", ""] + [value for _, value in rows]
        return left, right

    def _pause_controls(self):
        return ["УПРАВЛЕНИЕ", "",
                "  WASD — движение,  Shift — бег",
                "  Space — прыжок,  мышь — осмотреться",
                "  ЛКМ / E — действие инструментом",
                "  ПКМ — удобрить грядку",
                "  1..5 — инструменты",
                "  Q или колесо — выбор семян",
                "  T — лавка,  K — котёл",
                "  J — журнал,  Tab — карта",
                "  O — настройки и клавиши",
                "  F — продать всё у прилавка",
                "  F5 / F9 — сохранить / загрузить",
                "  P — фоторежим,  F1 — интерфейс",
                "  M — звук,  - / = — громкость"]

    def _pause_bag(self):
        st = self.state
        lines = ["В СУМКЕ", ""]
        have = [f"  {CROPS[k].name}: {st.count(k)}"
                for k in CROP_ORDER if st.count(k)]
        lines += have or ["  (пусто)"]
        seeds = [f"  Семена «{CROPS[k].name}»: {st.count(f'seed_{k}')}"
                 for k in CROP_ORDER if st.count(f"seed_{k}")]
        lines += [""] + (seeds or ["  Семян нет"])
        lines += ["", f"  Рыба: {st.fish}", f"  Монеты: {st.coins}"]
        audio = getattr(self.base, "audio", None)
        if audio is not None and audio.enabled:
            lines += ["", "ЗВУК", "",
                      f"  Громкость: {audio.master * 100:.0f}%",
                      f"  Музыка: {audio.music_volume * 100:.0f}%"]
            if not audio.music:
                lines.append("  (музыка ещё генерируется…)")
        return lines

    # Two rows of three. Six buttons across one row left every label spilling
    # over its own frame and into the next button.
    PAUSE_COLS = 3
    PAUSE_HALF_W = 0.32
    PAUSE_GAP = 0.02

    def _build_pause_buttons(self):
        """Pause needs a way out that is not just Esc."""
        from direct.gui.DirectGui import DirectButton
        app = self.base
        tut = getattr(app, "tutorial", None)
        entries = [
            ("Продолжить", app.on_escape),
            (f"Сохранить (слот {app.save_slot})", app.cycle_save_slot),
            ("Настройки", app.toggle_options),
        ]
        # A button that cannot do anything is worse than no button: drop the
        # skip once the tutorial is over or already switched off.
        if tut is not None and tut.active and not tut.finished:
            entries.append(("Пропустить обучение", app.skip_tutorial))
        entries += [
            ("В главное меню", app.open_main_menu),
            ("Выход из игры", app.userExit),
        ]
        pitch = self.PAUSE_HALF_W * 2.0 + self.PAUSE_GAP
        rows = [entries[i:i + self.PAUSE_COLS]
                for i in range(0, len(entries), self.PAUSE_COLS)]
        placed = []
        for row, group in enumerate(rows):
            # A short last row is centred on its own, not left at the edge.
            left = -pitch * (len(group) - 1) / 2.0
            for col, (label, cmd) in enumerate(group):
                placed.append((left + col * pitch, -0.475 - row * 0.115,
                               label, cmd))
        for x, y, label, cmd in placed:
            b = DirectButton(
                parent=self.panel, text=label, text_font=self.font,
                text_fg=INK, text_scale=0.033, text_pos=(0, -0.011),
                frameColor=((0.12, 0.14, 0.12, 0.9), (0.26, 0.32, 0.18, 0.95),
                            (0.34, 0.42, 0.22, 1.0), (0.1, 0.1, 0.1, 0.6)),
                frameSize=(-self.PAUSE_HALF_W, self.PAUSE_HALF_W, -0.043, 0.053),
                relief=1, pos=(x, 0, y), command=cmd)
            b.setTransparency(TransparencyAttrib.MAlpha)
            self.panel_buttons.append(b)

    def refresh_panel(self):
        # Every panel shares these two text nodes, and the journal resizes them,
        # so put them back to the default before rebuilding anything.
        self.panel_body.setScale(0.047)
        self.panel_body.setPos(-0.95, 0.44)
        self.panel_body2.hide()
        if self.panel_mode == "shop":
            # Prices go in their own column. Padding names to a fixed width
            # only lines anything up in a monospaced font, and this one is not:
            # every price in the shop started at a different x.
            self.panel_title.setText("Лавка")
            names, prices = [], []
            for i, (key, name, price, desc) in enumerate(shop_entries(self.state.upgrades)):
                owned = ("  [куплено]" if key == "lantern_oil"
                         and self.state.upgrades.lantern_oil else "")
                cursor = ">" if i == self.shop_index else " "
                names.append(f"{cursor} {name}")
                prices.append(f"{price} мон.{owned}")
                if i == self.shop_index:
                    names.append(f"    {desc}")
                    prices.append("")          # keep the columns in step
            self.panel_body.setText("\n".join(names))
            self.panel_body2.setPos(-0.20, 0.44)
            self.panel_body2.setText("\n".join(prices))
            self.panel_body2.show()
            self.panel_hint.setText(
                f"Монет: {self.state.coins}    "
                "↑/↓ выбор   Enter купить   F продать всё   Esc выход")
        elif self.panel_mode == "kitchen":
            from ..game.cooking import RECIPES, item_name
            kitchen = self.base.kitchen
            self.panel_title.setText("Котёл")
            lines, prices = [], []
            for i, r in enumerate(RECIPES):
                cursor = ">" if i == kitchen.index else " "
                parts = "  ".join(f"{item_name(k)} x{v}" for k, v in r.inputs.items())
                have = self.state.count(r.key)
                stock = f"   (в сумке: {have})" if have else ""
                lines.append(f"{cursor} {r.name}")
                prices.append(f"{r.sell_price} мон.{stock}")
                lines.append(f"    {parts}")
                prices.append("")
                if i == kitchen.index:
                    missing = kitchen.missing(r)
                    if missing:
                        short = ", ".join(f"{item_name(k)} x{v}"
                                          for k, v in missing.items())
                        lines.append(f"    не хватает: {short}")
                    else:
                        lines.append(f"    можно готовить  ·  +{r.stamina:.0f} сил")
                    prices.append("")
                lines.append("")
                prices.append("")
            self.panel_body.setText("\n".join(lines))
            self.panel_body2.setPos(-0.20, 0.44)
            self.panel_body2.setText("\n".join(prices))
            self.panel_body2.show()
            self.panel_hint.setText(
                "↑/↓ выбор   Enter приготовить   F съесть   K или Esc выход")
        elif self.panel_mode == "journal":
            page = JOURNAL_PAGES[self.journal_page]
            self.panel_title.setText(f"Журнал — {page}")
            builder = (self._journal_quests, self._journal_almanac,
                       self._journal_stats)[self.journal_page]
            left, right = builder()
            stats = self.journal_page == 2
            scale = 0.045 if stats else 0.036   # statistics is a short page
            split = -0.30 if stats else 0.04
            self.panel_body.setScale(scale)
            self.panel_body.setPos(-0.95, 0.50)
            self.panel_body.setText("\n".join(left))
            self.panel_body2.setScale(scale)
            self.panel_body2.setPos(split, 0.50)
            self.panel_body2.setText("\n".join(right))
            self.panel_body2.show()
            self.panel_hint.setText("←→ — раздел · J или Esc — закрыть")
        elif self.panel_mode == "pause":
            # Two columns, and both must stop well above the buttons: as one
            # list this ran straight underneath them and the bag was unreadable.
            self.panel_title.setText("Пауза")
            self.panel_body.setScale(0.036)
            self.panel_body.setPos(-0.98, 0.50)
            self.panel_body.setText("\n".join(self._pause_controls()))
            self.panel_body2.setScale(0.036)
            self.panel_body2.setPos(0.10, 0.50)
            self.panel_body2.setText("\n".join(self._pause_bag()))
            self.panel_body2.show()
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
        # Four of the ten hints wrap to two lines, and the second line used to
        # hang below the panel over the scenery. Grow the frame to the text.
        rows = self.tutor_hint.textNode.getNumRows()
        bottom = -0.122 - rows * 0.036 * 1.25 + 0.010
        self.tutor_panel["frameSize"] = (-0.02, 0.86, bottom, 0.055)

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
            else:
                # Which tier you are holding. Buying a 520-coin hoe changed
                # nothing you could see on the bar it sits in. Roman numerals
                # rather than stars: the fallback fonts do not all carry the
                # dingbats, and a missing glyph draws an empty box.
                tier = getattr(state.upgrades, key, 1)
                if tier > 1:
                    label += " " + ("II" if tier == 2 else "III")
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

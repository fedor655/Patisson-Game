"""Патиссон гейм на телефоне — вид сверху на общую ферму.

    python -m patisson2.mobile.main 31.76.72.214:7777 Имя

The phone cannot run the desktop renderer: that pipeline wants OpenGL
4.3, compute shaders and a hundred and seventy thousand blades of grass.
It does not have to. The farm is simulated on the server, so a phone only
needs to draw what it is told and pass touches back — which is a plan
view of the beds, a toolbar and a status line.

Everything here is Kivy and the standard library. Nothing imports the
game engine, so this is the piece that can actually become an APK.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

try:                                    # inside the game's package
    from .link import DEFAULT_PORT, FarmLink
except ImportError:                     # packaged flat for a phone
    from link import DEFAULT_PORT, FarmLink

# Tool -> what tapping a bed means, and what the button says.
TOOLS = [
    ("can", "Лейка", "water"),
    ("hoe", "Мотыга", "weed"),
    ("seeds", "Семена", "plant"),
    ("basket", "Корзина", "harvest"),
    ("fert", "Удобрить", "feed"),
]
CROPS = ["patisson", "carrot", "tomato", "wheat", "pumpkin",
         "turnip"]
CROP_NAMES = {"patisson": "Патиссон", "carrot": "Морковь", "tomato": "Томат",
              "wheat": "Пшеница", "pumpkin": "Тыква",
              "turnip": "Репа"}
SEASONS = ["Весна", "Лето", "Осень", "Зима"]
# Сколько ждать перед новой попыткой дозвониться.
RETRY_SECONDS = 5.0
WEATHER = {"clear": "Ясно", "cloudy": "Облачно", "rain": "Дождь",
           "snow": "Снег"}


def _settings_path() -> str:
    """Куда класть адрес фермы, чтобы не набирать его каждый раз."""
    base = os.environ.get("ANDROID_PRIVATE") or os.path.expanduser("~")
    return os.path.join(base, "patisson-phone.json")


def load_settings() -> dict:
    try:
        with open(_settings_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:                       # noqa: BLE001
        return {}


def save_settings(data: dict) -> None:
    try:
        with open(_settings_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:                       # noqa: BLE001
        pass                                # не за что тут падать


class FarmView(Widget):
    """The beds, seen from above, with a finger for a cursor."""

    def __init__(self, link: FarmLink, **kwargs):
        super().__init__(**kwargs)
        self.link = link
        self.tool = 0
        self.crop = 0
        self._name_textures: dict = {}
        self.bind(pos=lambda *_a: self.redraw(),
                  size=lambda *_a: self.redraw())

    # --- mapping the farm onto the screen -----------------------------

    def _transform(self):
        """Fit every bed on screen with room to spare, keeping it square."""
        layout = self.link.layout
        if not layout:
            return None
        xs = [p[0] for p in layout]
        ys = [p[1] for p in layout]
        span_x = max(max(xs) - min(xs), 1.0)
        span_y = max(max(ys) - min(ys), 1.0)
        pad = 0.16
        scale = min(self.width * (1 - pad) / (span_x + 2.0),
                    self.height * (1 - pad) / (span_y + 2.0))
        cx = (max(xs) + min(xs)) / 2.0
        cy = (max(ys) + min(ys)) / 2.0
        return scale, cx, cy

    def to_screen(self, wx: float, wy: float):
        t = self._transform()
        if t is None:
            return self.center_x, self.center_y
        scale, cx, cy = t
        return (self.center_x + (wx - cx) * scale,
                self.center_y + (wy - cy) * scale)

    def bed_at(self, sx: float, sy: float):
        """Which bed the finger landed on, if any."""
        t = self._transform()
        if t is None:
            return None
        scale = t[0]
        reach = max(scale * 0.75, 24.0)
        best, best_d = None, reach * reach
        for index, (wx, wy, _wz) in enumerate(self.link.layout):
            px, py = self.to_screen(wx, wy)
            d = (px - sx) ** 2 + (py - sy) ** 2
            if d < best_d:
                best, best_d = index, d
        return best

    # --- drawing -------------------------------------------------------

    def redraw(self, *_args):
        self.canvas.clear()
        t = self._transform()
        with self.canvas:
            Color(0.29, 0.42, 0.22)
            Rectangle(pos=self.pos, size=self.size)
            if t is None:
                return
            scale = t[0]
            size = max(scale * 1.35, 18.0)
            for index, (wx, wy, _wz) in enumerate(self.link.layout):
                px, py = self.to_screen(wx, wy)
                plot = self.link.plots.get(index, {})
                self._draw_bed(px, py, size, plot)
            for entry in self.link.players:
                pos = entry.get("p") or [0, 0, 0]
                px, py = self.to_screen(pos[0], pos[1])
                mine = entry.get("id") == self.link.player_id
                Color(1.0, 0.86, 0.35) if mine else Color(0.55, 0.75, 1.0)
                Ellipse(pos=(px - 9, py - 9), size=(18, 18))
                if not mine:
                    self._draw_name(px, py, entry.get("name", "?"))

    def _draw_name(self, px, py, name):
        """Кто это стоит на грядках. Точка без имени ничего не говорит."""
        tex = self._name_textures.get(name)
        if tex is None:
            label = CoreLabel(text=str(name)[:14], font_size=13)
            label.refresh()
            tex = label.texture
            self._name_textures[name] = tex
        Color(1, 1, 1, 0.92)
        Rectangle(texture=tex, pos=(px - tex.width / 2, py + 11),
                  size=tex.size)

    def _draw_bed(self, px, py, size, plot):
        half = size / 2.0
        Color(0.33, 0.23, 0.15)                       # soil
        Rectangle(pos=(px - half, py - half), size=(size, size))
        crop = plot.get("crop")
        if crop:
            progress = min(max(plot.get("pr", 0.0), 0.0), 1.0)
            health = plot.get("hp", 1.0)
            if progress >= 1.0:
                Color(1.0, 0.92, 0.45)                # ripe
            else:
                Color(0.35 + 0.25 * (1 - health), 0.55 + 0.3 * progress, 0.28)
            grow = size * (0.28 + 0.52 * progress)
            Ellipse(pos=(px - grow / 2, py - grow / 2), size=(grow, grow))
        if plot.get("wd", 0.0) >= 0.3:                # weeds
            Color(0.20, 0.45, 0.12)
            Line(points=[px - half + 3, py - half + 3,
                         px + half - 3, py + half - 3], width=1.4)
        if plot.get("bl", 0.0) >= 0.05:               # blight
            Color(0.45, 0.20, 0.35)
            Line(rectangle=(px - half, py - half, size, size), width=1.6)
        if plot.get("w", 1.0) < 0.25 and crop:        # thirsty
            Color(0.85, 0.55, 0.20)
            Line(circle=(px, py, half * 0.85), width=1.3)

    # --- touching ------------------------------------------------------

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        index = self.bed_at(*touch.pos)
        if index is None:
            return True
        _key, _label, action = TOOLS[self.tool]
        if action == "plant":
            self.link.act("plant", index, CROPS[self.crop])
        else:
            self.link.act(action, index)
        return True


class PatissonMobile(App):
    title = "Патиссон гейм"

    def __init__(self, host: str = "", port: int = DEFAULT_PORT,
                 name: str = "Телефон", **kwargs):
        super().__init__(**kwargs)
        self.link = None
        self._retry_in = RETRY_SECONDS
        saved = load_settings()
        self.host = host or saved.get("host", "")
        self.port = port or int(saved.get("port", DEFAULT_PORT))
        self.player_name = name if name != "Телефон" else saved.get("name",
                                                             "Телефон")

    def build(self):
        """Сперва спросить, к какой ферме идём."""
        Window.clearcolor = (0.08, 0.09, 0.07, 1)
        self.screen = BoxLayout(orientation="vertical")
        self._show_setup()
        return self.screen

    # --- экран подключения -------------------------------------------

    def _show_setup(self, message: str = ""):
        """Адрес фермы спрашивается здесь, и только здесь.

        Раньше он брался из аргументов командной строки. На телефоне
        их нет: приложение всегда стучалось в 127.0.0.1, где ничего
        нет и быть не может, — то есть подключиться к ферме с
        телефона было нельзя вообще никак.
        """
        self.screen.clear_widgets()
        self.screen.add_widget(Label(text="Патиссон гейм", font_size=30,
                                     size_hint=(1, None), height=90,
                                     color=(1.0, 0.85, 0.42, 1)))
        self.screen.add_widget(Label(
            text=message or "Адрес фермы и ваше имя",
            font_size=15, size_hint=(1, None), height=64,
            color=((1.0, 0.6, 0.5, 1) if message else (0.8, 0.82, 0.8, 1))))
        self.host_input = TextInput(
            text=f"{self.host}:{self.port}" if self.host else "",
            hint_text="адрес:порт", multiline=False, font_size=20,
            size_hint=(1, None), height=64)
        self.screen.add_widget(self.host_input)
        self.player_name_input = TextInput(text=self.player_name, hint_text="имя",
                                    multiline=False, font_size=20,
                                    size_hint=(1, None), height=64)
        self.screen.add_widget(self.player_name_input)
        go = Button(text="На ферму", font_size=22,
                    size_hint=(1, None), height=72)
        go.bind(on_release=lambda _b: self._connect())
        self.screen.add_widget(go)
        self.screen.add_widget(Widget())        # пустое место снизу

    def _connect(self):
        address = (self.host_input.text or "").strip()
        if not address:
            self._show_setup("Впишите адрес фермы")
            return
        host, _, port = address.rpartition(":")
        if not host:
            host, port = address, str(DEFAULT_PORT)
        try:
            self.port = int(port or DEFAULT_PORT)
        except ValueError:
            self._show_setup(f"Порт «{port}» не число")
            return
        self.host = host
        self.player_name = (self.player_name_input.text or "Телефон").strip()
        save_settings({"host": self.host, "port": self.port,
                       "name": self.player_name})
        self.link = FarmLink(self.host, self.port, self.player_name)
        self._retry_in = RETRY_SECONDS
        self.screen.clear_widgets()
        self.screen.add_widget(self._build_farm())
        Clock.schedule_interval(self.tick, 1.0 / 20.0)

    # --- экран фермы ---------------------------------------------------

    def _build_farm(self):
        Window.clearcolor = (0.08, 0.09, 0.07, 1)
        root = BoxLayout(orientation="vertical")
        # Paint the frame ourselves rather than leaning on the window's
        # clear colour: on a phone the app may be composited over
        # anything, and pale text on an unknown background is a
        # coin toss.
        with root.canvas.before:
            Color(0.08, 0.09, 0.07)
            self._backdrop = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._fit_backdrop, size=self._fit_backdrop)

        self.status = Label(text="Подключаюсь…", size_hint=(1, None),
                            height=44, font_size=17)
        root.add_widget(self.status)

        self.view = FarmView(self.link)
        root.add_widget(self.view)

        self.news = Label(text="", size_hint=(1, None), height=34,
                          font_size=14, color=(0.85, 0.9, 0.8, 1))
        root.add_widget(self.news)

        # Что лежит в общем амбаре. Без этого «Удобрить» и «Семена»
        # были кнопками, которые иногда молча ничего не делают: ферма
        # отказывает, когда класть в землю нечего, и сказать об этом
        # некому.
        self.barn = Label(text="", size_hint=(1, None), height=30,
                          font_size=14, color=(0.75, 0.78, 0.72, 1))
        root.add_widget(self.barn)

        # Два ряда: чем работать по грядке, и что делать со всей фермой.
        tools_bar = BoxLayout(size_hint=(1, None), height=58, spacing=3,
                              padding=3)
        self.tool_buttons = []
        for index, (_key, label, _action) in enumerate(TOOLS):
            btn = Button(text=label, font_size=15)
            btn.bind(on_release=lambda _b, i=index: self.pick_tool(i))
            tools_bar.add_widget(btn)
            self.tool_buttons.append(btn)
        root.add_widget(tools_bar)

        farm_bar = BoxLayout(size_hint=(1, None), height=58, spacing=3,
                             padding=3)
        self.crop_button = Button(text="Патиссон", font_size=15)
        self.crop_button.bind(on_release=lambda _b: self.next_crop())
        farm_bar.add_widget(self.crop_button)
        sell = Button(text="Продать", font_size=15)
        sell.bind(on_release=lambda _b: self.link.act("sell"))
        farm_bar.add_widget(sell)
        # Разваленное пугало — это вороны на каждой спелой грядке, и
        # починить его должен уметь тот, кто рядом, хоть с телефона.
        scare = Button(text="Пугало", font_size=15)
        scare.bind(on_release=lambda _b: self.link.act("repair"))
        farm_bar.add_widget(scare)
        self.scare_button = scare
        root.add_widget(farm_bar)
        self.pick_tool(0)
        return root

    def _fit_backdrop(self, widget, _value):
        self._backdrop.pos = widget.pos
        self._backdrop.size = widget.size

    def pick_tool(self, index: int):
        self.view.tool = index
        for i, btn in enumerate(self.tool_buttons):
            btn.background_color = ((1.0, 0.85, 0.4, 1) if i == index
                                    else (1, 1, 1, 1))

    def next_crop(self):
        self.view.crop = (self.view.crop + 1) % len(CROPS)
        self._refresh_barn()

    def _refresh_barn(self):
        """Семена выбранной культуры, удобрение, зола и пугало."""
        stock = self.link.inventory
        crop = CROPS[self.view.crop]
        seeds = int(stock.get("seed_" + crop, 0))
        self.crop_button.text = f"{CROP_NAMES[crop]} x{seeds}"
        self.crop_button.color = ((1, 1, 1, 1) if seeds
                                  else (1.0, 0.6, 0.5, 1))
        self.barn.text = (f"Амбар: удобрение {int(stock.get('fertilizer', 0))}"
                          f"   зола {int(stock.get('ash', 0))}"
                          f"   пугало {self.link.scarecrow * 100:.0f}%")
        # Три состояния, и все три решает ферма: чинить нечего,
        # потрёпано, или вороны уже не боятся.
        if not self.link.crow_ok:
            self.scare_button.text = "Пугало упало"
            self.scare_button.color = (1.0, 0.55, 0.45, 1)
        elif self.link.crow_fix:
            self.scare_button.text = "Пугало потрёпано"
            self.scare_button.color = (1.0, 0.87, 0.5, 1)
        else:
            self.scare_button.text = "Пугало цело"
            self.scare_button.color = (1, 1, 1, 1)

    def reconnect(self):
        """Свежая попытка дозвониться до той же фермы."""
        self._retry_in = RETRY_SECONDS
        old = self.link
        self.link = FarmLink(old.host, old.port, old.name)
        self.view.link = self.link
        old.close()

    def tick(self, _dt):
        fresh = self.link.pump()
        if self.link.status == "failed":
            # Телефон теряет сеть постоянно — в лифте, в метро, на даче.
            # Замереть с пустым экраном хуже, чем сказать, что случилось,
            # и попробовать вернуться самому.
            self._retry_in -= _dt
            left = max(0, int(self._retry_in) + 1)
            self.status.text = (f"{self.link.error or 'Связь потеряна'} — "
                                f"пробую снова через {left} с")
            if self._retry_in <= 0.0:
                self.reconnect()
            return
        self._retry_in = RETRY_SECONDS
        if self.link.status != "online":
            return
        clock = self.link.clock
        hour = clock.get("hour", 0.0)
        season = SEASONS[int(clock.get("season", 0)) % 4]
        weather = WEATHER.get(clock.get("weather", "clear"), "")
        self.status.text = (f"{int(hour):02d}:{int(hour % 1 * 60):02d}  "
                            f"День {clock.get('day', 0) + 1}  {season}  "
                            f"{weather}   {self.link.coins} мон.")
        if fresh:
            self.news.text = fresh[-1]
        self._refresh_barn()
        self.view.redraw()

    def on_stop(self):
        self.link.close()


def main(argv=None):
    """Запуск. Адрес можно передать строкой, но телефон спросит сам."""
    argv = list(sys.argv[1:] if argv is None else argv)
    host, port, name = "", DEFAULT_PORT, "Телефон"
    if argv:
        host, _, tail = argv[0].rpartition(":")
        if not host:
            host, tail = argv[0], ""
        port = int(tail or DEFAULT_PORT)
    if len(argv) > 1:
        name = argv[1]
    try:
        PatissonMobile(host, port, name).run()
    except Exception:                       # noqa: BLE001
        # На телефоне нет консоли: без этого приложение просто
        # исчезает после заставки, и почему — не узнать никак.
        _show_crash(traceback.format_exc())


def _show_crash(text: str) -> None:
    try:
        with open(_settings_path() + ".crash", "w", encoding="utf-8") as fh:
            fh.write(text)
    except Exception:                       # noqa: BLE001
        pass
    try:
        from kivy.app import App as _App

        class Crash(_App):
            def build(self):
                return Label(text=text[-1500:], font_size=13,
                             color=(1.0, 0.6, 0.5, 1))

        Crash().run()
    except Exception:                       # noqa: BLE001
        sys.stderr.write(text)


if __name__ == "__main__":
    main()

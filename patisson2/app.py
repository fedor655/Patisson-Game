"""Patisson 2.0 — application entry point and game loop."""

from __future__ import annotations

import math
import random
import sys

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    ClockObject,
    Vec3,
    Vec4,
    WindowProperties,
    loadPrcFileData,
)

from .config import Config
from .engine.pipeline import RenderPipeline
from .game.farming import CROPS, CROP_ORDER, Farm
from .game.npc import Villagers
from .game.player import Player
from .game.state import GameState, SHOP_ITEMS, load_game, save_game
from .ui.hud import HUD
from .world.daynight import DayNightCycle
from .world.props import Props, plot_positions
from .world.world import World

WEATHER_LABELS = {
    "clear": "Ясно",
    "cloudy": "Облачно",
    "rain": "Дождь",
    "snow": "Снег",
}


def configure(cfg: Config, offscreen: bool = False):
    """PRC settings. These must be set before ShowBase is constructed."""
    g = cfg.graphics
    loadPrcFileData("", f"win-size {g.width} {g.height}")
    loadPrcFileData("", "window-title Patisson 2.0")
    loadPrcFileData("", "framebuffer-multisample 0")
    loadPrcFileData("", f"sync-video {'#t' if g.vsync else '#f'}")
    # Render targets must keep their exact size or every post pass samples the
    # wrong region of the screen.
    loadPrcFileData("", "textures-power-2 none")
    loadPrcFileData("", "gl-coordinate-system default")
    loadPrcFileData("", "notify-level-glgsg warning")
    loadPrcFileData("", "audio-library-name null")
    if g.fullscreen and not offscreen:
        loadPrcFileData("", "fullscreen #t")
    if offscreen:
        loadPrcFileData("", "window-type offscreen")


class PatissonApp(ShowBase):
    def __init__(self, cfg: Config | None = None, offscreen: bool = False):
        self.cfg = cfg or Config()
        super().__init__()
        self.offscreen = offscreen
        self.disableMouse()
        self.setBackgroundColor(0, 0, 0, 1)
        globalClock = ClockObject.getGlobalClock()
        globalClock.setMaxDt(0.10)

        g = self.cfg.graphics
        self.camLens.setFov(74)
        self.camLens.setNearFar(0.12, g.view_distance)

        self.pipeline = RenderPipeline(self, g)
        self.world = World(self, self.pipeline, self.cfg.world, g)
        self.props = Props(self, self.world, self.pipeline)
        self.farm = Farm(self, self.world, self.props, self.cfg.game.day_length)
        self.villagers = Villagers(self, self.world, self.props)
        self.cycle = DayNightCycle(self.cfg.game.day_length,
                                   self.cfg.game.start_hour,
                                   self.cfg.game.season_days)
        self.state = GameState(self.cfg.game)
        self.state.stamina_frac = 1.0
        self.player = Player(self, self.world, self.cfg.game, start=(2.0, -9.0))
        self.hud = HUD(self, self.state, self.cfg)

        for x, y in plot_positions():
            self.farm.add_plot(x, y)

        self.weather = "clear"
        self.weather_timer = 40.0
        self.rng = random.Random(self.cfg.world.seed ^ 0x5EED)

        self.keys = {}
        self.paused = False
        self.fishing = None            # (state, timer)
        self.photo_mode = False
        self._setup_input()
        self._grab_mouse(True)

        self.taskMgr.add(self.update, "game-update")
        self.state.notify("Ферма ждёт. Возьмите мотыгу (1) и вскопайте грядку.", 8.0)

    # ------------------------------------------------------------------ input

    def _setup_input(self):
        binds = {
            "w": "forward", "s": "back", "a": "left", "d": "right",
            "space": "jump", "shift": "sprint",
            "arrow_up": "forward", "arrow_down": "back",
            "arrow_left": "left", "arrow_right": "right",
        }
        for key, action in binds.items():
            self.accept(key, self._set_key, [action, True])
            self.accept(f"{key}-up", self._set_key, [action, False])

        self.accept("escape", self.on_escape)
        self.accept("e", self.on_interact)
        self.accept("mouse1", self.on_interact)
        self.accept("mouse3", self.on_secondary)
        self.accept("t", self.toggle_shop)
        self.accept("j", self.toggle_journal)
        self.accept("q", self.state.cycle_seed, [1])
        self.accept("wheel_up", self.on_wheel, [-1])
        self.accept("wheel_down", self.on_wheel, [1])
        self.accept("f", self.on_sell)
        self.accept("f1", self.hud.toggle)
        self.accept("f5", self.on_save)
        self.accept("f9", self.on_load)
        self.accept("p", self.toggle_photo_mode)
        self.accept("enter", self.on_confirm)
        for i in range(1, 6):
            self.accept(str(i), self.select_tool, [i - 1])

    def _set_key(self, action, value):
        self.keys[action] = value

    def _grab_mouse(self, grab: bool):
        self.mouse_grabbed = grab and not self.offscreen
        # Offscreen captures render into a GraphicsBuffer, which has no window
        # properties to set.
        if hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(self.mouse_grabbed)
            self.win.requestProperties(props)
        self.player.locked = not grab

    # --------------------------------------------------------------- commands

    def select_tool(self, index: int):
        from .game.state import TOOLS
        self.state.tool_index = max(0, min(len(TOOLS) - 1, index))

    def on_wheel(self, delta: int):
        if self.hud.panel_mode == "shop":
            self.hud.move_shop_cursor(delta)
        else:
            self.state.cycle_seed(delta)

    def on_escape(self):
        if self.hud.dialogue:
            self.hud.hide_dialogue()
            return
        if self.hud.panel_mode:
            self.hud.close_panel()
            self.paused = False
            self._grab_mouse(True)
            return
        self.paused = True
        self.hud.open_panel("pause")
        self._grab_mouse(False)

    def toggle_shop(self):
        if self.hud.panel_mode == "shop":
            self.hud.close_panel()
            self.paused = False
            self._grab_mouse(True)
        elif self.hud.panel_mode is None:
            self.hud.open_panel("shop")
            self.paused = True
            self._grab_mouse(False)

    def toggle_journal(self):
        if self.hud.panel_mode == "journal":
            self.hud.close_panel()
            self.paused = False
            self._grab_mouse(True)
        elif self.hud.panel_mode is None:
            self.hud.open_panel("journal")
            self.paused = True
            self._grab_mouse(False)

    def on_confirm(self):
        if self.hud.panel_mode == "shop":
            self.state.buy(self.hud.shop_key)
            self.hud.refresh_panel()

    def on_save(self):
        path = save_game(self.state, self.farm, self.cycle, self.player)
        self.state.notify(f"Сохранено: {path.name}")

    def on_load(self):
        if load_game(self.state, self.farm, self.cycle, self.player):
            self.state.notify("Игра загружена")
        else:
            self.state.notify("Сохранение не найдено")

    def on_sell(self):
        if self._near_stall():
            self.state.sell_all()
        else:
            self.state.notify("Продавать можно у прилавка")

    def toggle_photo_mode(self):
        tracer = getattr(self, "pathtracer", None)
        if tracer is None:
            from .engine.pathtracer import PathTracer
            try:
                self.pathtracer = PathTracer(self, self.cfg.graphics)
            except Exception as exc:      # driver or capability problem
                self.state.notify(f"Фоторежим недоступен: {exc}")
                self.pathtracer = False
                return
            tracer = self.pathtracer
        if tracer is False:
            self.state.notify("Фоторежим недоступен на этой системе")
            return
        self.photo_mode = not self.photo_mode
        if self.photo_mode:
            tracer.begin(self.player, self.cycle.state())
            self.state.notify("Фоторежим: трассировка лучей…", 5.0)
        else:
            tracer.end()

    # ----------------------------------------------------------- interaction

    def _near_stall(self) -> bool:
        from .world.props import LAYOUT
        sx, sy, _h = LAYOUT["market_stall"]
        return (self.player.pos.x - sx) ** 2 + (self.player.pos.y - sy) ** 2 < 16.0

    def _near_well(self) -> bool:
        from .world.props import LAYOUT
        wx, wy, _h = LAYOUT["well"]
        return (self.player.pos.x - wx) ** 2 + (self.player.pos.y - wy) ** 2 < 9.0

    def _near_water(self) -> bool:
        p = self.player.pos
        for dist in (1.5, 2.5, 3.5):
            d = self.player.look_dir()
            x, y = p.x + d.x * dist, p.y + d.y * dist
            if self.world.height_at(x, y) < self.cfg.world.water_level:
                return True
        return False

    def _aim_plot(self):
        aim = self.player.ground_aim()
        target = aim if aim is not None else self.player.aim_point(1.8)
        return self.farm.nearest(target, 1.1), target

    def context(self):
        """What pressing E would do right now: (prompt, tip)."""
        st = self.state
        npc = self.villagers.nearest(self.player.pos, 2.8)
        if npc is not None:
            return f"[E] Поговорить — {npc.name}", npc.activity
        if self.fishing:
            phase = self.fishing[0]
            if phase == "bite":
                return "[E] Подсекай!", ""
            return "Ждём поклёвки…", "[E] отменить"
        tool = st.tool
        plot, _ = self._aim_plot()
        if tool == "hoe":
            if plot is not None and plot.crop is None and plot.tilled:
                return "", "Грядка уже вскопана"
            return "[E] Вскопать грядку", "Смотрите на землю"
        if tool == "can":
            if self._near_well() or self._near_water():
                return "[E] Набрать воду", f"{st.water:.0f}/{st.upgrades.can_capacity:.0f}"
            if plot is not None and plot.crop is not None:
                if st.water < 1.0:
                    return "", "Лейка пуста — наберите у колодца"
                return "[E] Полить", f"Влага: {plot.water*100:.0f}%"
            return "", ""
        if tool == "seeds":
            crop = CROPS[st.seed_key]
            if plot is not None and plot.crop is None:
                if st.count(f"seed_{crop.key}") <= 0:
                    return "", f"Нет семян «{crop.name}» — купите в лавке (T)"
                return f"[E] Посадить: {crop.name}", "Q — другая культура"
            return "", f"Выбрано: {crop.name} (Q — сменить)"
        if tool == "rod":
            if self._near_water():
                return "[E] Забросить удочку", ""
            return "", "Нужен пруд"
        if tool == "basket":
            if self._near_stall():
                return "[F] Продать всё", f"{st.coins} монет"
            if plot is not None and plot.ripe:
                return f"[E] Собрать: {CROPS[plot.crop].name}", ""
            if plot is not None and plot.crop is not None:
                return "", f"Зреет: {plot.progress*100:.0f}%"
        return "", ""

    def on_interact(self):
        if self.paused or self.hud.panel_mode:
            return
        if self.hud.dialogue:
            self.hud.hide_dialogue()
            return
        st = self.state

        npc = self.villagers.nearest(self.player.pos, 2.8)
        if npc is not None:
            self.hud.show_dialogue(npc.name, npc.talk())
            return

        if self.fishing:
            self._fishing_input()
            return

        tool = st.tool
        plot, target = self._aim_plot()

        if tool == "hoe":
            if plot is None and target is not None:
                new = self.farm.till(target.x, target.y)
                if new is not None:
                    st.notify("Грядка вскопана")
                else:
                    st.notify("Здесь копать нельзя")
            elif plot is not None and plot.crop is not None and plot.health <= 0.02:
                self.farm.clear(plot)

        elif tool == "can":
            if self._near_well() or self._near_water():
                st.water = st.upgrades.can_capacity
                st.notify("Лейка полна")
            elif plot is not None and st.water >= 1.0:
                if self.farm.water_plot(plot):
                    st.water = max(0.0, st.water - 1.0)
                else:
                    st.notify("Грядка уже полита")
            elif plot is not None:
                st.notify("Лейка пуста")

        elif tool == "seeds":
            if plot is not None and plot.crop is None:
                key = st.seed_key
                if st.take(f"seed_{key}"):
                    self.farm.plant(plot, key)
                    st.unlock("first_seed")
                    st.notify(f"Посажено: {CROPS[key].name}")
                    growing = sum(1 for p in self.farm.plots if p.crop)
                    if growing >= 10:
                        st.unlock("green_thumb")
                else:
                    st.notify(f"Нет семян «{CROPS[key].name}»")

        elif tool == "rod":
            if self._near_water():
                delay = 1.4 if st.upgrades.enchanted_rod else 3.0
                self.fishing = ["wait", self.rng.uniform(delay * 0.6, delay * 1.6)]
            else:
                st.notify("Подойдите к воде")

        elif tool == "basket":
            if plot is not None and plot.ripe:
                result = self.farm.harvest(plot)
                if result:
                    key, count = result
                    st.give(key, count)
                    st.record("harvest", key, count)
                    st.unlock("first_harvest")
                    total_pat = self.farm.harvest_log.get("patisson", 0)
                    if total_pat >= 10:
                        st.unlock("patisson_lover")
                    if all(self.farm.harvest_log.get(k, 0) > 0 for k in CROP_ORDER):
                        st.unlock("all_crops")
                    st.notify(f"Собрано: {CROPS[key].name} x{count}")
            elif self._near_stall():
                st.sell_all()

    def on_secondary(self):
        """Right click: fertilise the plot under the cursor."""
        if self.paused or self.hud.panel_mode:
            return
        plot, _ = self._aim_plot()
        if plot is None or plot.crop is None:
            return
        if not self.state.take("fertilizer"):
            self.state.notify("Нет удобрения (купите в лавке)")
            return
        self.farm.feed_plot(plot)
        self.state.notify("Удобрено")

    def _fishing_input(self):
        phase = self.fishing[0]
        if phase == "bite":
            self.state.fish += 1
            self.state.total_fish += 1
            self.state.record("fish")
            self.state.notify("Поймана рыба!")
            if self.state.total_fish >= 20:
                self.state.unlock("angler")
            self.fishing = None
        else:
            self.fishing = None
            self.state.notify("Удочка смотана")

    def _update_fishing(self, dt: float):
        if not self.fishing:
            return
        self.fishing[1] -= dt
        if self.fishing[1] <= 0:
            if self.fishing[0] == "wait":
                self.fishing = ["bite", 1.35]
            else:
                self.state.notify("Рыба сорвалась…")
                self.fishing = None

    # ---------------------------------------------------------------- weather

    def _update_weather(self, dt: float):
        self.weather_timer -= dt
        if self.weather_timer > 0:
            return
        self.weather_timer = self.rng.uniform(70.0, 190.0)
        season = self.cycle.season
        if season == 3:
            choices, weights = ("clear", "cloudy", "snow"), (2, 3, 3)
        elif season == 2:
            choices, weights = ("clear", "cloudy", "rain"), (3, 3, 3)
        else:
            choices, weights = ("clear", "cloudy", "rain"), (5, 3, 2)
        self.weather = self.rng.choices(choices, weights=weights)[0]
        if self.weather == "rain":
            self.state.notify("Пошёл дождь — грядки польются сами")

    # ----------------------------------------------------------------- update

    def update(self, task):
        dt = min(ClockObject.getGlobalClock().getDt(), 0.10)
        st = self.state
        st.play_time += dt

        if not self.paused and self.mouse_grabbed:
            self._mouse_look()

        blocked = self.paused or self.hud.panel_mode is not None
        if not blocked:
            self.cycle.advance(dt)
            self._update_weather(dt)
            self._update_fishing(dt)
            events = self.farm.update(dt, self.cycle.season, self.weather == "rain")
            for e in events:
                st.notify(e)

        self.player.update(dt, self.keys, blocked=blocked)
        self.player.apply_to_camera(self.camera)
        st.stamina_frac = self.player.stamina / self.cfg.game.stamina_max

        sky = self.cycle.state()
        p = self.pipeline
        p.sun_dir = sky.sun_dir
        p.light_dir = sky.light_dir
        p.sun_color = sky.sun_color
        cover = sky.cloud_cover
        if self.weather in ("rain", "snow"):
            cover = min(0.92, cover + 0.35)
        elif self.weather == "cloudy":
            cover = min(0.85, cover + 0.18)
        p.cloud_cover = cover
        p.fog_tint = sky.fog_tint
        p.exposure_target = sky.exposure * (1.18 if self.weather == "rain" else 1.0)
        self.render.setShaderInput("u_ambientScale", sky.ambient_scale)

        night = 1.0 if sky.is_night else max(0.0, 1.0 - sky.sun_dir.z * 8.0)
        if st.upgrades.lantern_oil:
            night *= 1.7

        wind = Vec4(0.82, 0.57, 0.0,
                    0.75 if self.weather in ("rain", "snow") else 0.42)
        self.world.update(dt, self.player.pos, wind, self.cycle.total_time)
        self.world.apply_season(self.cycle.season)
        self.props.update(dt, self.cycle.total_time, night)
        self.villagers.update(dt if not blocked else 0.0, self.cycle.hour,
                              self.cycle.total_time)
        p.update(dt, self.player.eye, self.player.pos)

        if 23.5 <= self.cycle.hour or self.cycle.hour < 0.5:
            st.unlock("night_owl")
        if st.coins >= 1000:
            st.unlock("rich")

        st.update_notifications(dt)
        prompt, tip = self.context()
        self.hud.set_prompt(prompt, tip)
        self.hud.update(self.cycle, st, WEATHER_LABELS[self.weather])

        tracer = getattr(self, "pathtracer", None)
        if self.photo_mode and tracer:
            tracer.step(self.player, sky)

        return task.cont

    def _mouse_look(self):
        if not self.win.getProperties().getForeground():
            return
        pointer = self.win.getPointer(0)
        if not pointer.getInWindow():
            return
        cx = self.win.getXSize() // 2
        cy = self.win.getYSize() // 2
        x, y = pointer.getX(), pointer.getY()
        if self.win.movePointer(0, cx, cy):
            self.player.add_look(x - cx, y - cy)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = Config()
    if "--low" in argv:
        cfg.graphics = type(cfg.graphics).preset("low")
    elif "--ultra" in argv:
        cfg.graphics = type(cfg.graphics).preset("ultra")
    elif "--medium" in argv:
        cfg.graphics = type(cfg.graphics).preset("medium")
    if "--fullscreen" in argv:
        cfg.graphics.fullscreen = True
    configure(cfg)
    app = PatissonApp(cfg)
    app.run()


if __name__ == "__main__":
    main()

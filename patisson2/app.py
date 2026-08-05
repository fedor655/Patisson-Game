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

from .audio.manager import AudioManager
from . import settings as user_settings
from .input import ACTIONS, Bindings, Gamepad, PAD_BUTTONS
from .config import Config
from .engine.pipeline import RenderPipeline
from .game.cooking import POT_POSITION, Kitchen, item_name
from .game.farming import CROPS, CROP_ORDER, Farm
from .game.fishing import BITE, IDLE, REELING, WAITING, Fishing
from .game.livestock import FEED_ITEM, SPECIES, Livestock
from .game.npc import Villagers
from .game.pests import Pests
from .game.player import Player
from .game.state import GameState, load_game, save_game, shop_entries
from .game.tutorial import Tutorial
from .ui.hud import HUD
from .ui.menu import MainMenu
from .ui.options import OptionsScreen
from .ui.worldmap import WorldMap
from .world.daynight import DayNightCycle
from .world.props import Props, plot_positions
from .world.weather import Precipitation
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
    if g.fullscreen and not offscreen:
        loadPrcFileData("", "fullscreen #t")
    if offscreen:
        loadPrcFileData("", "window-type offscreen")


class PatissonApp(ShowBase):
    def __init__(self, cfg: Config | None = None, offscreen: bool = False,
                 audio: bool = True, use_settings: bool = True):
        self.cfg = cfg or Config()
        # Stored choices decide the expensive settings before anything is
        # built, so the first frame is already what the player asked for.
        # Screenshot captures pass use_settings=False: whatever the machine
        # happens to have saved must not change what the pictures look like.
        self.settings = (user_settings.load() if use_settings
                         else user_settings.apply_preset(
                             dict(user_settings.DEFAULTS), "high"))
        user_settings.apply_to_config(self.cfg, self.settings)
        self._persist_settings = use_settings
        self.bindings = Bindings(self.settings.get("keys"))
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
        self.pests = Pests(self, self.world, self.props, self.farm,
                           self.cfg.game.day_length)
        self.precip = Precipitation(self, self.world, self.pipeline)
        self.livestock = Livestock(self, self.world, self.props,
                                   self.cfg.game.day_length)
        self.cycle = DayNightCycle(self.cfg.game.day_length,
                                   self.cfg.game.start_hour,
                                   self.cfg.game.season_days)
        self.state = GameState(self.cfg.game)
        self.state.stamina_frac = 1.0
        self.player = Player(self, self.world, self.cfg.game, start=(2.0, -9.0))
        self.hud = HUD(self, self.state, self.cfg)
        self.kitchen = Kitchen(self.state)
        self.audio = AudioManager(self) if audio else None
        if self.audio:
            self.state.sound = self.audio.play

        for x, y in plot_positions():
            self.farm.add_plot(x, y)

        self.weather = "clear"
        self.weather_timer = 40.0
        self.rng = random.Random(self.cfg.world.seed ^ 0x5EED)

        self.keys = {}
        self.paused = False
        self.fishing = Fishing(random.Random(self.cfg.world.seed ^ 0xF15))
        self.photo_mode = False
        self.worldmap = WorldMap(self, self.hud, self.world, self.cfg.world)
        self.options = OptionsScreen(self, self.hud)
        self.tutorial = Tutorial()
        self._walked = 0.0
        self.mode = "menu"             # menu | playing
        self.menu = MainMenu(self, self.hud)
        self._setup_input()

        self.apply_settings()
        self.taskMgr.add(self.update, "game-update")
        self.open_main_menu()

    # ------------------------------------------------------------------ input

    def _setup_input(self):
        self.gamepad = Gamepad(self)
        self._bind_actions()
        self._setup_fixed_input()

    def _bind_actions(self):
        """(Re)attach every rebindable action to whatever key it now uses."""
        for action, _label, _default, _rebind in ACTIONS:
            key = self.bindings.key_for(action)
            if not key:
                continue
            if action in ("forward", "back", "left", "right", "sprint"):
                self.accept(key, self._set_key, [action, True])
                self.accept(f"{key}-up", self._set_key, [action, False])
            else:
                self.accept(key, self._fire_action, [action])

    def _clear_action_keys(self):
        for action, _label, _default, _rebind in ACTIONS:
            key = self.bindings.key_for(action)
            if key:
                self.ignore(key)
                self.ignore(f"{key}-up")

    def _fire_action(self, action: str):
        handler = {
            "jump": lambda: None,          # movement handled by _set_key
            "interact": self.on_interact,
            "secondary": self.on_secondary,
            "sell": self.on_sell,
            "cycle_seed": lambda: self.state.cycle_seed(1),
            "shop": self.toggle_shop,
            "kitchen": self.toggle_kitchen,
            "journal": self.toggle_journal,
            "map": self.toggle_map,
            "options": self.toggle_options,
            "photo": self.toggle_photo_mode,
            "save": self.on_save,
            "load": self.on_load,
        }.get(action)
        if handler is not None:
            handler()

    def rebind(self, action: str, key: str) -> str | None:
        """Point an action at a new key and re-attach every handler."""
        self._clear_action_keys()
        error = self.bindings.rebind(action, key)
        self._bind_actions()
        self.settings["keys"] = self.bindings.to_dict()
        if self._persist_settings:
            user_settings.save(self.settings)
        return error

    def reset_bindings(self):
        self._clear_action_keys()
        self.bindings.reset()
        self._bind_actions()
        self.settings["keys"] = {}
        if self._persist_settings:
            user_settings.save(self.settings)

    def _setup_fixed_input(self):
        # Left/right double as value adjustment on the settings screen.
        for key, delta in (("arrow_left", -1), ("arrow_right", 1)):
            self.accept(key, self._on_side_arrow, [delta, True])
            self.accept(f"{key}-up", self._on_side_arrow, [delta, False])
        # Up/down double as list navigation while a panel owns the screen.
        for key, action in (("arrow_up", "forward"), ("arrow_down", "back")):
            self.accept(key, self._on_arrow, [action, True])
            self.accept(f"{key}-up", self._on_arrow, [action, False])

        self.accept("escape", self.on_escape)
        self.accept("mouse1", self.on_interact)
        self.accept("wheel_up", self.on_wheel, [-1])
        self.accept("wheel_down", self.on_wheel, [1])
        self.accept("f1", self.hud.toggle)
        self.accept("minus", self.nudge_volume, [-0.1])
        self.accept("=", self.nudge_volume, [0.1])
        self.accept("m", self.toggle_mute)
        self.accept("enter", self.on_confirm)
        for i in range(1, 6):
            self.accept(str(i), self.select_tool, [i - 1])

        # A controller drives the same actions; its layout is conventional and
        # therefore fixed rather than rebindable.
        for button, action in PAD_BUTTONS.items():
            self.accept(f"gp-{button}", self._on_pad_button, [action])

    def _on_side_arrow(self, delta, value):
        if value and self.options.visible:
            self.options.change(delta)
            return
        self.keys["right" if delta > 0 else "left"] = value

    def _on_pad_button(self, action: str):
        if action == "pause":
            self.on_escape()
        elif action == "panel_up":
            self._on_arrow("forward", True)
        elif action == "panel_down":
            self._on_arrow("back", True)
        elif action == "panel_left":
            self._on_side_arrow(-1, True)
        elif action == "panel_right":
            self._on_side_arrow(1, True)
        elif action == "jump":
            self.keys["jump"] = True
            self.taskMgr.doMethodLater(0.12, self._release_jump, "pad-jump")
        else:
            self._fire_action(action)

    def _apply_gamepad(self, dt: float, blocked: bool) -> None:
        """Fold stick positions into the same keys/look the keyboard drives."""
        pad = getattr(self, "gamepad", None)
        if pad is None or not pad.connected:
            return
        mx, my, lx, ly = pad.sticks()
        if blocked:
            return
        self.keys["forward"] = my > 0.15
        self.keys["back"] = my < -0.15
        self.keys["right"] = mx > 0.15
        self.keys["left"] = mx < -0.15
        self.keys["sprint"] = (mx * mx + my * my) > 0.64
        if lx or ly:
            self.player.heading -= lx * 170.0 * dt
            self.player.pitch = max(-89.0, min(89.0,
                                               self.player.pitch + ly * 130.0 * dt))

    def _release_jump(self, task):
        self.keys["jump"] = False
        return task.done

    def _set_key(self, action, value):
        self.keys[action] = value

    def _on_arrow(self, action, value):
        if value and self.options.visible:
            self.options.move(-1 if action == "forward" else 1)
            self.sound("click", 0.3)
            return
        if value and self.worldmap.visible:
            self.worldmap.move(-1 if action == "forward" else 1)
            self.sound("click", 0.35)
            return
        if value and self.hud.panel_mode in ("shop", "kitchen"):
            self.panel_cursor(-1 if action == "forward" else 1)
            return
        self.keys[action] = value

    def panel_cursor(self, delta: int):
        if self.hud.panel_mode == "shop":
            self.hud.move_shop_cursor(delta)
        elif self.hud.panel_mode == "kitchen":
            self.kitchen.move(delta)
            self.hud.refresh_panel()
        self.sound("click", 0.35)

    def _grab_mouse(self, grab: bool):
        self.mouse_grabbed = grab and not self.offscreen
        # Offscreen captures render into a GraphicsBuffer, which has no window
        # properties to set.
        if hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(self.mouse_grabbed)
            self.win.requestProperties(props)
        self.player.locked = not grab

    # ------------------------------------------------------------------ modes

    def open_main_menu(self):
        """Return to the title screen; the world keeps rendering behind it."""
        self.mode = "menu"
        self.paused = False
        self.hud.close_panel()
        self.hud.hide_dialogue()
        self.worldmap.close()
        self.hud.root.hide()
        self.menu.show()
        self._grab_mouse(False)
        self.keys.clear()
        # A settled mid-morning is the most flattering light for the title.
        self.cycle.total_time = 9.4 / 24.0 * self.cfg.game.day_length
        self.weather = "clear"
        self.player.frozen = True
        self.pipeline.prime_exposure()

    def _enter_world(self):
        self.mode = "playing"
        self.menu.hide()
        self.pipeline.prime_exposure()
        if self.hud.visible:
            self.hud.root.show()
        self.player.frozen = False
        self.paused = False
        self._grab_mouse(True)

    def menu_new_game(self):
        self.sound("click", 0.6)
        self.reset_world()
        self.tutorial = Tutorial()
        self._walked = 0.0
        self._enter_world()
        # The tutorial panel says all this, and says it until it is done.
        if not self.tutorial.active:
            self.state.notify("Ферма ждёт.", 5.0)

    def menu_continue(self):
        self.sound("click", 0.6)
        if load_game(self.state, self.farm, self.cycle, self.player,
                     livestock=self.livestock, pests=self.pests,
                     tutorial=self.tutorial):
            self._enter_world()
            self.state.notify("Игра загружена")
        else:
            self.sound("error", 0.6)
            self.menu.info.setText("Не удалось прочитать сохранение.")

    def reset_world(self):
        """Fresh save state and a fresh set of starting plots."""
        self.state.__init__(self.cfg.game)
        if self.audio:
            self.state.sound = self.audio.play
        for plot in list(self.farm.plots):
            self.farm._clear_model(plot)
        self.farm.plots.clear()
        self.farm.harvest_log.clear()
        # Only the player-painted channels reset: red is tilled soil and
        # green is worn path, but blue is the building footprints, which
        # keep grass from growing through the floors.
        self.world.mask.data[:, :, :2] = 0
        self.world.mask._dirty = True
        for x, y in plot_positions():
            self.farm.add_plot(x, y)
        self.cycle.total_time = (self.cfg.game.start_hour / 24.0
                                 * self.cfg.game.day_length)
        self.player.pos.x, self.player.pos.y = 2.0, -9.0
        self.player.pos.z = self.world.height_at(2.0, -9.0)
        self.player.heading, self.player.pitch = 0.0, -6.0
        self.player.vel.set(0, 0, 0)
        self.weather = "clear"

    # --------------------------------------------------------------- commands

    def nudge_volume(self, delta: float):
        if not self.audio:
            return
        level = self.audio.nudge_master(delta)
        self.state.notify(f"Громкость: {level * 100:.0f}%", 1.6)
        self.hud.refresh_panel()

    def toggle_mute(self):
        if not self.audio:
            return
        self._muted = not getattr(self, "_muted", False)
        if self._muted:
            self._pre_mute = self.audio.master
            self.audio.set_volumes(master=0.0)
            self.state.notify("Звук выключен", 1.6)
        else:
            self.audio.set_volumes(master=getattr(self, "_pre_mute", 0.9))
            self.state.notify("Звук включён", 1.6)
        self.hud.refresh_panel()

    def apply_settings(self) -> None:
        """Push the stored choices at the live pipeline and mixer."""
        d = self.settings
        g = self.cfg.graphics
        pipe = self.pipeline

        size = int(d["shadow_size"])
        if size != g.shadow_size:
            g.shadow_size = size
            pipe.sun.setShadowCaster(True, size, size, -3000)
            pipe.set_shadow_size(size)

        g.ssao = bool(d["ssao"])
        g.bloom = bool(d["bloom"])
        g.godrays = bool(d["godrays"])
        pipe.set_ssao(g.ssao)
        pipe.composite.setShaderInput(
            "u_bloomStrength", g.bloom_strength if g.bloom else 0.0)
        pipe.composite.setShaderInput(
            "u_godrayStrength", g.godray_strength if g.godrays else 0.0)

        count = max(1000, int(Config().graphics.grass_density * float(d["grass_scale"])))
        if getattr(self, "world", None) is not None:
            self.world.grass_np.setInstanceCount(count)

        if self.audio:
            self.audio.set_volumes(master=d["master_volume"],
                                   music=d["music_volume"],
                                   sfx=d["sfx_volume"])

    def toggle_options(self):
        if self.options.visible:
            self.close_options()
            return
        self.sound("click", 0.5)
        self.hud.close_panel()
        self.worldmap.close()
        self.hud.root.hide()
        self.options.open()
        self._grab_mouse(False)

    def _button_thrower(self):
        """None when there is no window to read buttons from (offscreen runs)."""
        throwers = getattr(self, "buttonThrowers", None)
        return throwers[0].node() if throwers else None

    def begin_capture(self):
        """Listen for the next raw button so it can be bound to an action."""
        thrower = self._button_thrower()
        if thrower is None:
            return
        thrower.setButtonDownEvent("rebind-button")
        self.accept("rebind-button", self._on_capture)

    def _on_capture(self, button):
        thrower = self._button_thrower()
        if thrower is not None:
            thrower.setButtonDownEvent("")
        self.ignore("rebind-button")
        name = str(button)
        if name == "escape":
            self.options.capturing = None
            self.options.refresh()
            return
        self.options.captured(name)

    def close_options(self):
        if self.options.page == "keys":
            self.options.back_to_main()
            self.sound("click", 0.4)
            return
        self.sound("click", 0.45)
        self.options.close()
        if self._persist_settings:
            user_settings.save(self.settings)
        if self.mode == "menu":
            self.menu.show()
        else:
            if self.hud.visible:
                self.hud.root.show()
            self._grab_mouse(not self.paused)

    def toggle_map(self):
        if self.mode == "menu" or self.hud.panel_mode:
            return
        self.sound("click", 0.5)
        self.teach("map")
        opened = self.worldmap.toggle()
        # The HUD would otherwise print prompts straight across the map.
        if opened:
            self.hud.root.hide()
        elif self.hud.visible:
            self.hud.root.show()
        self._grab_mouse(not opened)

    def travel_to_selected(self):
        """Walk there off-screen: the time it would have taken still passes."""
        label, (tx, ty), _kind = self.worldmap.selected()
        seconds = self.worldmap.travel_cost(self.player.pos)
        if seconds < 2.0:
            self.sound("error", 0.5)
            self.state.notify("Вы уже здесь")
            return
        self.cycle.total_time += seconds
        self.player.pos.x, self.player.pos.y = tx, ty
        self.player.pos.z = self.world.height_at(tx, ty)
        self.player.vel.set(0, 0, 0)
        # Arriving costs stamina, so travelling is a convenience, not a free lunch.
        self.player.stamina = max(0.0, self.player.stamina - seconds * 0.55)
        self.worldmap.close()
        if self.hud.visible:
            self.hud.root.show()
        self._grab_mouse(True)
        self.sound("click", 0.7)
        minutes = int(seconds / self.cfg.game.day_length * 24 * 60)
        self.state.notify(f"{label}: дорога заняла {max(1, minutes)} мин")

    def skip_tutorial(self):
        self.sound("click", 0.5)
        self.tutorial.skip()
        self.state.notify("Обучение отключено")
        self.hud.close_panel()
        self.paused = False
        self._grab_mouse(True)

    def teach(self, event: str) -> None:
        """Tell the tutorial something real happened."""
        step = self.tutorial.record(event)
        if step is not None:
            self.sound("click", 0.45)
            if self.tutorial.finished:
                self.state.notify("Обучение пройдено. Ферма ваша.", 6.0)
                self.state.unlock("first_seed")

    def sound(self, name: str, volume: float = 1.0, pitch: float = 0.0):
        if self.audio:
            self.audio.play(name, volume, pitch)

    def select_tool(self, index: int):
        self.sound("click", 0.5)
        from .game.state import TOOLS
        self.state.tool_index = max(0, min(len(TOOLS) - 1, index))

    def on_wheel(self, delta: int):
        if self.hud.panel_mode in ("shop", "kitchen"):
            self.panel_cursor(delta)
        else:
            self.state.cycle_seed(delta)

    def on_escape(self):
        if self.options.visible:
            self.close_options()
            return
        self.sound("click", 0.45)
        if self.worldmap.visible:
            self.worldmap.close()
            if self.hud.visible:
                self.hud.root.show()
            self._grab_mouse(True)
            return
        if self.mode == "menu":
            self.menu.back()
            return
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
        if self.mode == "menu":
            return
        self.sound("click", 0.5)
        if self.hud.panel_mode == "shop":
            self.hud.close_panel()
            self.paused = False
            self._grab_mouse(True)
        elif self.hud.panel_mode is None:
            self.hud.open_panel("shop")
            self.paused = True
            self._grab_mouse(False)

    def toggle_journal(self):
        if self.mode == "menu":
            return
        self.sound("click", 0.5)
        if self.hud.panel_mode == "journal":
            self.hud.close_panel()
            self.paused = False
            self._grab_mouse(True)
        elif self.hud.panel_mode is None:
            self.hud.open_panel("journal")
            self.paused = True
            self._grab_mouse(False)

    def toggle_kitchen(self):
        if self.mode == "menu":
            return
        if self.hud.panel_mode == "kitchen":
            self.hud.close_panel()
            self.paused = False
            self._grab_mouse(True)
        elif self.hud.panel_mode is None and self._near_pot():
            self.sound("click", 0.5)
            self.hud.open_panel("kitchen")
            self.paused = True
            self._grab_mouse(False)
        elif self.hud.panel_mode is None:
            self.sound("error", 0.5)
            self.state.notify("Котёл стоит у дома")

    def on_cook(self):
        """Enter in the kitchen cooks; F eats what is selected."""
        recipe = self.kitchen.cook()
        if recipe is None:
            self.sound("error", 0.6)
            missing = self.kitchen.missing()
            short = ", ".join(f"{item_name(k)} x{v}" for k, v in missing.items())
            self.state.notify(f"Не хватает: {short}")
        else:
            self.sound("harvest", 0.8)
            self.state.notify(f"Приготовлено: {recipe.name}")
            self.state.unlock("first_dish")
            self.state.record("cook", recipe.key)
            if len(self.state.cooked) >= 5:
                self.state.unlock("chef")
        self.hud.refresh_panel()

    def on_eat(self):
        recipe = self.kitchen.eat(self.player)
        if recipe is None:
            self.sound("error", 0.6)
            self.state.notify("Этого блюда нет в сумке")
        else:
            self.sound("water", 0.5)
            self.state.notify(f"Съедено: {recipe.name} (+{recipe.stamina:.0f} сил)")
        self.hud.refresh_panel()

    def on_confirm(self):
        if self.options.visible:
            self.options.confirm()
            return
        if self.worldmap.visible:
            self.travel_to_selected()
            return
        if self.hud.panel_mode == "kitchen":
            self.on_cook()
            return
        if self.hud.panel_mode == "shop":
            before = self.state.coins
            self.state.buy(self.hud.shop_key)
            self.sound("coin" if self.state.coins != before else "error", 0.8)
            self.hud.refresh_panel()

    def on_save(self):
        path = save_game(self.state, self.farm, self.cycle, self.player,
                         livestock=self.livestock, pests=self.pests,
                         tutorial=self.tutorial)
        self.state.notify(f"Сохранено: {path.name}")

    def on_load(self):
        if load_game(self.state, self.farm, self.cycle, self.player,
                     livestock=self.livestock, pests=self.pests,
                     tutorial=self.tutorial):
            self.state.notify("Игра загружена")
        else:
            self.state.notify("Сохранение не найдено")

    def on_sell(self):
        if self.hud.panel_mode == "kitchen":
            self.on_eat()
            return
        if self._near_stall():
            sold = self.state.sell_all()
            self.sound("coin" if sold else "error", 0.9)
            if sold:
                self.teach("sell")
        else:
            self.sound("error", 0.6)
            self.state.notify("Продавать можно у прилавка")

    def toggle_photo_mode(self):
        if self.mode == "menu":
            return
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

    def _near_pot(self) -> bool:
        px, py = POT_POSITION
        return (self.player.pos.x - px) ** 2 + (self.player.pos.y - py) ** 2 < 20.0

    def _near_bed(self, reach: float = 1.9) -> bool:
        bed = getattr(self.props, "bed_pos", None)
        if bed is None:
            return False
        dx = self.player.pos.x - bed[0]
        dy = self.player.pos.y - bed[1]
        return dx * dx + dy * dy < reach * reach

    def _sleep(self):
        """Sleep through to six in the morning, waking rested."""
        st = self.state
        self.cycle.skip_to_hour(6.0)
        self.player.stamina = self.cfg.game.stamina_max
        st.stamina_frac = 1.0
        self.sound("achieve", 0.35)
        st.notify(f"Утро {self.cycle.day + 1}-го дня. Вы выспались.")
        st.unlock("well_rested")

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
        if self._near_bed():
            return "[E] Лечь спать", "до утра"
        crow = self.pests.scarecrow
        if (self.player.pos - crow.pos).lengthSquared() < 6.0:
            return "[E] Поправить пугало", f"состояние: {crow.status()}"
        npc = self.villagers.nearest(self.player.pos, 2.8)
        if npc is not None:
            return f"[E] Поговорить — {npc.name}", npc.activity
        if self._near_pot():
            return "[K] Готовить у котла", "Блюда дороже, чем сырьё"
        animal, animal_state = self.livestock.nearest(self.player.pos)
        if animal_state is not None:
            kind = "курица" if animal_state.kind == "chicken" else "корова"
            if animal_state.ready:
                product = SPECIES[animal_state.kind][0]
                return f"[E] Забрать: {item_name(product)}", kind
            cost = SPECIES[animal_state.kind][2]
            if animal_state.hungry:
                if st.count(FEED_ITEM) >= cost:
                    return f"[E] Покормить ({item_name(FEED_ITEM)} x{cost})", kind
                return "", f"{kind} голодна — нужна пшеница x{cost}"
            pct = animal_state.progress * 100.0
            return "", f"{kind}: сыта, готово на {pct:.0f}%"
        if self.fishing.active:
            fs = self.fishing.state
            if fs.phase == BITE:
                return "[E] Подсекай!", ""
            if fs.phase == REELING:
                return ("[E] Тяни, когда метка в зоне",
                        f"{fs.species.name} · {fs.pulls_done}/{fs.species.pulls}")
            return "Ждём поклёвки…", "[E] смотать"
        tool = st.tool
        plot, _ = self._aim_plot()
        if tool == "hoe":
            if plot is not None and plot.crop is None and plot.tilled:
                if plot is not None and plot.weeds >= 0.05:
                    return "[E] Прополоть", f"Сорняки: {plot.weeds*100:.0f}%"
                return "", "Грядка уже вскопана"
            return "[E] Вскопать грядку", "Смотрите на землю"
        if tool == "can":
            if self._near_well() or self._near_water():
                return "[E] Набрать воду", f"{st.water:.0f}/{st.upgrades.can_capacity:.0f}"
            if plot is not None and plot.crop is not None:
                if st.water < 1.0:
                    return "", "Лейка пуста — наберите у колодца"
                note = f"Влага: {plot.water*100:.0f}%"
                if plot.sick:
                    note += "  ·  гниль — нужна зола (ПКМ)"
                elif plot.weedy:
                    note += "  ·  сорняки — прополите мотыгой"
                return "[E] Полить", note
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
                note = f"Зреет: {plot.progress*100:.0f}%"
                if plot.sick:
                    note += "  ·  поражено гнилью"
                elif plot.weedy:
                    note += "  ·  заросло сорняками"
                return "", note
        return "", ""

    def on_interact(self):
        if self.mode == "menu" or self.paused or self.hud.panel_mode:
            return
        if self.hud.dialogue:
            self.hud.hide_dialogue()
            return
        st = self.state

        if self._near_bed():
            self._sleep()
            return
        crow = self.pests.scarecrow
        if (self.player.pos - crow.pos).lengthSquared() < 6.0:
            if crow.repair():
                self.sound("plant", 0.7)
                st.notify("Пугало поправлено")
            else:
                self.sound("error", 0.5)
                st.notify("Пугало и так в порядке")
            return
        npc = self.villagers.nearest(self.player.pos, 2.8)
        if npc is not None:
            self.sound("click", 0.5)
            self.hud.show_dialogue(npc.name, npc.talk())
            return

        if self._near_pot():
            self.toggle_kitchen()
            return

        animal, animal_state = self.livestock.nearest(self.player.pos)
        if animal_state is not None:
            if animal_state.ready:
                product = self.livestock.collect(animal_state)
                st.give(product, 1)
                st.record("collect", product)
                self.sound("cluck" if animal_state.kind == "chicken" else "moo", 0.7)
                st.notify(f"Собрано: {item_name(product)}")
            elif animal_state.hungry:
                if self.livestock.feed(animal_state, st):
                    self.sound("plant", 0.7)
                    st.unlock("farmhand")
                    st.notify("Накормлено")
                else:
                    self.sound("error", 0.6)
                    st.notify(f"Нужна пшеница x{SPECIES[animal_state.kind][2]}")
            else:
                self.sound("click", 0.4)
            return

        if self.fishing.active:
            self._fishing_input()
            return

        tool = st.tool
        plot, target = self._aim_plot()

        if tool == "hoe":
            if plot is None and target is not None:
                weedy = self.farm.nearest(target, 1.0)
                if weedy is not None and weedy.weeds >= 0.05:
                    self.farm.weed(weedy)
                    self.sound("dig", 0.7)
                    st.weeded = getattr(st, "weeded", 0) + 1
                    if st.weeded >= 20:
                        st.unlock("gardener")
                    st.notify("Грядка прополота")
                    self.teach("weed")
                    return
                from .world.layout import PLOT_SPACING
                dug = 0
                for ox, oy in st.upgrades.till_pattern:
                    if self.farm.till(target.x + ox * PLOT_SPACING,
                                      target.y + oy * PLOT_SPACING) is not None:
                        dug += 1
                if dug:
                    self.sound("dig", 0.9)
                    self.teach("till")
                    st.notify("Грядка вскопана" if dug == 1
                              else f"Вскопано грядок: {dug}")
                else:
                    self.sound("error", 0.6)
                    st.notify("Здесь копать нельзя")
            elif plot is not None and plot.crop is not None and plot.health <= 0.02:
                self.farm.clear(plot)

        elif tool == "can":
            if self._near_well() or self._near_water():
                st.water = st.upgrades.can_capacity
                self.sound("well" if self._near_well() else "splash", 0.7)
                self.teach("fill")
                st.notify("Лейка полна")
            elif plot is not None and st.water >= 1.0:
                targets = [plot]
                spread = st.upgrades.water_radius
                if spread > 0.0:
                    targets = [q for q in self.farm.plots
                               if (q.x - plot.x) ** 2 + (q.y - plot.y) ** 2
                               < spread * spread]
                poured = 0
                for q in targets:
                    if st.water < 1.0:
                        break
                    if self.farm.water_plot(q):
                        st.water = max(0.0, st.water - 1.0)
                        poured += 1
                if poured:
                    self.sound("water", 0.8)
                    self.teach("water")
                    if poured > 1:
                        st.notify(f"Полито грядок: {poured}")
                elif not poured:
                    self.sound("error", 0.5)
                    st.notify("Грядка уже полита")
            elif plot is not None:
                self.sound("error", 0.5)
                st.notify("Лейка пуста")

        elif tool == "seeds":
            if plot is not None and plot.crop is None:
                key = st.seed_key
                if st.take(f"seed_{key}"):
                    self.farm.plant(plot, key)
                    self.sound("plant", 0.85)
                    self.teach("plant")
                    st.unlock("first_seed")
                    st.notify(f"Посажено: {CROPS[key].name}")
                    growing = sum(1 for p in self.farm.plots if p.crop)
                    if growing >= 10:
                        st.unlock("green_thumb")
                else:
                    self.sound("error", 0.6)
                    st.notify(f"Нет семян «{CROPS[key].name}»")

        elif tool == "rod":
            if self._near_water():
                self.fishing.cast(st.upgrades)
                self.sound("cast", 0.8)
            else:
                self.sound("error", 0.6)
                st.notify("Подойдите к воде")

        elif tool == "basket":
            if plot is not None and plot.ripe:
                result = self.farm.harvest(plot, st.upgrades.harvest_bonus)
                if result:
                    key, count = result
                    self.sound("harvest", 0.9)
                    self.teach("harvest")
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
        if self.mode == "menu" or self.paused or self.hud.panel_mode:
            return
        plot, _ = self._aim_plot()
        if plot is None or plot.crop is None:
            return
        if not self.state.take("fertilizer"):
            self.sound("error", 0.6)
            self.state.notify("Нет удобрения (купите в лавке)")
            return
        if plot.sick:
            if self.state.take("ash"):
                self.farm.cure(plot)
                self.sound("plant", 0.8)
                self.state.notify("Гниль вылечена золой")
            else:
                self.sound("error", 0.6)
                self.state.notify("Нужна зола (купите в лавке)")
            return
        self.farm.feed_plot(plot)
        self.sound("plant", 0.7)
        self.state.notify("Удобрено")

    def _fishing_input(self):
        st = self.state
        event = self.fishing.strike(self.cycle.hour, self.cycle.season,
                                    st.upgrades.luck)
        if event == "early":
            self.sound("error", 0.5)
            st.notify("Рано подсёк — леска пуста")
        elif event == "hooked":
            self.sound("splash", 0.7)
        elif event == "pull":
            self.sound("click", 0.6)
        elif event == "miss":
            self.sound("error", 0.45)
        elif event == "lost":
            self.sound("error", 0.7)
            st.notify("Рыба сорвалась")
        elif event == "landed":
            self._land_fish()

    def _land_fish(self):
        st = self.state
        catch = self.fishing.take_catch()
        if catch is None:
            return
        if catch.species.key == "boot":
            self.sound("splash", 0.7)
            st.notify("Старый сапог. Бывает.")
            return
        self.sound("catch", 0.8)
        st.add_fish(catch.species.key, catch.size)
        st.record("fish")
        st.notify(f"Поймано: {catch.describe()} — {catch.value} мон.")
        if st.total_fish >= 20:
            st.unlock("angler")
        if catch.species.key == "pike":
            st.unlock("pike_hunter")
        if catch.species.key == "goldfish":
            st.unlock("golden")
        from .game.fishing import SPECIES
        wanted = {sp.key for sp in SPECIES if sp.key != "boot"}
        if wanted <= set(st.fish_log):
            st.unlock("ichthyologist")

    def _update_fishing(self, dt: float):
        if not self.fishing.active:
            return
        event = self.fishing.update(dt, self.state.upgrades)
        if event == "bite":
            self.sound("splash", 0.5)
        elif event == "missed_bite":
            self.sound("error", 0.5)
            self.state.notify("Не успели подсечь")

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

        in_menu = self.mode == "menu"
        blocked = (in_menu or self.paused or self.worldmap.visible
                   or self.options.visible
                   or self.hud.panel_mode is not None)
        if not blocked:
            self.cycle.advance(dt)
            self._update_weather(dt)
            self._update_fishing(dt)
            raining = self.weather == "rain"
            for line in self.pests.update(dt, self.player.pos, raining):
                st.notify(line)
                if line.startswith("Ворона улетела"):
                    st.unlock("crow_chaser")
            events = self.farm.update(dt, self.cycle.season, raining)
            self.livestock.update(dt)
            for e in events:
                st.notify(e)

        if in_menu:
            cam_pos = self.menu.update(dt, self.camera, self.world)
        else:
            before = Vec3(self.player.pos)
            self._apply_gamepad(dt, blocked)
            self.player.update(dt, self.keys, blocked=blocked)
            self.player.apply_to_camera(self.camera)
            self._walked += (self.player.pos - before).length()
            if self._walked > 8.0:
                self.teach("move")
            cam_pos = self.player.eye
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
        p.set_ambient_scale(sky.ambient_scale)

        night = 1.0 if sky.is_night else max(0.0, 1.0 - sky.sun_dir.z * 8.0)
        if st.upgrades.lantern_oil:
            night *= 1.7

        gust = 0.75 if self.weather in ("rain", "snow") else 0.42
        wind = Vec4(0.82, 0.57, 0.0, gust)
        self.precip.set_weather(self.weather)
        self.precip.update(dt, cam_pos, self.cycle.total_time,
                           Vec3(0.82 * gust * 3.2, 0.57 * gust * 3.2, 0.0))
        self.world.update(dt, cam_pos if in_menu else self.player.pos, wind,
                          self.cycle.total_time)
        if self.cycle.season != self.world.season:
            self.world.apply_season(self.cycle.season)
            self.props.apply_season(self.cycle.season)
        self.props.update(dt, self.cycle.total_time, night,
                          cam_pos if in_menu else self.player.pos)
        self.villagers.update(dt if not blocked else 0.0, self.cycle.hour,
                              self.cycle.total_time,
                              None if in_menu else self.player.eye,
                              self.weather)
        p.update(dt, cam_pos, Vec3(cam_pos.x, cam_pos.y, cam_pos.z))

        if not in_menu and (23.5 <= self.cycle.hour or self.cycle.hour < 0.5):
            st.unlock("night_owl")
        if st.coins >= 1000:
            st.unlock("rich")

        if self.audio:
            speed = math.hypot(self.player.vel.x, self.player.vel.y) / 4.4
            event = self.audio.update(
                dt, hour=self.cycle.hour, is_night=sky.is_night,
                weather=self.weather, moving=0.0 if blocked else speed,
                on_ground=self.player.on_ground, paused=blocked)
            if event == "critter" and not blocked:
                self._critter_sound()
            if self.weather == "rain" and not blocked \
                    and self.rng.random() < dt * 0.035:
                self.audio.play("thunder", 0.45)

        self.worldmap.update(self.player.pos, self.player.heading, self.villagers)
        st.update_notifications(dt)
        if not in_menu:
            prompt, tip = self.context()
            self.hud.set_prompt(prompt, tip)
        self.hud.update(self.cycle, st, WEATHER_LABELS[self.weather])

        tracer = getattr(self, "pathtracer", None)
        if self.photo_mode and tracer:
            tracer.step(self.player, sky)
            st.photo_progress = tracer.progress
        else:
            st.photo_progress = None

        return task.cont

    def _critter_sound(self):
        """Let a nearby animal pipe up, attenuated by distance."""
        near = [a for a in self.props.animals
                if (a.node.getPos() - self.player.pos).lengthSquared() < 640.0]
        if not near:
            return
        animal = self.rng.choice(near)
        name = animal.node.getName()
        if name.startswith("chicken"):
            sound, falloff = "cluck", 20.0
        elif name.startswith("cow"):
            sound, falloff = "moo", 34.0
        else:
            return
        self.audio.play_at(sound, animal.node.getPos(), self.player.eye,
                           falloff=falloff, volume=0.8, pitch=0.08)

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

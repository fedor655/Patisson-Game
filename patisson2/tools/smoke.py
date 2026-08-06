"""Drive every player action once, headlessly, and fail loudly if any of it breaks.

    python -m patisson2.tools.smoke

Written after shipping a NameError in the sell path that survived six commits:
the code compiled, the screenshots still rendered, and nothing exercised the
one line that was broken. Compiling is not evidence that a game runs.
"""

from __future__ import annotations

import os
import random
import sys
import traceback
from pathlib import Path

from panda3d.core import Vec3

from ..config import Config

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    """Run one action; record whether it raised."""
    try:
        fn()
    except Exception:
        CHECKS.append((name, False, traceback.format_exc(limit=3)))
    else:
        CHECKS.append((name, True, ""))


def run() -> int:
    from ..app import PatissonApp, configure
    from ..game.fishing import BITE, REELING, WAITING

    cfg = Config()
    cfg.graphics.width, cfg.graphics.height = 640, 360
    cfg.graphics.vsync = False
    configure(cfg, offscreen=True)
    app = PatissonApp(cfg, offscreen=True, audio=False, use_settings=False)
    for _ in range(8):
        app.taskMgr.step()

    st = app.state
    # Every field the game state is supposed to have, recorded before play
    # starts. Anything that appears later was created by an assignment from
    # outside __init__ — which is how the weeding counter came to exist
    # without ever being saved, silently resetting that achievement on load.
    declared_fields = set(vars(st))
    check("новая игра", app.menu_new_game)
    check("кадр", lambda: [app.taskMgr.step() for _ in range(5)])

    # --- everything the player does with a key ---------------------------
    # Through on_interact and friends, standing and aiming where a player
    # would, and asserting the world moved. Calling Farm.weed() directly is
    # what let the weeding branch sit unreachable for the life of the branch:
    # "[E] Прополоть" was on screen and the key did nothing.

    def stand(x, y, heading=0.0, pitch=-70.0):
        app.player.pos.x, app.player.pos.y = x, y
        app.player.pos.z = app.world.height_at(x, y)
        app.player.heading, app.player.pitch = heading, pitch
        app.player.frozen = True

    def face(tx, ty, back=0.9, pitch=-70.0):
        """Stand `back` metres south of a spot and look down at it."""
        stand(tx, ty - back, 0.0, pitch)

    def acts(label, setup, press, moved):
        def run():
            setup()
            prompt = app.context()[0]
            press()
            assert moved(), f"{label}: ничего не изменилось (подсказка {prompt!r})"
        check(label, run)

    plot = app.farm.plots[0]

    acts("вспашка", lambda: (setattr(st, "tool_index", 0), stand(18.0, 18.0)),
         app.on_interact,
         lambda: app.farm.nearest(app.player.aim_point(1.0), 2.0) is not None)

    def plant_setup():
        plot.crop, plot.tilled, plot.weeds = None, True, 0.0
        st.give("seed_patisson", 5)
        st.tool_index, st.seed_index = 2, 0
        face(plot.x, plot.y)
    acts("посадка", plant_setup, app.on_interact, lambda: plot.crop == "patisson")

    def well_setup():
        from ..world.layout import LAYOUT
        st.water, st.tool_index = 0.0, 1
        wx, wy, _h = LAYOUT["well"]
        stand(wx + 1.2, wy + 1.2, 0.0, -30.0)
    acts("вода из колодца", well_setup, app.on_interact, lambda: st.water > 0.0)

    def pond_setup():
        # The waterline sits well inside the nominal pond radius; stand on the
        # shore where a player fishing would.
        st.water, st.tool_index = 0.0, 1
        px, py = app.world.pond_centre
        for dist in range(int(app.world.pond_radius), 3, -1):
            if app.world.height_at(px, py - dist) >= app.cfg.world.water_level:
                stand(px, py - dist, 0.0, -20.0)
                if app._near_water():
                    return
        raise AssertionError("не нашлось берега, с которого видно воду")
    acts("вода из пруда", pond_setup, app.on_interact, lambda: st.water > 0.0)

    def water_setup():
        plot.water, st.water, st.tool_index = 0.0, 8.0, 1
        face(plot.x, plot.y)
    acts("полив грядки", water_setup, app.on_interact, lambda: plot.water > 0.0)

    def fert_setup():
        plot.food = 0.0
        st.give("fertilizer", 2)
        st.tool_index = 0
        face(plot.x, plot.y)
    acts("удобрение (ПКМ)", fert_setup, app.on_secondary, lambda: plot.food > 0.0)

    def cure_setup():
        plot.blight = 0.6
        st.give("ash", 2)
        st.tool_index = 0
        face(plot.x, plot.y)
    acts("лечение гнили", cure_setup, app.on_secondary, lambda: plot.blight < 0.05)

    def weed_setup():
        plot.weeds = 0.8
        st.tool_index = 0
        face(plot.x, plot.y)

    def weeded_and_counted():
        return plot.weeds < 0.05 and st.weeded >= 1
    acts("прополка", weed_setup, app.on_interact, weeded_and_counted)

    def harvest_setup():
        plot.crop, plot.progress = "patisson", 1.0
        app.farm._refresh_model(plot)
        st.tool_index = 4
        face(plot.x, plot.y)
    acts("сбор урожая", harvest_setup, app.on_interact,
         lambda: plot.crop is None and st.count("patisson") > 0)

    def stall_setup():
        from ..world.layout import LAYOUT
        st.give("patisson", 4)
        st.coins = 0
        sx, sy, _h = LAYOUT["market_stall"]
        stand(sx + 1.0, sy + 1.0, 0.0, -20.0)
    acts("продажа у прилавка", stall_setup, app.on_sell, lambda: st.coins > 0)

    def scarecrow_setup():
        app.pests.scarecrow.condition = 0.3
        stand(app.pests.scarecrow.pos.x, app.pests.scarecrow.pos.y - 1.5)
    acts("починка пугала", scarecrow_setup, app.on_interact,
         lambda: app.pests.scarecrow.condition > 0.9)

    held = {}

    def feed_setup():
        from ..game.livestock import FEED_ITEM
        animal, state = next(iter(app.livestock.animals()))
        held["state"] = state
        state.fed, state.ready, state.progress = 0.0, False, 0.0
        st.give(FEED_ITEM, 8)
        p = animal.node.getPos()
        stand(p.x, p.y - 1.0, 0.0, -40.0)
    acts("кормление", feed_setup, app.on_interact,
         lambda: held["state"].fed > 0.0)

    def collect_setup():
        animal, state = next(iter(app.livestock.animals()))
        held["state"] = state
        state.ready, state.progress = True, 1.0
        p = animal.node.getPos()
        stand(p.x, p.y - 1.0, 0.0, -40.0)
    acts("сбор продукта", collect_setup, app.on_interact,
         lambda: not held["state"].ready)

    def cook_setup():
        from ..game.cooking import POT_POSITION
        st.give("egg", 6)
        st.give("milk", 4)
        px, py = POT_POSITION
        stand(px, py - 1.2, 0.0, -30.0)
        app.toggle_kitchen()                 # K opens the pot
        app.kitchen.index = 1                # omelette
    acts("готовка (Enter у котла)", cook_setup, app.on_confirm,
         lambda: st.count("omelette") > 0)
    app.toggle_kitchen()

    def talk_setup():
        app.hud.hide_dialogue()
        p = app.villagers.npcs[0].node.getPos()
        stand(p.x, p.y - 1.2, 0.0, -10.0)
    acts("разговор", talk_setup, app.on_interact,
         lambda: app.hud.dialogue is not None)
    app.hud.hide_dialogue()

    def tutorial_completes():
        """Every step must be reachable by playing.

        The ninth step, "look into the shop", had nothing emitting its event,
        so the tutorial stopped at 8/10 for good: the tenth step was
        unreachable, the panel never went away, and the sign-off never came.
        """
        from ..game.tutorial import STEPS

        emitted = set()
        source = Path(__file__).resolve().parents[1] / "app.py"
        text = source.read_text(encoding="utf-8")
        for step in STEPS:
            if f'teach("{step.event}")' in text:
                emitted.add(step.event)
        missing = [s.event for s in STEPS if s.event not in emitted]
        assert not missing, f"шагам обучения нечем сработать: {missing}"

        # And drive it: every step, in order, must advance.
        app.tutorial.index, app.tutorial.active = 0, True
        for step in STEPS:
            before = app.tutorial.index
            app.teach(step.event)
            assert app.tutorial.index == before + 1, \
                f"обучение застряло на «{step.title}» ({step.event})"
        assert app.tutorial.finished, "обучение не считает себя пройденным"
    check("обучение проходится", tutorial_completes)

    def tiers_do_what_the_shop_says():
        """Each tier is sold with a sentence. Hold the game to it.

        The shop promises three beds in a row, then 3×3; 18 water then 34 and
        the neighbours too; a fruit more, then another and a quarter on the
        price; a faster bite, a wider strike window, a slower marker and more
        rare fish. Every one of those is a number some other code has to read,
        and nothing was checking that it still did.
        """
        import statistics
        from ..world.layout import PLOT_SPACING
        from ..world.props import plot_positions

        keep = (st.upgrades.hoe, st.upgrades.can,
                st.upgrades.rod, st.upgrades.basket)
        try:
            # --- hoe: beds broken by one press ---------------------------
            for tier, want in ((1, 1), (2, 3), (3, 9)):
                st.upgrades.hoe = tier
                for p in list(app.farm.plots):
                    app.farm._clear_model(p)
                app.farm.plots.clear()
                st.tool_index = 0
                stand(20.0 + tier * 6.0, 20.0)
                app.on_interact()
                assert len(app.farm.plots) == want, \
                    f"мотыга т{tier}: вскопано {len(app.farm.plots)}, ждали {want}"
            for p in list(app.farm.plots):
                app.farm._clear_model(p)
            app.farm.plots.clear()
            for x, y in plot_positions():
                app.farm.add_plot(x, y)

            # --- can: capacity, and whether neighbours get wet -----------
            for tier, want in ((1, 8), (2, 18), (3, 34)):
                st.upgrades.can = tier
                assert st.upgrades.can_capacity == want, \
                    f"лейка т{tier}: ёмкость {st.upgrades.can_capacity}"
            target = app.farm.plots[7]
            near = [p for p in app.farm.plots if p is not target
                    and abs(p.x - target.x) <= PLOT_SPACING + 0.1
                    and abs(p.y - target.y) <= PLOT_SPACING + 0.1]
            assert near, "у грядки не нашлось соседей — проверка бессмысленна"
            for tier, neighbours_wet in ((1, False), (3, True)):
                st.upgrades.can = tier
                for p in app.farm.plots:
                    p.crop, p.water = "patisson", 0.0
                st.water, st.tool_index = 30.0, 1
                stand(target.x, target.y - 0.9)
                app.on_interact()
                assert target.water > 0.0, f"лейка т{tier}: цель не полита"
                wet = any(p.water > 0.0 for p in near)
                assert wet == neighbours_wet, \
                    f"лейка т{tier}: соседи политы={wet}, ждали {neighbours_wet}"

            # --- basket: fruit per bed, and the sale multiplier ----------
            for tier, want in ((1, 1), (2, 2), (3, 3)):
                st.upgrades.basket = tier
                plot0 = app.farm.plots[0]
                plot0.crop, plot0.progress, plot0.health = "patisson", 1.0, 1.0
                plot0.food = 0.0                 # no "well fed" bonus
                got = app.farm.harvest(plot0, st.upgrades.harvest_bonus)
                assert got and got[1] == want, \
                    f"корзина т{tier}: собрано {got and got[1]}, ждали {want}"
            plain, rich = [], []
            for tier, bucket in ((1, plain), (3, rich)):
                st.upgrades.basket = tier
                st.inventory.clear()
                st.give("patisson", 4)
                st.coins = 0
                st.sell_all()
                bucket.append(st.coins)
            assert rich[0] > plain[0], \
                f"корзина т3 не подняла цену: {plain[0]} -> {rich[0]}"

            # --- rod: the four numbers, and a bite that really comes faster
            waits = {}
            for tier in (1, 3):
                st.upgrades.rod = tier
                seen = []
                for _ in range(60):
                    app.fishing.cast(st.upgrades)
                    ticks = 0
                    while app.fishing.state.phase == WAITING and ticks < 4000:
                        app.fishing.update(1 / 60.0, st.upgrades)
                        ticks += 1
                    seen.append(ticks)
                    app.fishing.cancel()
                waits[tier] = statistics.median(seen)
            assert waits[3] < waits[1], \
                f"удочка т3 клюёт не быстрее: {waits[1]} -> {waits[3]} тиков"
            prev = None
            for tier in (1, 2, 3):
                st.upgrades.rod = tier
                now = (st.upgrades.bite_speed, -st.upgrades.strike_window,
                       st.upgrades.reel_ease, -st.upgrades.luck)
                if prev is not None:
                    assert all(a > b for a, b in zip(prev, now)), \
                        f"удочка т{tier} не лучше предыдущей: {prev} -> {now}"
                prev = now
        finally:
            (st.upgrades.hoe, st.upgrades.can,
             st.upgrades.rod, st.upgrades.basket) = keep
    check("тиры делают что обещано", tiers_do_what_the_shop_says)

    def tables_are_wired():
        """Every entry in every declaration table must be both produced and
        consumed somewhere.

        Three bugs have had this exact shape: a prompt whose branch could not
        run, a tutorial step whose event nobody emitted, a tool tier nothing
        displayed. Each was invisible until someone played that far. A table
        with a dead row in it is cheap to check and expensive to find by hand.
        """
        import re
        from ..audio import bank
        from ..config import Config
        from ..game.cooking import RECIPES
        from ..game.farming import CROPS, CROP_ORDER
        from ..game.livestock import PRODUCT_PRICE
        from ..game.state import (ACHIEVEMENTS, GameState, SHOP_ITEMS,
                                  TOOL_TIERS, default_quests)

        pkg = Path(__file__).resolve().parents[1]
        source = "\n".join(p.read_text(encoding="utf-8")
                           for p in pkg.rglob("*.py")
                           if "__pycache__" not in str(p) and p.name != "smoke.py")

        dead = [k for k in ACHIEVEMENTS if f'unlock("{k}")' not in source]
        assert not dead, f"достижения, которые нечем открыть: {dead}"

        kinds = {q.kind for q in default_quests()} - {"coins"}
        dead = [k for k in kinds if f'record("{k}"' not in source]
        assert not dead, f"виды заданий, которые никто не отмечает: {dead}"

        # Every sound a call site asks for must exist, or play() silently
        # does nothing and the action loses its voice.
        asked = set(re.findall(
            r'(?:self\.sound|\.play|play_at|sound)\(\s*"([a-z0-9_]+)"', source))
        unknown = sorted(asked - set(bank.ALL))
        assert not unknown, f"звуки, которых нет в банке: {unknown}"

        # Every shop line has to be buyable, and every tool tier has to both
        # sell and change something about the tool.
        fresh = GameState(Config().game)
        fresh.coins = 100_000
        unbuyable = [key for key, *_ in SHOP_ITEMS if not fresh.buy(key)]
        assert not unbuyable, f"товары, которые не покупаются: {unbuyable}"
        # Buying is not enough: buy() falls through to a generic "put it in
        # the bag" for anything it does not recognise, so an item nothing
        # consumes would sell happily and then sit there for ever.
        for key, name, _price, _desc in SHOP_ITEMS:
            if key.startswith("seed_"):
                assert key[5:] in CROPS, f"{key}: такой культуры нет"
                continue
            assert source.count(f'"{key}"') > 1, \
                f"{name} ({key}) покупается, но нигде не используется"

        fresh = GameState(Config().game)
        fresh.coins = 100_000
        for tool, tiers in TOOL_TIERS.items():
            for _ in tiers:
                was = getattr(fresh.upgrades, tool)
                assert fresh.buy(f"tool_{tool}"), f"{tool}: тир {was + 1} не продаётся"
                assert getattr(fresh.upgrades, tool) == was + 1, \
                    f"{tool}: покупка не подняла тир"
            seen = set()
            for level in (1, 2, 3):
                setattr(fresh.upgrades, tool, level)
                seen.add(tuple(str(getattr(fresh.upgrades, p)) for p in dir(
                    fresh.upgrades) if not p.startswith("_")
                    and not callable(getattr(fresh.upgrades, p))))
            assert len(seen) == 3, f"{tool}: тиры ничего не меняют"

        # Crops need seeds to buy and a slot in the cycle; recipes need
        # ingredients that exist.
        for key in CROPS:
            assert any(k == f"seed_{key}" for k, *_ in SHOP_ITEMS), \
                f"{key}: семена не продаются"
            assert key in CROP_ORDER, f"{key}: не выбирается клавишей Q"
        have = set(CROPS) | set(PRODUCT_PRICE) | {"fish"}
        for recipe in RECIPES:
            missing = [k for k in recipe.inputs if k not in have]
            assert not missing, f"{recipe.name}: ингредиенты негде взять {missing}"
    check("таблицы подключены", tables_are_wired)

    def tier_is_visible():
        """The tool bar must say which tier you are holding.

        Buying the 520-coin hoe changed nothing on the bar the hoe sits in.
        """
        from ..game.state import TOOLS
        keep = st.upgrades.hoe
        try:
            st.upgrades.hoe = 1
            app.hud.update(app.cycle, st, "Ясно")
            plain = app.hud.tool_labels[TOOLS.index("hoe")].getText()
            st.upgrades.hoe = 3
            app.hud.update(app.cycle, st, "Ясно")
            upgraded = app.hud.tool_labels[TOOLS.index("hoe")].getText()
        finally:
            st.upgrades.hoe = keep
        assert upgraded != plain, f"тир не виден на панели: {plain!r} = {upgraded!r}"
        for ch in upgraded:
            assert ch.isprintable(), f"непечатаемый знак в подписи: {upgraded!r}"
    check("тир инструмента виден", tier_is_visible)

    def sleep_setup():
        bed = app.props.bed_pos
        stand(bed[0], bed[1], 0.0, 0.0)
        app.cycle.total_time = (app.cycle.day * app.cfg.game.day_length
                                + 20.0 / 24.0 * app.cfg.game.day_length)
        held["day"] = app.cycle.day
    acts("сон в кровати", sleep_setup, app.on_interact,
         lambda: app.cycle.day > held["day"])

    # --- fishing ---------------------------------------------------------
    def fish_round():
        app.fishing.cast(st.upgrades)
        for _ in range(900):
            app.fishing.update(1 / 60.0, st.upgrades)
            if app.fishing.state.phase == BITE:
                app.fishing.strike(9.0, 1, st.upgrades.luck)
                break
        assert app.fishing.state.phase == REELING, "не подсеклось"
        for _ in range(4000):
            app.fishing.update(1 / 60.0, st.upgrades)
            if app.fishing.state.in_band():
                if app.fishing.strike(9.0, 1, st.upgrades.luck) == "landed":
                    app._land_fish()
                    return
            if not app.fishing.active:
                return
    check("рыбалка", fish_round)

    # --- economy ---------------------------------------------------------
    check("продажа", lambda: (st.give("patisson", 3), st.add_fish("roach", 0.4),
                              app.on_sell()))
    check("покупка семян", lambda: (setattr(st, "coins", 9999),
                                    st.buy("seed_carrot")))
    check("улучшение инструмента", lambda: st.buy("tool_hoe"))
    check("готовка", lambda: (st.give("egg", 4), st.give("milk", 2),
                              app.kitchen.cook()))

    # --- animals ---------------------------------------------------------
    def livestock_round():
        animal, state = next(iter(app.livestock.animals()))
        st.give("wheat", 4)
        app.livestock.feed(state, st)
        state.ready = True
        app.livestock.collect(state)
    check("живность", livestock_round)

    def feeding_pays_the_same():
        """One feeding must yield the same whether you hover or walk away.

        Feed used to drain while a finished product stood waiting, so a player
        who fed the barn and went fishing came back to half the eggs the wheat
        had paid for — and nothing in the game said so.
        """
        from ..game.livestock import SPECIES

        def run(kind, collect_every_tick):
            state = next(s for _a, s in app.livestock.animals() if s.kind == kind)
            state.fed = SPECIES[kind][3]
            state.progress, state.ready = 0.0, False
            got, idle = 0, 0.0
            step = app.cfg.game.day_length / 500.0
            for _ in range(3000):
                app.livestock.update(step)
                if state.ready and (collect_every_tick or idle >= 1.0):
                    app.livestock.collect(state)
                    got, idle = got + 1, 0.0
                elif state.ready:
                    idle += step / app.cfg.game.day_length
            return got

        for kind in ("chicken", "cow"):
            eager, lazy = run(kind, True), run(kind, False)
            assert eager == lazy, (
                f"{kind}: у грядки {eager} шт, а если уйти — {lazy}; "
                "корм сгорает, пока продукт ждёт")
            assert eager >= 1, f"{kind}: кормёжка не дала ничего"
    check("кормёжка не пропадает", feeding_pays_the_same)

    # --- villagers --------------------------------------------------------
    def dialogue_round():
        from ..game.dialogue import GREETINGS, TOPICS
        npc = app.villagers.npcs[0]
        npc.met, _ = False, npc.recent.clear()   # someone may have met them
        assert npc.talk(app.talk_context()) == GREETINGS[npc.key], "нет знакомства"
        # Every topic must have a line for every villager, or a context that
        # only fits one of them would leave the others with nothing to say.
        for topic in TOPICS:
            for other in app.villagers.npcs:
                assert topic.lines.get(other.key), f"{topic.name}: нет {other.key}"
        seen = set()
        for other in app.villagers.npcs:
            for _ in range(40):
                line = other.talk(app.talk_context())
                assert line and not line.endswith("«»"), f"пустая реплика: {line}"
                seen.add(line)
        assert len(seen) > 12, f"слишком однообразно: {len(seen)}"
    check("разговоры", dialogue_round)

    # --- soundscape -------------------------------------------------------
    def soundscape_round():
        scape = app.soundscape
        assert scape.trees, "ни одного дерева не записано"
        px, py = scape.pond_centre
        near = scape.beds(px, py)
        far = scape.beds(px + 400.0, py + 400.0)
        assert near["amb_water"] > far["amb_water"], "пруд не громче вблизи"
        assert scape.beds(px, py, indoors=True)["amb_water"] == 0.0
        heard = set()
        for hour in (2.0, 8.0, 13.0, 19.5, 23.0):
            for _ in range(60):
                got = scape.pick(px, py, hour, 0, "clear")
                if got:
                    name, pos, falloff, volume = got
                    assert falloff > 0.0 and 0.0 < volume <= 1.0
                    assert len(pos) == 3
                    heard.add(name)
        assert heard, "за целые сутки не раздалось ни звука"
    check("звуки природы", soundscape_round)

    def crow_round():
        heard = []
        app.pests.caw = lambda pos: heard.append(pos)
        plot = app.farm.plots[1]
        plot.crop, plot.progress = "patisson", 1.0
        app.pests.timer = 0.0
        app.pests._spawn_crow()
        assert app.pests.crows, "ворона не появилась"
        far = Vec3(500.0, 500.0, 0.0)          # out of scaring range
        for _ in range(400):
            app.pests.update(0.05, far, False)
            if heard:
                break
        assert heard, "ворона села молча"
        app.pests.caw = app._crow_caw
    check("ворона каркает", crow_round)

    # --- panels and screens ----------------------------------------------
    for name, opener in (("лавка", app.toggle_shop), ("котёл", app.toggle_kitchen),
                         ("журнал", app.toggle_journal)):
        check(name, lambda o=opener: (o(), app.taskMgr.step(), o()))

    def journal_pages():
        app.toggle_journal()
        from ..ui.hud import JOURNAL_PAGES
        for page in range(len(JOURNAL_PAGES)):
            app.hud.journal_page = page
            app.hud.refresh_panel()
            app.taskMgr.step()
        app.toggle_journal()
    check("разделы журнала", journal_pages)

    check("карта", lambda: (app.toggle_map(), app.taskMgr.step(), app.toggle_map()))
    check("переход по карте", lambda: (app.toggle_map(), app.worldmap.move(2),
                                       app.travel_to_selected()))
    check("настройки", lambda: (app.toggle_options(), app.options.change(1),
                                app.close_options()))

    def presets():
        """A preset flag must beat the settings file, and applying settings
        twice must give the same answer as applying them once."""
        from .. import settings as us
        from ..config import Config, GraphicsConfig

        on_disk = us.apply_preset(dict(us.DEFAULTS), "high")
        for name, ssao, godrays, shadow in (("low", False, False, 1024),
                                            ("medium", True, False, 2048),
                                            ("ultra", True, True, 4096)):
            cfg = Config()
            cfg.graphics = GraphicsConfig.preset(name)
            chosen = us.resolve(on_disk, name)
            us.apply_to_config(cfg, chosen)
            g = cfg.graphics
            assert g.ssao is ssao, f"--{name}: ssao {g.ssao}, ждали {ssao}"
            assert g.godrays is godrays, f"--{name}: лучи {g.godrays}"
            assert g.shadow_size == shadow, f"--{name}: тени {g.shadow_size}"
            assert on_disk["preset"] == "high", "resolve испортил файл настроек"

        cfg = Config()
        data = us.apply_preset(dict(us.DEFAULTS), "low")
        us.apply_to_config(cfg, data)
        once = cfg.graphics.grass_density
        us.apply_to_config(cfg, data)
        assert cfg.graphics.grass_density == once, (
            f"настройки не идемпотентны: {once} -> {cfg.graphics.grass_density}")
    check("пресеты качества", presets)
    check("переназначение", lambda: (app.rebind("interact", "r"),
                                     app.reset_bindings()))

    def bindings_cover_actions():
        """Every listed action must move the player or run a handler, and no
        two actions may end up sharing a key however you rebind them."""
        from ..input import ACTIONS, DEFAULTS, MOVEMENT, RESERVED
        handled = set(app.action_handlers()) | set(MOVEMENT)
        listed = {a for a, _l, _k, _r in ACTIONS}
        missing = sorted(listed - handled)
        assert not missing, f"действия без обработчика: {missing}"

        rng = random.Random(4)
        pool = sorted(set(DEFAULTS.values()) | set("yuiopnmb"))
        rebindable = [a for a, _l, _k, r in ACTIONS if r]
        for _ in range(200):
            app.bindings.rebind(rng.choice(rebindable), rng.choice(pool))
            keys = app.bindings.keys
            blank = [a for a in DEFAULTS if not keys.get(a)]
            assert not blank, f"действие осталось без клавиши: {blank}"
            seen = {}
            for act, key in keys.items():
                assert key not in seen, f"{act} и {seen[key]} на одной клавише {key}"
                seen[key] = act
        assert app.bindings.rebind(rebindable[0], sorted(RESERVED)[0]), \
            "зарезервированную клавишу дали занять"
        app.reset_bindings()
    check("действия и клавиши", bindings_cover_actions)
    check("пауза", lambda: (app.on_escape(), app.taskMgr.step(), app.on_escape()))

    def measure_buttons(buttons, where):
        """Every label inside its own frame, and no two frames overlapping.

        Six pause buttons used to sit in one row with every label spilling over
        its frame into its neighbour, and the save-slot labels ran a third of
        their length past the button. Both were laid out by guessing a scale.
        """
        from panda3d.core import TextNode
        boxes = []
        for b in buttons:
            node = b.component("text0").textNode
            scale = b["text_scale"][0]
            width = node.getWidth() * scale
            l, r, d, u = b["frameSize"]
            if node.getAlign() == TextNode.ALeft:
                room = r - b["text_pos"][0]
            else:
                room = r - l
            assert width <= room - 0.01, \
                f"{where}: {b['text']!r} шире кнопки ({width:.3f} > {room:.3f})"
            x, _y, z = b.getPos()
            boxes.append((x + l, x + r, z + d, z + u, b["text"]))
        for i, a in enumerate(boxes):
            for c in boxes[i + 1:]:
                apart = a[1] <= c[0] or c[1] <= a[0] or a[3] <= c[2] or c[3] <= a[2]
                assert apart, f"{where}: кнопки налезают — {a[4]!r} и {c[4]!r}"
        return boxes

    def pause_layout():
        app.hud.open_panel("pause")
        app.taskMgr.step()
        boxes = measure_buttons(app.hud.panel_buttons, "пауза")
        # The body must stop above the top row of buttons.
        top = max(b[3] for b in boxes)
        body_z = app.hud.panel_body.getPos()[1]
        rows = len(app.hud.panel_body.getText().split("\n"))
        bottom = body_z - rows * app.hud.panel_body.getScale()[0] * 1.22
        assert bottom > top, f"текст заходит на кнопки: {bottom:.3f} <= {top:.3f}"
        app.hud.close_panel()
    check("вёрстка паузы", pause_layout)

    def menu_layout():
        """Same measurements for the title screen, plus its longest pane."""
        app.write_save(1)                     # so the slot list has real text
        menu = app.menu
        for name, build in (("главное", menu._build_root),
                            ("сохранения", menu._build_saves),
                            ("звук", menu._build_settings),
                            ("достижения", menu._build_achievements)):
            build()
            app.taskMgr.step()
            measure_buttons(menu.buttons, f"меню/{name}")
        # The achievements list must fit on the screen and on its own panel.
        text = menu.info.getText()
        rows = text.count("\n") + 1
        top = menu.info.getPos()[1]
        bottom = top - rows * menu.info.getScale()[0] * 1.22
        assert bottom > -1.0, f"список уезжает за экран: {bottom:.3f}"
        panel_bottom = menu.info_panel["frameSize"][2]
        assert panel_bottom <= bottom, \
            f"подложка короче списка: {panel_bottom:.3f} > {bottom:.3f}"
        menu._build_root()
    check("вёрстка меню", menu_layout)

    def tutorial_panel():
        """Every step's hint must be shorter than the panel it is drawn on.

        Four of the ten hints wrap to a second line, which used to hang below
        the panel over the scenery. Panda's own text bounds under-report a
        wrapped block, so this measures the panel against the row count.
        """
        from ..game.tutorial import STEPS
        app.tutorial.active = True
        seen = set()
        for i in range(len(STEPS) + 1):
            app.tutorial.index = i
            app.hud._update_tutorial()
            app.taskMgr.step()
            hint = app.hud.tutor_hint
            rows = hint.textNode.getNumRows()
            seen.add(rows)
            need = -0.122 - rows * hint.getScale()[0] * 1.25
            bottom = app.hud.tutor_panel["frameSize"][2]
            assert bottom <= need + 0.011, (
                f"шаг {i}: {rows} строк(и) не помещаются "
                f"({bottom:.3f} > {need:.3f})")
        assert max(seen) > 1, "ни одна подсказка не переносится — проверка пустая"
    check("панель обучения", tutorial_panel)

    def map_texture():
        """Specific places on the map must look like what stands there.

        The map used to be shaded from the height field alone: a smooth green
        field with the farm as a thumbnail in the middle of it. Counting
        coloured pixels is not enough to catch that — bare hillside is reddish
        too — so this reads the pixel at each landmark.
        """
        import numpy as np
        from ..ui.worldmap import _px
        from ..world.layout import LAYOUT
        from ..world.terrain import POND_CENTRE
        tex = app.worldmap.texture
        data = np.frombuffer(tex.getRamImage().getData(), np.uint8)
        data = data.reshape(tex.getYSize(), tex.getXSize(), 4)

        def at(x, y):                       # texture rows are y, columns x
            b, g, r, _a = data[int(_px(y)), int(_px(x))]
            return int(r), int(g), int(b)

        for name in ("house", "barn"):
            bx, by, _h = LAYOUT[name]
            r, g, b = at(bx, by)
            assert r > g + 55 and r > 120, f"{name} не нарисован: rgb {r},{g},{b}"
        r, g, b = at(*POND_CENTRE)
        assert b > r + 40, f"пруд не нарисован: rgb {r},{g},{b}"
        # A tree, and open ground two metres to its side, must differ.
        tx, ty, _tz = app.props.trees[0]
        tr, tg, tb = at(tx, ty)
        orr, og, ob = at(tx + 6.0, ty + 6.0)
        assert tg < og - 12, f"лес не нарисован: дерево {tg} vs поле {og}"
    check("карта нарисована", map_texture)

    # --- sleeping, saving, loading ---------------------------------------
    check("сон", lambda: (setattr(app.player.pos, "x", app.props.bed_pos[0]),
                          setattr(app.player.pos, "y", app.props.bed_pos[1]),
                          app.on_interact()))
    def round_trip():
        """Save a distinctive world, wreck it, load it, compare every field.

        "Did load_game raise?" is not the question. The question is whether
        what you saved is what comes back — the weather did not, so a game
        saved in the rain loaded into sunshine and the villagers walked back
        out from under their roofs.
        """
        def snap():
            return {
                "coins": st.coins, "fish": st.fish, "water": round(st.water, 4),
                "inventory": dict(st.inventory),
                "upgrades": dict(vars(st.upgrades)),
                "achievements": sorted(st.achievements),
                "cooked": dict(st.cooked),
                "fish_log": {k: list(v) for k, v in st.fish_log.items()},
                "total_earned": st.total_earned, "weeded": st.weeded,
                "best_fish": list(st.best_fish) if st.best_fish else None,
                "quests": [(q.key, q.progress, q.done) for q in st.quests],
                "plots": [(p.crop, round(p.progress, 4), round(p.water, 4),
                           round(p.weeds, 4), round(p.blight, 4), p.tilled)
                          for p in app.farm.plots],
                "harvest_log": dict(app.farm.harvest_log),
                "livestock": [(round(s.fed, 4), round(s.progress, 4), s.ready)
                              for _a, s in app.livestock.animals()],
                "scarecrow": round(app.pests.scarecrow.condition, 4),
                "tutorial": (app.tutorial.index, app.tutorial.active),
                "clock": round(app.cycle.total_time, 3),
                "player": (round(app.player.pos.x, 3), round(app.player.pos.y, 3)),
                "met": sorted(n.key for n in app.villagers.npcs if n.met),
                "weather": app.weather,
            }

        st.coins = 1234
        st.give("seed_pumpkin", 4)
        st.buy("tool_hoe")
        st.unlock("first_seed")
        st.add_fish("pike", 4.4)
        st.total_earned = 4321
        st.quests[0].progress, st.quests[0].done = 1, True
        for i, plot in enumerate(app.farm.plots[:6]):
            plot.tilled = True
            plot.crop = ("patisson", "carrot", "tomato")[i % 3]
            plot.progress, plot.water = 0.11 * (i + 1), 0.07 * i
            plot.weeds, plot.blight = 0.09 * i, 0.04 * i
        app.farm.harvest_log["patisson"] = 12
        for idx, (_a, s) in enumerate(app.livestock.animals()):
            s.fed, s.progress, s.ready = 0.3 + 0.05 * idx, 0.2, idx % 3 == 0
        app.pests.scarecrow.condition = 0.42
        app.tutorial.index = 4
        app.cycle.total_time = 3210.5
        app.player.pos.x, app.player.pos.y = -12.5, 21.25
        app.villagers.npcs[1].met = True
        app.weather = "rain"

        before = snap()
        app.write_save(3)
        st.coins, st.total_earned = 1, 0
        st.inventory.clear()
        st.achievements.clear()
        st.fish_log.clear()
        st.best_fish = None
        st.upgrades.hoe = 1
        for q in st.quests:
            q.progress, q.done = 0, False
        for plot in app.farm.plots:
            plot.crop, plot.progress, plot.water = None, 0.0, 0.0
            plot.weeds, plot.blight, plot.tilled = 0.0, 0.0, False
        app.farm.harvest_log.clear()
        for _a, s in app.livestock.animals():
            s.fed, s.progress, s.ready = 0.0, 0.0, False
        app.pests.scarecrow.condition = 1.0
        app.tutorial.index, app.tutorial.active = 0, True
        app.cycle.total_time = 0.0
        app.player.pos.x, app.player.pos.y = 0.0, 0.0
        for n in app.villagers.npcs:
            n.met = False
        app.weather = "clear"

        assert app.load_slot(3), "слот 3 не прочитался"
        after = snap()
        wrong = [k for k in before if before[k] != after[k]]
        assert not wrong, "\n".join(
            [f"не восстановилось: {', '.join(wrong)}"]
            + [f"  {k}: было {before[k]!r}, стало {after[k]!r}" for k in wrong])
    check("сохранение восстанавливает всё", round_trip)

    def broken_saves():
        """A damaged save must not take the game down.

        The file is on disk where a player can edit it, a disk can corrupt it
        and an older build can have written it. Six of these used to raise
        straight out of load_game — and describe() raised too, so a single bad
        slot made the main menu unopenable.
        """
        import json
        from ..game.state import describe, slot_path

        blobs = {
            "пустой файл": "",
            "не json": "{{{ ",
            "список вместо объекта": "[1, 2, 3]",
            "строка вместо объекта": '"hello"',
            "обрезанный": '{"state": {"coins": 10',
            "поля не тех типов": json.dumps({
                "state": {"coins": "много", "inventory": "нет", "quests": 7,
                          "upgrades": [1, 2], "achievements": 3, "fish_log": 9,
                          "best_fish": "щука"},
                "farm": {"plots": "нет", "harvested": 5},
                "livestock": {"animals": "нет"}, "pests": {"scarecrow": "целое"},
                "villagers": {"met": 5}, "weather": {"kind": 12, "timer": "скоро"},
                "tutorial": {"index": "два"}, "clock": {"total_time": "полдень"},
                "player": {"x": None, "y": [], "heading": {}},
            }),
            "нули везде": json.dumps({k: None for k in (
                "state", "farm", "livestock", "pests", "villagers", "tutorial",
                "clock", "player", "weather")}),
            "культура из другой игры": json.dumps({
                "farm": {"plots": [{"x": 1.0, "y": 2.0, "crop": "дракон",
                                    "progress": 99.0, "tilled": True}]},
                "weather": {"kind": "метеоритный дождь", "timer": -5.0},
            }),
        }
        path = slot_path(3)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            for label, blob in blobs.items():
                path.write_text(blob, encoding="utf-8")
                app.load_slot(3)          # may be False; must never raise
                app.taskMgr.step()
                assert describe(3), f"{label}: слот нечем описать"
            # And the world still works afterwards.
            app.farm.plant(app.farm.plots[0], "patisson")
            app.state.sell_all()
        finally:
            path.unlink(missing_ok=True)
        assert describe(3) == "пусто", "удалённый слот описан неверно"
    check("битые сохранения", broken_saves)

    def unwritable_home():
        """A disk that will not take the save must say so, not crash.

        Pressing F5 is the moment a player is trying hardest to protect their
        game; a full disk or a locked-down profile used to answer with a
        traceback. Autosave was already guarded, manual save was not.
        """
        from .. import settings as us
        from ..game import state as st_mod

        blocker = Path(os.environ.get("TEMP", ".")) / "patisson_smoke_blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        keep = (st_mod.SAVE_DIR, st_mod.SAVE_PATH, us.SETTINGS_PATH)
        try:
            st_mod.SAVE_DIR = blocker / "sub"
            st_mod.SAVE_PATH = st_mod.SAVE_DIR / "save.json"
            us.SETTINGS_PATH = blocker / "sub" / "settings.json"
            st.notifications.clear()
            app.on_save()                      # must not raise
            said = " ".join(text for text, _t in st.notifications)
            assert "Не удалось сохранить" in said, \
                f"F5 не пожаловался на отказ диска: {said!r}"
            app.autosave()                     # must not raise either
            us.save(dict(us.DEFAULTS))         # settings are a convenience
            assert st_mod.describe(1) in ("пусто", "повреждено")
        finally:
            st_mod.SAVE_DIR, st_mod.SAVE_PATH, us.SETTINGS_PATH = keep
            blocker.unlink(missing_ok=True)
        app.on_save()                          # and works again afterwards
    check("диск не пишется", unwritable_home)

    check("сохранение", app.on_save)
    check("автосохранение", app.autosave)
    check("загрузка", app.on_load)
    check("выход в меню", app.open_main_menu)

    def no_stowaway_fields():
        """No field may appear on the game state that __init__ never declared.

        A field created by `st.something = ...` from across the codebase is
        invisible to to_dict, so it is not saved, and the player loses it on
        every load. That is exactly what happened to the count of weeded beds:
        twenty are needed for an achievement and the tally reset every time
        the game was loaded.
        """
        appeared = sorted(set(vars(st)) - declared_fields)
        assert not appeared, (
            f"поля появились в обход __init__: {appeared}. "
            "Объявите их в GameState и сохраните в to_dict/from_dict")
        # And everything that counts progress has to survive a round trip.
        saved = set(st.to_dict())
        for field in ("weeded", "total_earned", "cooked", "fish_log",
                      "achievements", "play_time"):
            assert field in saved, f"{field} не попадает в сохранение"
    check("состояние без безбилетников", no_stowaway_fields)

    failures = [c for c in CHECKS if not c[1]]
    for name, ok, detail in CHECKS:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}", flush=True)
        if not ok:
            print("\n".join("        " + ln for ln in detail.strip().split("\n")),
                  flush=True)
    print(f"\n{len(CHECKS) - len(failures)}/{len(CHECKS)} проверок пройдено",
          flush=True)
    return 1 if failures else 0


def main():
    code = run()
    sys.stdout.flush()
    os._exit(code)


if __name__ == "__main__":
    main()

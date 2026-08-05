"""Drive every player action once, headlessly, and fail loudly if any of it breaks.

    python -m patisson2.tools.smoke

Written after shipping a NameError in the sell path that survived six commits:
the code compiled, the screenshots still rendered, and nothing exercised the
one line that was broken. Compiling is not evidence that a game runs.
"""

from __future__ import annotations

import os
import sys
import traceback

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
    from ..game.fishing import BITE, REELING

    cfg = Config()
    cfg.graphics.width, cfg.graphics.height = 640, 360
    cfg.graphics.vsync = False
    configure(cfg, offscreen=True)
    app = PatissonApp(cfg, offscreen=True, audio=False, use_settings=False)
    for _ in range(8):
        app.taskMgr.step()

    st = app.state
    check("новая игра", app.menu_new_game)
    check("кадр", lambda: [app.taskMgr.step() for _ in range(5)])

    # --- tools -----------------------------------------------------------
    def use(tool_index, where=(6.0, 8.0)):
        st.tool_index = tool_index
        app.player.pos.x, app.player.pos.y = where
        app.player.pitch = -60.0
        app.on_interact()

    check("мотыга", lambda: use(0, (18.0, 18.0)))
    check("лейка у колодца", lambda: use(1, (8.4, 7.6)))
    plot = app.farm.plots[0]
    check("посадка", lambda: (st.give("seed_patisson", 3),
                              app.farm.plant(plot, "patisson")))
    check("полив грядки", lambda: app.farm.water_plot(plot))
    check("удобрение", lambda: (st.give("fertilizer", 1), app.on_secondary()))
    check("прополка", lambda: (setattr(plot, "weeds", 0.8), app.farm.weed(plot)))
    check("лечение гнили", lambda: (setattr(plot, "blight", 0.5),
                                    st.give("ash", 1), app.farm.cure(plot)))
    check("сбор урожая", lambda: (setattr(plot, "progress", 1.0),
                                  app.farm.harvest(plot, st.upgrades.harvest_bonus)))

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

    # --- villagers --------------------------------------------------------
    def dialogue_round():
        from ..game.dialogue import GREETINGS, TOPICS
        npc = app.villagers.npcs[0]
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
    check("переназначение", lambda: (app.rebind("interact", "r"),
                                     app.reset_bindings()))
    check("пауза", lambda: (app.on_escape(), app.taskMgr.step(), app.on_escape()))

    def pause_layout():
        """Labels inside their own frames, and no two frames overlapping.

        Six buttons used to sit in one row: every label spilled over its frame
        and into its neighbour, and the panel text ran underneath them all.
        """
        app.hud.open_panel("pause")
        app.taskMgr.step()
        boxes = []
        for b in app.hud.panel_buttons:
            scale = b["text_scale"][0]
            width = b.component("text0").textNode.getWidth() * scale
            l, r, d, u = b["frameSize"]
            assert width <= (r - l) - 0.01, f"{b['text']!r} шире кнопки"
            x, _y, z = b.getPos()
            boxes.append((x + l, x + r, z + d, z + u, b["text"]))
        for i, a in enumerate(boxes):
            for c in boxes[i + 1:]:
                apart = a[1] <= c[0] or c[1] <= a[0] or a[3] <= c[2] or c[3] <= a[2]
                assert apart, f"кнопки налезают: {a[4]!r} и {c[4]!r}"
        # The body must stop above the top row of buttons.
        top = max(b[3] for b in boxes)
        body_z = app.hud.panel_body.getPos()[1]
        rows = len(app.hud.panel_body.getText().split("\n"))
        bottom = body_z - rows * app.hud.panel_body.getScale()[0] * 1.22
        assert bottom > top, f"текст заходит на кнопки: {bottom:.3f} <= {top:.3f}"
        app.hud.close_panel()
    check("вёрстка паузы", pause_layout)

    # --- sleeping, saving, loading ---------------------------------------
    check("сон", lambda: (setattr(app.player.pos, "x", app.props.bed_pos[0]),
                          setattr(app.player.pos, "y", app.props.bed_pos[1]),
                          app.on_interact()))
    check("сохранение", app.on_save)
    check("автосохранение", app.autosave)
    check("загрузка", app.on_load)
    check("выход в меню", app.open_main_menu)

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

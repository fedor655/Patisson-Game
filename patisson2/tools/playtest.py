"""Отыграть на ферме целый год и пожаловаться на всё странное.

    python -X utf8 -m patisson2.tools.playtest [дней]

Это не модульный тест: здесь нажимаются те же обработчики, что и у
игрока, в том же порядке, — копать, поливать, полоть, собирать, ходить
к пруду с удочкой, кормить кур и корову, варить у котла, продавать и
докупать семена, — а потом предъявляется всё, что выглядит неправильно:
деньги, ушедшие назад, запас в минусе, задание, которое нельзя закрыть,
культура, не выросшая за целый год, день без единого урожая.

Часы настоящие: игра ограничивает шаг 0,10 с на кадр, поэтому сессия
играется кадр за кадром с фиксированным шагом, а игровой день сокращён
до минуты. Все скорости в игре выражены на игровой день, так что это
сжимает симуляцию целиком, а не перекашивает её часть.

Найденное — это повод посмотреть, а не приговор. Так нашлись «Морковь
созрел» (четыре культуры из шести объявляли о себе не в том роде) и
то, что зимой не вызревало ничего.
"""
import io
import os
import sys
import tempfile
import traceback

REPORT = os.path.join(tempfile.gettempdir(), "patisson-playtest.txt")
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 29   # круг сезонов
DT = 0.10                      # matches the app's own per-frame cap
DAY_SECONDS = 60.0


def main():
    from panda3d.core import ClockObject

    from patisson2.config import Config
    from patisson2.app import PatissonApp, configure
    from patisson2.game.farming import CROPS, CROP_ORDER
    from patisson2.game.state import SHOP_ITEMS
    from patisson2.world.layout import LAYOUT

    cfg = Config()
    cfg.graphics.width, cfg.graphics.height = 640, 400
    cfg.graphics.vsync = False
    cfg.game.day_length = DAY_SECONDS
    configure(cfg, offscreen=True)
    app = PatissonApp(cfg, offscreen=True, audio=False, use_settings=False)

    clock = ClockObject.getGlobalClock()
    clock.setMode(ClockObject.MNonRealTime)
    clock.setDt(DT)

    for _ in range(6):
        app.taskMgr.step()
    app.menu_new_game()
    for _ in range(6):
        app.taskMgr.step()

    st, farm = app.state, app.farm
    out = io.StringIO()
    problems, log = [], []
    seen_notes, last_notes = {}, set()
    TOOLS = {"hoe": 0, "can": 1, "seeds": 2, "rod": 3, "basket": 4}
    # Список берётся из самой игры. Копия отстала на шестую культуру:
    # репу, которая одна и растёт зимой, проба не сажала ни разу.
    SEEDS = CROP_ORDER
    shop_keys = [k for k, *_ in SHOP_ITEMS]

    def stand(x, y, h=0.0, p=-70.0):
        app.player.pos.x, app.player.pos.y = x, y
        app.player.pos.z = app.world.height_at(x, y)
        app.player.heading, app.player.pitch = h, p
        app.player.frozen = True

    def frame():
        app.taskMgr.step()
        fresh = {n[0] for n in st.notifications}
        for text in fresh - last_notes:
            seen_notes[text] = seen_notes.get(text, 0) + 1
        last_notes.clear()
        last_notes.update(fresh)

    def buy(key, times=1):
        """Walk into the shop and buy, the way the keys do it."""
        if key not in shop_keys:
            return
        app.toggle_shop()
        app.hud.shop_index = shop_keys.index(key)
        for _ in range(times):
            app.on_confirm()
        app.toggle_shop()

    start_coins = st.coins
    out.write(f"старт: {st.coins} мон., {dict(st.inventory)}\n"
              f"день = {DAY_SECONDS:.0f} с, шаг {DT} с, "
              f"кадров на день {int(DAY_SECONDS / DT)}\n\n")

    harvested_today = 0
    planted_kinds = [0]        # чтобы культуры шли по кругу
    day = app.cycle.day
    sx, sy, _h = LAYOUT["market_stall"]
    frames_per_day = int(DAY_SECONDS / DT)

    from patisson2.game.cooking import POT_POSITION
    from patisson2.world.heightfield import POND_CENTRE
    from patisson2.game.fishing import BITE, IDLE, REELING

    # День игрока — это не только грядки. Раньше проба только копала,
    # и пять заданий из девяти не закрывались никогда: их закрывают
    # удочка, куры, корова и котёл.
    FARM_UNTIL = int(frames_per_day * 0.62)
    FISH_UNTIL = int(frames_per_day * 0.86)
    BARN_UNTIL = int(frames_per_day * 0.95)

    for i in range(DAYS * frames_per_day):
        hour = i % frames_per_day

        # --- у пруда: закинуть, подсечь, вываживать ------------------
        if FARM_UNTIL <= hour < FISH_UNTIL:
            st.tool_index = TOOLS['rod']
            stand(POND_CENTRE[0] + 5.5, POND_CENTRE[1] - 5.5, 0.0, -10.0)
            phase = app.fishing.state.phase
            if phase == IDLE:
                app.on_interact()
            elif phase == BITE or (phase == REELING
                                   and app.fishing.state.in_band()):
                app.on_interact()
            frame()
            continue

        # --- в хлеву: покормить и собрать ---------------------------
        if FISH_UNTIL <= hour < BARN_UNTIL:
            for animal, state in list(app.livestock.animals()):
                p = animal.node.getPos()
                stand(p.x, p.y - 0.8)
                app.on_interact()
            frame()
            continue

        # --- у котла: сварить, что получается -----------------------
        if hour >= BARN_UNTIL:
            stand(POT_POSITION[0] + 1.0, POT_POSITION[1] - 1.0)
            if app.hud.panel_mode != 'kitchen':
                app.toggle_kitchen()
            else:
                # Перебрать все рецепты: что сварится — то сварится.
                from patisson2.game.cooking import RECIPES
                for _ in range(len(RECIPES)):
                    app.on_cook()
                    app.kitchen.move(1)
                app.toggle_kitchen()
            frame()
            continue

        # --- act like a player, a few times a second ------------------
        if i % 5 == 0:
            for plot in farm.plots:
                if plot.crop is None:
                    if plot.tilled:
                        # Игрок сажает то, что растёт сейчас, а не первое
                        # попавшееся: вне сезона рост втрое медленнее.
                        # И перебирает культуры по кругу, а не берёт
                        # первую подходящую: с сортировкой по одному
                        # признаку патиссон подходит всегда и занимал
                        # все грядки — томат и тыкву проба покупала
                        # весь год и не посадила ни разу.
                        planted_kinds[0] += 1
                        turn = planted_kinds[0] % len(SEEDS)
                        order = sorted(
                            ((turn + k) % len(SEEDS)
                             for k in range(len(SEEDS))),
                            key=lambda n: app.cycle.season
                            not in CROPS[SEEDS[n]].seasons)
                        for n in order:
                            key = SEEDS[n]
                            if st.inventory.get(f"seed_{key}", 0) > 0:
                                st.seed_index = n
                                st.tool_index = TOOLS["seeds"]
                                stand(plot.x, plot.y - 0.85)
                                app.on_interact()
                                break
                    continue
                if plot.ripe:
                    st.tool_index = TOOLS["basket"]
                    stand(plot.x, plot.y - 0.85)
                    n0 = sum(st.inventory.values())
                    app.on_interact()
                    if sum(st.inventory.values()) > n0:
                        harvested_today += 1
                elif plot.water < 0.5:
                    st.water = st.upgrades.can_capacity      # topped at well
                    st.tool_index = TOOLS["can"]
                    stand(plot.x, plot.y - 0.85)
                    app.on_interact()
                elif plot.weeds >= 0.3:
                    st.tool_index = TOOLS["hoe"]
                    stand(plot.x, plot.y - 0.85)
                    app.on_interact()
        frame()

        # --- end of day: sell, restock, sleep -------------------------
        if app.cycle.day != day:
            stand(sx + 1.6, sy - 1.6)
            before = st.coins
            app.on_sell()
            earned = st.coins - before
            in_season = [k for k in SEEDS
                         if app.cycle.season in CROPS[k].seasons]
            for key, want in [(f"seed_{k}", 5) for k in in_season]:
                price = next(p for k, _n, p, _d in SHOP_ITEMS if k == key)
                buy(key, min(want, max(0, (st.coins - 20) // price)))
            done = sum(1 for q in st.quests if q.done)
            log.append((day + 1, harvested_today, earned, st.coins, done))
            out.write(f"день {day + 1} ({app.cycle.season_name}): "
                      f"собрано {harvested_today}, "
                      f"выручка {earned}, итого {st.coins} мон., "
                      f"заданий {done}/9\n")
            if harvested_today == 0 and day >= 2:
                problems.append(f"день {day + 1}: за весь день ни одного "
                                f"урожая")
            harvested_today = 0
            day = app.cycle.day

    out.write(f"\nитог: {st.coins} мон. (старт {start_coins})\n"
              f"инвентарь: {dict(st.inventory)}\n"
              f"собрано за сессию: {dict(farm.harvest_log)}\n")
    unfinished = [q.title for q in st.quests if not q.done]
    out.write(f"незакрытые задания: {unfinished}\n")
    out.write(f"уведомления: {dict(sorted(seen_notes.items(), key=lambda kv: -kv[1])[:8])}\n")

    if any(v < 0 for v in st.inventory.values()):
        problems.append(f"отрицательный запас: {dict(st.inventory)}")
    if st.coins < 0:
        problems.append(f"отрицательные монеты: {st.coins}")
    if st.coins <= start_coins and DAYS >= 6:
        problems.append(f"за {DAYS} дней ферма не заработала ничего "
                        f"({start_coins} -> {st.coins})")
    if not farm.harvest_log:
        problems.append("за всю сессию не собрано ни одного плода")
    if not any(q.done for q in st.quests):
        problems.append("ни одно задание не закрылось")
    # Про год спрашивается, только если год и правда отыгран: короткий
    # прогон не обязан вырастить тыкву и увидеть финал.
    if DAYS >= 4 * cfg.game.season_days + 1:
        grown = set(farm.harvest_log)
        missed = [CROPS[k].name for k in CROP_ORDER if k not in grown]
        if missed:
            problems.append(f"за целый год так и не выросли: {missed}")
        if not st.finale_shown:
            problems.append("год прошёл, а итогов игра не показала")
        if "year" not in st.achievements:
            problems.append("нет достижения за прожитый год")

    out.write("\nНАЙДЕНО:\n")
    for p in problems or ["ничего подозрительного"]:
        out.write(f"  {'!' if problems else '·'} {p}\n")

    open(REPORT, "w", encoding="utf-8").write(out.getvalue())
    print(out.getvalue(), flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        os._exit(1)

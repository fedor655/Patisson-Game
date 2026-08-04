"""Drives the real game offscreen and saves gameplay screenshots.

    python -m patisson2.tools.shots [outdir]

Rendering offscreen makes captures deterministic — a window that loses focus or
gets occluded can hand back a blank framebuffer.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

from panda3d.core import Filename, Vec3

from ..config import Config

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "screenshots2"


def look_at(player, target, from_pos):
    player.frozen = True
    player.pos = Vec3(*from_pos)
    dx = target[0] - from_pos[0]
    dy = target[1] - from_pos[1]
    dz = target[2] - (from_pos[2] + 1.68)
    player.heading = math.degrees(math.atan2(-dx, dy))
    player.pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))


def capture(out_dir: Path = DEFAULT_OUT, width: int = 1600, height: int = 900):
    from ..app import PatissonApp, configure

    cfg = Config()
    cfg.graphics.width = width
    cfg.graphics.height = height
    cfg.graphics.vsync = False
    configure(cfg, offscreen=True)

    app = PatissonApp(cfg, offscreen=True, audio=False)
    out_dir.mkdir(parents=True, exist_ok=True)

    def settle(frames=6):
        for _ in range(frames):
            app.taskMgr.step()

    def shot(name, hour=None, weather=None):
        if hour is not None:
            app.cycle.total_time = app.cycle.day * cfg.game.day_length \
                                   + hour / 24.0 * cfg.game.day_length
        if weather is not None:
            app.weather = weather
            app.weather_timer = 9e9
            # Skip the fade so a capture never lands mid-crossfade.
            app.precip.set_weather(weather)
            app.precip.snap()
        settle(3)
        # Let exposure settle on the new lighting.
        sky = app.cycle.state()
        app.pipeline._exposure = sky.exposure
        settle(5)
        path = out_dir / name
        ok = app.win.saveScreenshot(Filename.fromOsSpecific(str(path)))
        print(f"[shot] {name} -> {ok}", flush=True)

    settle(8)

    # Title screen first, then drop into the world for the rest.
    shot("00-main-menu.png")
    app.menu_new_game()
    settle(4)

    terrain = app.world.terrain
    st = app.state

    def gz(x, y):
        return terrain.height_at(x, y)

    # 1. The farm at morning, looking over the plots towards the well.
    look_at(app.player, (4.0, 5.0, 0.6), (3.0, -6.5, gz(3.0, -6.5)))
    st.tool_index = 0
    shot("01-farm-morning.png", hour=8.0, weather="clear")

    # 2. Grow the crops so the plots are worth looking at.
    for i, plot in enumerate(app.farm.plots):
        crop = ("patisson", "patisson", "carrot", "tomato", "wheat", "patisson")[i % 6]
        app.farm.plant(plot, crop)
        plot.progress = min(1.0, 0.30 + (i % 7) * 0.12)
        plot.water = 0.8
        plot.food = 0.7
        app.farm._refresh_model(plot)
    st.tool_index = 1
    st.water = 8.0
    look_at(app.player, (0.5, 3.0, 0.35), (-2.2, -2.6, gz(-2.2, -2.6)))
    shot("02-crops.png", hour=10.5)

    # 3. Close on a ripe patisson.
    ripe = app.farm.plots[0]
    app.farm.plant(ripe, "patisson")
    ripe.progress = 1.0
    ripe.water, ripe.food, ripe.health = 0.9, 0.8, 1.0
    app.farm._refresh_model(ripe)
    st.tool_index = 4
    look_at(app.player, (ripe.x, ripe.y, ripe.z + 0.30),
            (ripe.x - 1.5, ripe.y - 1.5, gz(ripe.x - 1.5, ripe.y - 1.5)))
    shot("03-patisson-ripe.png", hour=12.0)

    # 4. The pond, from the reeds.
    from ..world.terrain import POND_CENTRE
    px, py = POND_CENTRE
    cx, cy = px + 13.0, py - 13.0
    look_at(app.player, (px, py, cfg.world.water_level), (cx, cy, gz(cx, cy)))
    st.tool_index = 3
    shot("04-pond.png", hour=15.0, weather="clear")

    # 5. The well and the house.
    look_at(app.player, (7.5, 7.0, 1.4), (12.0, 0.5, gz(12.0, 0.5)))
    shot("05-well.png", hour=9.0)

    look_at(app.player, (16.0, -13.0, 2.4), (7.0, -20.0, gz(7.0, -20.0)))
    shot("06-house.png", hour=17.0)

    # 6. Barn, cows and chickens.
    look_at(app.player, (-19.0, -14.0, 2.0), (-8.0, -22.0, gz(-8.0, -22.0)))
    shot("07-barn.png", hour=11.0)

    # 7. Market stall with a villager.
    look_at(app.player, (-13.0, -2.0, 1.4), (-7.0, -6.0, gz(-7.0, -6.0)))
    st.coins = 385
    st.give("patisson", 4)
    st.fish = 6
    shot("08-market.png", hour=14.0)

    # 8. Wide shot of the whole farm from the hillside.
    hx, hy = 34.0, -34.0
    look_at(app.player, (-6.0, 6.0, 0.0), (hx, hy, gz(hx, hy) + 7.0))
    shot("09-overview.png", hour=16.5)

    # 9. Golden hour and night.
    look_at(app.player, (-20.0, 16.0, 2.0), (6.0, -8.0, gz(6.0, -8.0)))
    shot("10-sunset.png", hour=19.6)

    look_at(app.player, (7.5, 7.0, 1.2), (2.0, -5.0, gz(2.0, -5.0)))
    shot("11-night.png", hour=23.0)

    # 10. Rain and the journal/shop UI.
    look_at(app.player, (0.0, 6.0, 0.4), (5.0, -5.0, gz(5.0, -5.0)))
    shot("12-rain.png", hour=13.0, weather="rain")

    app.hud.open_panel("shop")
    shot("13-shop.png", hour=13.0, weather="clear")
    app.hud.close_panel()

    # Kitchen: stock the bag so the recipe list shows real availability.
    from ..game.cooking import POT_POSITION
    for key, n in (("wheat", 5), ("egg", 3), ("milk", 2), ("pumpkin", 1),
                   ("patisson", 2), ("tomato", 1), ("carrot", 2)):
        st.give(key, n)
    st.fish = 3
    px, py = POT_POSITION
    app.player.pos.x, app.player.pos.y = px, py
    app.player.pos.z = gz(px, py)
    # Stand off to the side so the hearth, not the house wall, is the backdrop.
    look_at(app.player, (px, py, 0.5), (px - 3.4, py + 2.6, gz(px - 3.4, py + 2.6)))
    shot("14-hearth.png", hour=13.0)
    app.kitchen.index = 4
    app.hud.open_panel("kitchen")
    shot("15-kitchen.png", hour=13.0)
    app.hud.close_panel()

    app.hud.open_panel("journal")
    st.record("harvest", "patisson", 3)
    st.unlock("first_seed")
    st.unlock("first_harvest")
    app.hud.refresh_panel()
    shot("16-journal.png")
    app.hud.close_panel()

    # 11. Autumn, then winter. The clock has to move so the game loop agrees
    # with the season we're asking for.
    day = cfg.game.day_length
    season_len = day * cfg.game.season_days
    app.cycle.total_time += season_len * 2
    look_at(app.player, (-3.0, 13.0, 1.0), (11.0, -15.0, gz(11.0, -15.0) + 3.0))
    shot("17-autumn.png", hour=16.0, weather="clear")

    app.cycle.total_time += season_len
    look_at(app.player, (-4.0, 10.0, 0.5), (6.0, -10.0, gz(6.0, -10.0)))
    shot("18-winter.png", hour=12.0, weather="snow")

    # 12. Photo mode: the same view, path traced.
    app.cycle.total_time = day * 8 + 10.5 / 24.0 * day     # back to summer
    app.weather = "clear"
    look_at(app.player, (7.5, 7.0, 1.2), (2.0, -3.0, gz(2.0, -3.0)))
    settle(4)
    app.toggle_photo_mode()
    tracer = getattr(app, "pathtracer", None)
    if tracer:
        while tracer.samples < 320:
            app.taskMgr.step()
        shot("19-pathtraced.png")
        app.toggle_photo_mode()
    else:
        print("[shot] 19-pathtraced.png skipped (no compute support)", flush=True)

    print("done ->", out_dir, flush=True)
    sys.stdout.flush()
    os._exit(0)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    capture(out)


if __name__ == "__main__":
    main()

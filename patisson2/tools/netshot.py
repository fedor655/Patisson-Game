"""Photographs a hosted farm — the one shot the offline capture cannot take.

    python -X utf8 -m patisson2.tools.netshot [outdir]

Everything `shots.py` captures can be staged inside one process. Company
cannot: it needs a server with a world of its own, a client that reached
it over a socket, and other people standing on the ground. So this starts
a real server on a loopback port, joins it with the real game through the
same code path the menu uses, stands three visitors in the field and
takes the picture.

It is also the only check on two things no assertion reads well: that the
name over somebody's head is legible at farming distance, and that the
roster in the corner does not run off the edge of the screen.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from pathlib import Path

from ..config import Config

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "screenshots2"

# Where the visitors stand, and how far that is from the camera below.
VISITORS = ((901, "Борис", 3.5, 5.0),
            (902, "Марта", -5.5, 9.0),
            (903, "Пётр Алексеевич", 27.0, 24.0))

VIEW_FROM = (0.0, -7.0)
VIEW_HEADING, VIEW_PITCH = 0.0, -7.0
VIEW_HOUR = 10.5


class _Deaf:
    """A visitor the server can talk to and who never answers.

    Standing somebody on the farm without a socket is not enough any
    more: the first broadcast finds the write fails and drops them, which
    is right for a dead connection and useless for a stand-in.
    """

    def write(self, _data) -> None:
        pass

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        pass


def _start_server(holder: dict) -> None:
    from ..net.server import FarmServer

    async def go():
        server = FarmServer(save_path=None)
        holder["server"] = server
        tcp = await asyncio.start_server(server.serve_client, "127.0.0.1", 0)
        holder["port"] = tcp.sockets[0].getsockname()[1]
        async with tcp:
            await asyncio.gather(tcp.serve_forever(), server.run_ticks())

    try:
        asyncio.run(go())
    except Exception as exc:                                # noqa: BLE001
        holder["error"] = exc


def capture(out_dir: Path = DEFAULT_OUT, width: int = 1600,
            height: int = 900) -> Path:
    from panda3d.core import Filename, Vec3

    from ..app import PatissonApp, configure
    from ..net.server import Player

    holder: dict = {}
    threading.Thread(target=_start_server, args=(holder,),
                     daemon=True).start()
    for _ in range(200):
        if "port" in holder or "error" in holder:
            break
        time.sleep(0.05)
    if "port" not in holder:
        raise RuntimeError(f"сервер не поднялся: {holder.get('error')}")

    cfg = Config()
    cfg.graphics.width, cfg.graphics.height = width, height
    cfg.graphics.vsync = False
    configure(cfg, offscreen=True)
    app = PatissonApp(cfg, offscreen=True, audio=False, use_settings=False)

    app.settings["server"] = f"127.0.0.1:{holder['port']}"
    app.settings["player_name"] = "Фёдор"
    app.menu_join_server()
    for _ in range(400):
        app.taskMgr.step()
        if app.net is not None and app.net.online and app.net.client.snapshot:
            break
    if app.net is None or not app.net.online:
        raise RuntimeError("не удалось подключиться к своей же ферме")

    server = holder["server"]
    for pid, name, x, y in VISITORS:
        guest = Player(pid, name, _Deaf())
        guest.x, guest.y, guest.z = x, y, app.world.height_at(x, y)
        server.players[pid] = guest

    # The hour is set on the server, not here. On somebody else's farm the
    # clock is theirs: winding the local one just gets overwritten by the
    # next state message, and the picture comes out at whatever time the
    # server happened to be at.
    server.world.cycle.total_time = (
        server.world.cycle.day * cfg.game.day_length
        + VIEW_HOUR / 24.0 * cfg.game.day_length)
    app.player.frozen = True
    app.player.pos = Vec3(VIEW_FROM[0], VIEW_FROM[1],
                          app.world.height_at(*VIEW_FROM))
    app.player.heading, app.player.pitch = VIEW_HEADING, VIEW_PITCH
    for _ in range(240):
        app.taskMgr.step()
    # The join notice has done its job; it would only date the picture.
    app.state.notifications.clear()
    for _ in range(3):
        app.taskMgr.step()

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "21-multiplayer.jpg"
    app.graphicsEngine.renderFrame()
    app.graphicsEngine.renderFrame()
    app.win.saveScreenshot(Filename.fromOsSpecific(str(path)))
    print(f"снято: {path}", flush=True)
    print(app.hud.players_text.getText(), flush=True)
    return path


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    capture(out)
    sys.stdout.flush()
    # The server thread has its own event loop and no reason to be asked
    # politely: the picture is on disk.
    os._exit(0)


if __name__ == "__main__":
    main()

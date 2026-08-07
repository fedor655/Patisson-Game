"""Телефонный клиент целиком: экран подключения, ферма, касания.

    python -X utf8 -m patisson2.tools.phone_check

Отдельным процессом, потому что Kivy создаёт окно и забирает его себе,
а общий прогон проверок живёт в Panda3D. Здесь поднимается настоящий
сервер на локальном порту, приложение проходит путь игрока — вписать
адрес, нажать «На ферму», ткнуть в грядку — и всё это проверяется.

Появилось после того, как выяснилось, что адрес фермы телефон брал из
аргументов командной строки. На телефоне их нет: приложение всегда
стучалось в 127.0.0.1, где ничего нет и быть не может, — то есть
подключиться к ферме с телефона было нельзя вообще никак, и ни одна
проверка этого не замечала.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time

os.environ.setdefault("KIVY_NO_ARGS", "1")


def start_server(holder: dict) -> None:
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


def main() -> int:
    holder: dict = {}
    threading.Thread(target=start_server, args=(holder,), daemon=True).start()
    for _ in range(200):
        if "port" in holder or "error" in holder:
            break
        time.sleep(0.05)
    if "port" not in holder:
        print(f"сервер не поднялся: {holder.get('error')}", flush=True)
        return 1

    from kivy.base import EventLoop
    from kivy.core.window import Window

    Window.size = (430, 860)

    from ..mobile.main import PatissonMobile, load_settings, save_settings

    problems: list[str] = []
    app = PatissonMobile()
    EventLoop.ensure_window()
    app._run_prepare()

    def pump(times: int = 40) -> None:
        for _ in range(times):
            EventLoop.idle()
            time.sleep(0.01)

    pump()
    if app.link is not None:
        problems.append("приложение полезло на ферму, не спросив адреса")
    if not hasattr(app, "host_input"):
        problems.append("экрана подключения нет")
        print("; ".join(problems), flush=True)
        return 1

    # Пустой адрес — не повод молча никуда не пойти.
    app.host_input.text = "   "
    app._connect()
    pump(4)
    if app.link is not None:
        problems.append("с пустым адресом всё равно полезли подключаться")

    app.host_input.text = f"127.0.0.1:{holder['port']}"
    app.player_name_input.text = "Проверка"
    app._connect()
    for _ in range(300):
        EventLoop.idle()
        time.sleep(0.02)
        if app.link is not None and app.link.status == "online" \
                and app.link.plots:
            break
    if app.link is None or app.link.status != "online":
        problems.append(f"не подключились: "
                        f"{app.link and app.link.error}")
    else:
        if len(app.link.plots) != 24:
            problems.append(f"грядок пришло {len(app.link.plots)}")
        if not app.link.layout:
            problems.append("координаты грядок не пришли")

        # Касание по грядке должно доехать до фермы.
        server = holder["server"]
        server.world.state.inventory["seed_patisson"] = 3
        app.view.tool = 2                       # семена
        app.view.crop = 0                       # патиссон
        # Настоящее касание: находим грядку на экране тем же
        # преобразованием, каким её рисуют, и жмём туда пальцем.
        wx, wy, _wz = app.link.layout[0]
        point = app.view.to_screen(wx, wy)
        if app.view.bed_at(*point) != 0:
            problems.append(f"палец в грядку 0 попал в "
                            f"{app.view.bed_at(*point)}")

        class Touch:
            def __init__(self, pos):
                self.pos = pos

        app.view.on_touch_down(Touch(point))
        for _ in range(200):
            EventLoop.idle()
            time.sleep(0.02)
            if server.world.farm.plots[0].crop:
                break
        if not server.world.farm.plots[0].crop:
            problems.append("касание по грядке не доехало до фермы")
        if server.world.state.count("seed_patisson") != 2:
            problems.append("семечко не списалось с общего амбара")

        # Адрес запоминается, иначе набирать его каждый раз.
        saved = load_settings()
        if saved.get("host") != "127.0.0.1":
            problems.append(f"адрес не запомнился: {saved}")
        if saved.get("name") != "Проверка":
            problems.append(f"имя не запомнилось: {saved}")

    save_settings({})
    if problems:
        print("; ".join(problems), flush=True)
        return 1
    print("телефон: экран подключения, ферма, касание и память адреса — "
          "всё сходится", flush=True)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)

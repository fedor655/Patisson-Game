"""Two people on one farm, checked end to end.

    python -m patisson2.tools.net_check

Starts a real server on a loopback port and talks to it over a real
socket with the real protocol — no stubs, because the parts worth
doubting are exactly the ones a stub would paper over: framing, the
handshake, whether one player's watering can reaches the other player's
screen, and whether the farm survives someone yanking the cable.

Panda3D is never imported here. A hosted farm has no renderer, and this
is the proof that it does not need one.
"""

from __future__ import annotations

import asyncio
import sys

from ..net import protocol
from ..net.server import FarmServer


class Client:
    """The smallest thing that can be called a player."""

    def __init__(self, name: str):
        self.name = name
        self.id = None
        self.world = None
        self.plots: dict[int, dict] = {}
        self.coins = 0
        self.lines: list[str] = []
        self.reader = self.writer = None

    async def connect(self, port: int, version: int | None = None):
        self.reader, self.writer = await asyncio.open_connection(
            "127.0.0.1", port)
        hello = protocol.hello(self.name)
        if version is not None:
            hello["v"] = version
        await protocol.write_message(self.writer, hello)
        first = await protocol.read_message(self.reader)
        if first.get("t") == "welcome":
            self.id = first["id"]
            self.world = first["world"]
            self.plots = {p["i"]: p for p in self.world["plots"]}
            self.coins = self.world["coins"]
        return first

    async def pump(self, seconds: float = 0.6):
        """Read whatever the server has to say for a while."""
        end = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end:
            try:
                left = end - asyncio.get_event_loop().time()
                message = await asyncio.wait_for(
                    protocol.read_message(self.reader), timeout=max(left, 0.01))
            except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                break
            if message.get("t") == "state":
                for plot in message.get("plots", []):
                    self.plots[plot["i"]] = plot
                self.coins = message.get("coins", self.coins)
            elif message.get("t") == "event":
                self.lines.extend(message.get("lines", []))

    async def act(self, action, plot=None, arg=None):
        await protocol.write_message(self.writer,
                                     protocol.act(action, plot, arg))

    async def close(self):
        if self.writer is not None:
            self.writer.close()


async def run() -> int:
    server = FarmServer(save_path=None)
    tcp = await asyncio.start_server(server.serve_client, "127.0.0.1", 0)
    port = tcp.sockets[0].getsockname()[1]
    ticker = asyncio.ensure_future(server.run_ticks())
    problems: list[str] = []
    try:
        # --- an old client must be told why, not left hanging ----------
        stale = Client("Старая версия")
        answer = await stale.connect(port, version=protocol.PROTOCOL_VERSION + 99)
        if answer.get("t") != "bye" or "Обновите" not in answer.get("reason", ""):
            problems.append(f"старую версию пустили на ферму: {answer}")
        await stale.close()

        # --- two players join -----------------------------------------
        anna, boris = Client("Анна"), Client("Борис")
        await anna.connect(port)
        await boris.connect(port)
        if anna.id == boris.id:
            problems.append("двум игрокам выдан один номер")
        if not anna.world or len(anna.world["plots"]) != 24:
            problems.append(f"в снимке мира {len(anna.world or {})} грядок")
        await anna.pump(0.3)
        await boris.pump(0.3)
        if not any("Борис" in line for line in anna.lines):
            problems.append(f"Анна не увидела прихода Бориса: {anna.lines}")

        # --- one plants and waters, the other must see it --------------
        # An empty bed refuses the watering can on purpose -- you water
        # plants, not dirt -- so something has to be growing there first.
        bed = 0
        await anna.act("plant", bed, "patisson")
        await asyncio.sleep(0.4)
        await boris.pump(0.6)
        if boris.plots[bed]["crop"] != "patisson":
            problems.append(f"посадка Анны не дошла до Бориса: "
                            f"{boris.plots[bed]}")
        server.world.farm.plots[bed].water = 0.0
        await asyncio.sleep(0.3)
        await boris.pump(0.4)
        before = boris.plots[bed]["w"]
        await anna.act("water", bed)
        await asyncio.sleep(0.4)
        await boris.pump(0.6)
        after = boris.plots[bed]["w"]
        if after <= before:
            problems.append(f"полив Анны не дошёл до Бориса: "
                            f"{before} -> {after}")

        # --- and money is shared ---------------------------------------
        server.world.state.give("patisson", 2)
        coins_before = server.world.state.coins
        await boris.act("sell")
        await asyncio.sleep(0.4)
        await anna.pump(0.6)
        if server.world.state.coins <= coins_before:
            problems.append("продажа не принесла денег")
        if anna.coins != server.world.state.coins:
            problems.append(f"у Анны {anna.coins} монет, на сервере "
                            f"{server.world.state.coins}")

        # --- one leaves; the farm carries on ---------------------------
        await boris.close()
        await asyncio.sleep(0.5)
        if len(server.players) != 1:
            problems.append(f"после ухода осталось {len(server.players)} "
                            f"игроков вместо 1")
        await anna.act("plant", 1, "carrot")
        await asyncio.sleep(0.3)
        await anna.pump(0.4)
        if server.world.farm.plots[1].crop != "carrot":
            problems.append("после чужого обрыва сервер перестал слушать")

        # --- an empty farm must not rot --------------------------------
        await anna.close()
        await asyncio.sleep(0.4)
        day_before = server.world.cycle.total_time
        await asyncio.sleep(0.8)
        if server.world.cycle.total_time != day_before:
            problems.append("пустая ферма продолжает тикать — вороны "
                            "склюют урожай, пока никого нет")

        # --- and the client the game actually uses agrees too ----------
        problems.extend(await check_real_client(server, port))
        problems.extend(await check_phone(server, port))
        problems.extend(check_restart())
        problems.extend(await check_rubbish(port))
        problems.extend(await check_broken_connection(server, port))
    finally:
        ticker.cancel()
        tcp.close()

    for line in problems:
        print(f"  ! {line}", flush=True)
    if problems:
        return 1
    print("сеть: рукопожатие, снимок мира, чужой полив, общий кошелёк, "
          "обрыв, покой пустой фермы, клиент игры, телефон, "
          "перезапуск сервера и мусор в сокете — всё сходится",
          flush=True)
    return 0


async def check_real_client(server, port: int) -> list[str]:
    """The client the game actually uses: its own thread, its own queues.

    It has to reach the farm, receive the world, hand the beds to a local
    Farm so the models appear, and send an intent that the server acts on.
    """
    from ..net import client as netclient
    from ..net.world import SharedWorld

    problems: list[str] = []
    conn = netclient.NetClient("127.0.0.1", port, name="Клиент")
    # Waiting synchronously here would block the loop the server runs on,
    # and it would never get round to accepting the connection.
    for _ in range(400):
        if conn.status != "connecting":
            break
        await asyncio.sleep(0.02)
    if conn.status != "online":
        return [f"настоящий клиент не подключился: {conn.status} {conn.error}"]

    # A local farm to paint the server's numbers onto, headless.
    local = SharedWorld()
    if conn.snapshot:
        netclient.apply_state(local.farm, conn.snapshot, local.state,
                              local.cycle)
    server.world.farm.plant(server.world.farm.plots[5], "tomato")
    await asyncio.sleep(0.5)
    for message in conn.poll():
        if message.get("t") == "state":
            netclient.apply_state(local.farm, message, local.state,
                                  local.cycle)
    if local.farm.plots[5].crop != "tomato":
        problems.append(f"клиент не увидел чужую посадку: "
                        f"{local.farm.plots[5].crop}")

    # The shared barn starts with patissons and carrots and no wheat, and
    # the server is right to refuse seeds nobody owns -- so buy one first.
    server.world.state.give("seed_wheat", 1)
    conn.act("plant", 6, "wheat")
    await asyncio.sleep(0.5)
    if server.world.farm.plots[6].crop != "wheat":
        problems.append("сервер не принял намерение клиента")
    if server.world.state.inventory.get("seed_wheat"):
        problems.append("семя посадили, а из амбара оно не списалось")

    coins_before = local.state.coins
    server.world.state.give("patisson", 1)
    server.world.state.sell_all()
    await asyncio.sleep(0.5)
    for message in conn.poll():
        if message.get("t") == "state":
            netclient.apply_state(local.farm, message, local.state,
                                  local.cycle)
    if local.state.coins <= coins_before:
        problems.append(f"кошелёк не доехал до клиента: "
                        f"{coins_before} -> {local.state.coins}")
    conn.close()
    return problems


async def check_phone(server, port: int) -> list[str]:
    """The phone talks to the same farm, over the same wire.

    The mobile link is deliberately a separate, smaller implementation:
    a phone has no Panda3D, no numpy and no room for the whole game, so
    it shares the message format and nothing else. Which means it can
    drift from the server, and this is what catches it if it does.
    """
    from ..mobile.link import FarmLink

    problems: list[str] = []
    phone = FarmLink("127.0.0.1", port, name="Телефон")
    for _ in range(400):
        phone.pump()
        if phone.status != "connecting":
            break
        await asyncio.sleep(0.02)
    if phone.status != "online":
        return [f"телефон не подключился: {phone.status} {phone.error}"]
    if len(phone.plots) != 24 or len(phone.layout) != 24:
        problems.append(f"телефону пришло {len(phone.plots)} грядок и "
                        f"{len(phone.layout)} координат вместо 24")

    server.world.farm.plant(server.world.farm.plots[7], "carrot")
    for _ in range(60):
        phone.pump()
        if phone.plots.get(7, {}).get("crop") == "carrot":
            break
        await asyncio.sleep(0.02)
    if phone.plots.get(7, {}).get("crop") != "carrot":
        problems.append("телефон не увидел чужую посадку")

    server.world.farm.plots[7].water = 0.0
    phone.act("water", 7)
    for _ in range(60):
        phone.pump()
        if server.world.farm.plots[7].water > 0.0:
            break
        await asyncio.sleep(0.02)
    if server.world.farm.plots[7].water <= 0.0:
        problems.append("ферма не получила полив с телефона")

    # Амбар на общей ферме общий, и телефон должен видеть именно его:
    # без этого «Семена» и «Удобрить» — кнопки, которые иногда молча
    # ничего не делают, потому что класть в землю нечего.
    server.world.state.inventory["seed_wheat"] = 7
    server.world.state.inventory["fertilizer"] = 3
    for _ in range(60):
        phone.pump()
        if phone.inventory.get("seed_wheat") == 7:
            break
        await asyncio.sleep(0.02)
    if phone.inventory.get("seed_wheat") != 7:
        problems.append(f"телефон не увидел амбар фермы: "
                        f"{phone.inventory}")
    if phone.inventory.get("fertilizer") != 3:
        problems.append("телефон не увидел удобрение")

    # Состояние пугала решает ферма — телефон только рисует ответ.
    crow = server.world.pests.scarecrow
    crow.condition = 1.0
    for _ in range(60):
        phone.pump()
        if not phone.crow_fix:
            break
        await asyncio.sleep(0.02)
    if phone.crow_fix or not phone.crow_ok:
        problems.append("целое пугало телефон считает сломанным")
    crow.condition = 0.1
    for _ in range(60):
        phone.pump()
        if not phone.crow_ok:
            break
        await asyncio.sleep(0.02)
    if phone.crow_ok or not phone.crow_fix:
        problems.append("упавшее пугало телефон считает целым "
                        f"({phone.scarecrow})")
    crow.condition = 1.0
    if phone.clock.get("season") is None:
        problems.append("на телефон не пришли часы фермы")
    phone.close()
    return problems

def check_restart() -> list[str]:
    """A hosted farm has to outlive the process holding it.

    People leave crops in the ground and expect to find them there next
    week. The server wrote the world to disk from the start but never
    read it back, so every restart quietly handed everyone a fresh farm —
    which is worse than not saving at all, because it looks like it
    worked.
    """
    import tempfile
    from pathlib import Path

    from ..net.server import FarmServer

    problems: list[str] = []
    save = Path(tempfile.mkdtemp(prefix="patisson-world-")) / "world.json"
    before = FarmServer(save_path=save)
    before.world.farm.plant(before.world.farm.plots[3], "pumpkin")
    before.world.farm.plots[3].progress = 0.7
    before.world.state.coins = 777
    before.world.state.give("patisson", 4)
    before.world.cycle.total_time = before.world.cfg.game.day_length * 5.25
    before.world.pests.scarecrow.condition = 0.42
    before.save()

    after = FarmServer(save_path=save)
    bed = after.world.farm.plots[3]
    if bed.crop != "pumpkin" or abs(bed.progress - 0.7) > 0.01:
        problems.append(f"после перезапуска грядка стала {bed.crop} "
                        f"{bed.progress:.2f} вместо pumpkin 0.70")
    if after.world.state.coins != 777:
        problems.append(f"после перезапуска {after.world.state.coins} монет "
                        f"вместо 777")
    if after.world.state.inventory.get("patisson") != 4:
        problems.append("после перезапуска пропал урожай из амбара")
    if after.world.cycle.day != 5:
        problems.append(f"после перезапуска день {after.world.cycle.day + 1} "
                        f"вместо 6")
    if abs(after.world.pests.scarecrow.condition - 0.42) > 0.01:
        problems.append("после перезапуска пугало снова как новое")
    return problems


async def check_rubbish(port: int) -> list[str]:
    """Somebody will point something that is not the game at this port.

    None of it may take the farm down with it, and a real player must
    still be able to join afterwards.
    """
    problems: list[str] = []
    rubbish = [
        ("случайные байты", bytes([0, 1, 2, 3]) + b"hello"),
        ("огромный размер", (10 ** 7).to_bytes(4, "big") + b"x" * 10),
        ("не JSON", (5).to_bytes(4, "big") + b"{{{{{"),
        ("не объект", (3).to_bytes(4, "big") + b"[1]"),
        ("обрыв на середине", (100).to_bytes(4, "big") + b"abc"),
    ]
    for name, payload in rubbish:
        try:
            _r, w = await asyncio.open_connection("127.0.0.1", port)
            w.write(payload)
            await w.drain()
            await asyncio.sleep(0.15)
            w.close()
        except OSError as exc:
            problems.append(f"сервер отказал на «{name}»: {exc}")
            return problems
    guest = Client("После мусора")
    answer = await guest.connect(port)
    if answer.get("t") != "welcome":
        problems.append(f"после мусора живой игрок не зашёл: {answer}")
    await guest.close()
    return problems

async def check_broken_connection(server, port: int) -> list[str]:
    """Одна испорченная связь не должна останавливать мир для всех.

    Рассылка ловила два вида ошибок. Любая другая — сокет в состоянии,
    которого никто не ждал, — уходила в тик-цикл, а он собран вместе со
    слушателем: значит, одно битое соединение останавливало ферму для
    всех, кто на ней ещё играл. Потерянный тик — это икота, потерянный
    цикл — конец сессии.
    """
    from ..net.server import Player

    problems: list[str] = []
    guest = Client("Живой")
    await guest.connect(port)
    server.players[9999] = Player(9999, "Призрак", None)
    before = server.world.cycle.total_time
    await asyncio.sleep(0.8)
    if 9999 in server.players:
        problems.append("сломанное соединение осталось в списке игроков")
    if server.world.cycle.total_time <= before:
        problems.append("после сломанного соединения часы фермы встали")
    await guest.act("plant", 11, "patisson")
    await asyncio.sleep(0.4)
    if server.world.farm.plots[11].crop != "patisson":
        problems.append("после сломанного соединения сервер перестал слушать живых")
    await guest.close()
    return problems

def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())

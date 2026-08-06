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
    finally:
        ticker.cancel()
        tcp.close()

    for line in problems:
        print(f"  ! {line}", flush=True)
    if problems:
        return 1
    print("сеть: рукопожатие, снимок мира, чужой полив, общий кошелёк, "
          "обрыв и покой пустой фермы — всё сходится", flush=True)
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())

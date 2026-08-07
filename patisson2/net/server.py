"""A farm several people can work at once.

    python -m patisson2.net.server --port 7777

The server owns the world. Clients say what they would like to do and
this decides what happened — a bed is watered, a patisson is picked, the
money goes up — and tells everyone. Nothing about crop growth is trusted
to a client, because two machines running the same clock still drift, and
a farm that disagrees with itself is worse than no farm at all.

Two things learned from watching the simulation run on its own:

* **A farm nobody is standing on does not rot.** Left ticking with no
  players, the scarecrow fell apart in a day and a half and the crows
  stripped every ripe bed — nobody was there to mend it. The world only
  advances while somebody is connected.
* **Everything shared is shared.** One purse, one set of beds, one set of
  quests. Two players watering the same bed is not a conflict; both
  presses land, the second finds it already wet.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from . import protocol
from .world import SharedWorld

TICK_HZ = 15.0
SAVE_EVERY = 60.0          # seconds of real time between writes to disk
DEFAULT_SAVE = Path.home() / ".patisson2" / "server-world.json"

# What a client may ask for, and what it costs the world. Anything not in
# here is refused -- the list is the whole surface a stranger on the port
# can reach.
PLOT_ACTIONS = ("water", "weed", "cure", "feed", "harvest", "plant")


class Player:
    """One person on the farm, as the server sees them."""

    __slots__ = ("id", "name", "writer", "x", "y", "z", "heading", "pitch",
                 "joined")

    def __init__(self, player_id: int, name: str, writer):
        self.id = player_id
        self.name = name
        self.writer = writer
        self.x = self.y = self.z = 0.0
        self.heading = self.pitch = 0.0
        self.joined = time.monotonic()

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name,
                "p": [round(self.x, 2), round(self.y, 2), round(self.z, 2)],
                "h": round(self.heading, 1)}


class FarmServer:
    def __init__(self, save_path: Path | None = None, load: bool = True):
        self.world = SharedWorld()
        self.players: dict[int, Player] = {}
        self._next_id = 1
        self.tick = 0
        self.save_path = Path(save_path) if save_path else DEFAULT_SAVE
        self._last_save = time.monotonic()
        self._last_plots: list[dict] = []
        self._last_inventory: dict = {}
        self._pending: list[str] = []
        # People leave crops in the ground and expect to find them there
        # next week. Writing the world without reading it back would hand
        # everyone a fresh farm on every restart — worse than not saving
        # at all, because it looks like it worked.
        if load and save_path is not None:
            self.load()

    # ------------------------------------------------------------ the world

    def plot_dict(self, index: int) -> dict:
        p = self.world.farm.plots[index]
        return {"i": index, "crop": p.crop,
                "pr": round(p.progress, 3), "w": round(p.water, 2),
                "f": round(p.food, 2), "hp": round(p.health, 2),
                "wd": round(p.weeds, 2), "bl": round(p.blight, 2),
                "t": bool(p.tilled)}

    def snapshot(self) -> dict:
        st = self.world.state
        return {
            "plots": [self.plot_dict(i)
                      for i in range(len(self.world.farm.plots))],
            "layout": [[round(p.x, 2), round(p.y, 2), round(p.z, 2)]
                       for p in self.world.farm.plots],
            "clock": self.clock_dict(),
            "coins": st.coins,
            "inventory": dict(st.inventory),
            "players": [p.as_dict() for p in self.players.values()],
            **self.crow_dict(),
        }

    def crow_dict(self) -> dict:
        """The scarecrow, as two questions a client cannot get wrong.

        The number alone left everyone to invent their own idea of
        "needs mending", and the phone's idea would drift from the rule
        the server actually applies when the button is pressed.
        """
        crow = self.world.pests.scarecrow
        return {"scarecrow": round(crow.condition, 2),
                "crow_ok": bool(crow.working),
                "crow_fix": bool(crow.needs_repair)}

    def clock_dict(self) -> dict:
        c = self.world.cycle
        return {"day": c.day, "hour": round(c.hour, 2), "season": c.season,
                "weather": self.world.weather}

    # --------------------------------------------------------- what changed

    def deltas(self) -> dict:
        """Only what moved since the last tick — the farm is mostly still."""
        changes: dict = {}
        plots = [self.plot_dict(i) for i in range(len(self.world.farm.plots))]
        if self._last_plots:
            moved = [new for old, new in zip(self._last_plots, plots)
                     if old != new]
            if moved:
                changes["plots"] = moved
        else:
            changes["plots"] = plots
        self._last_plots = plots
        changes["clock"] = self.clock_dict()
        changes["coins"] = self.world.state.coins
        changes["players"] = [p.as_dict() for p in self.players.values()]
        changes.update(self.crow_dict())
        # The barn is shared, so it is the farm's business what is in it.
        # It was sent once, at the door, and never again: every client
        # then showed the stock it had joined with, and a player could
        # look at three seeds that had been planted by somebody else an
        # hour ago. It moves rarely, so it is sent when it moves.
        inventory = dict(self.world.state.inventory)
        if inventory != self._last_inventory:
            changes["inv"] = inventory
            self._last_inventory = inventory
        return changes

    # -------------------------------------------------------------- actions

    def handle_act(self, player: Player, message: dict) -> None:
        action = message.get("a")
        farm, st = self.world.farm, self.world.state
        if action in PLOT_ACTIONS:
            index = message.get("plot")
            if not isinstance(index, int) or not (
                    0 <= index < len(farm.plots)):
                return
            plot = farm.plots[index]
            if action == "water":
                farm.water_plot(plot)
            elif action == "weed":
                farm.weed(plot)
            # The stock is checked, the bed is asked, and only then is
            # anything spent. Taking first and acting after cost the farm
            # an item every time the answer was no -- and on a shared farm
            # the answer is often no through no fault of the person
            # clicking: two people plant the same bed in the same tick and
            # the loser pays a seed for nothing out of everybody's barn.
            elif action == "cure":
                if st.count("ash") and farm.cure(plot):
                    st.take("ash")
            elif action == "feed":
                if st.count("fertilizer") and farm.feed_plot(plot):
                    st.take("fertilizer")
            elif action == "plant":
                crop = message.get("arg")
                if (crop and st.count(f"seed_{crop}")
                        and farm.plant(plot, crop)):
                    st.take(f"seed_{crop}")
            elif action == "harvest":
                got = farm.harvest(plot, st.upgrades.harvest_bonus)
                if got:
                    st.give(got[0], got[1])
                    st.record("harvest", got[0], got[1])
                    self._pending.append(
                        f"{player.name}: собрано {got[0]} x{got[1]}")
        elif action == "sell":
            sold = st.sell_all()
            if sold:
                self._pending.append(f"{player.name} продал урожай: +{sold}")
        elif action == "buy":
            key = message.get("arg")
            if key:
                st.buy(key)
        elif action == "repair":
            if self.world.pests.scarecrow.repair():
                self._pending.append(f"{player.name} поправил пугало")

    # ----------------------------------------------------------- connection

    async def serve_client(self, reader, writer) -> None:
        peer = writer.get_extra_info("peername")
        player = None
        try:
            hello = await asyncio.wait_for(
                protocol.read_message(reader), timeout=15.0)
            if hello.get("t") != "hello":
                await protocol.write_message(
                    writer, protocol.bye("Первым сообщением должно быть hello"))
                return
            if hello.get("v") != protocol.PROTOCOL_VERSION:
                await protocol.write_message(
                    writer, protocol.version_error(hello.get("v")))
                return

            player = Player(self._next_id, str(hello.get("name", "Фермер")),
                            writer)
            self._next_id += 1
            self.players[player.id] = player
            print(f"[+] {player.name} (#{player.id}) с {peer}, "
                  f"на ферме {len(self.players)}", flush=True)
            await protocol.write_message(
                writer, protocol.welcome(player.id, self.snapshot()))
            self._pending.append(f"{player.name} пришёл на ферму")

            while True:
                message = await protocol.read_message(reader)
                kind = message.get("t")
                if kind == "move":
                    pos = message.get("p") or [0, 0, 0]
                    if isinstance(pos, list) and len(pos) == 3:
                        player.x, player.y, player.z = (
                            float(pos[0]), float(pos[1]), float(pos[2]))
                    player.heading = float(message.get("h", 0.0))
                    player.pitch = float(message.get("pi", 0.0))
                elif kind == "act":
                    self.handle_act(player, message)
                elif kind == "bye":
                    break
        except (asyncio.IncompleteReadError, ConnectionResetError,
                asyncio.TimeoutError):
            pass
        except protocol.ProtocolError as exc:
            print(f"[!] {peer}: {exc}", flush=True)
        finally:
            if player is not None:
                self.players.pop(player.id, None)
                self._pending.append(f"{player.name} ушёл с фермы")
                print(f"[-] {player.name} (#{player.id}) отключился, "
                      f"на ферме {len(self.players)}", flush=True)
            writer.close()

    async def broadcast(self, message: dict) -> None:
        """Tell everyone, and let no single connection take the farm down.

        This used to catch two kinds of failure. Anything else -- a socket
        in a state nobody expected, a half-closed handle -- escaped into
        the tick loop, and since the loop is gathered with the listener,
        one bad connection stopped the world for everybody still playing.
        A broken pipe is that player's problem; it is not the farm's.
        """
        dead = []
        for player in list(self.players.values()):
            try:
                await protocol.write_message(player.writer, message)
            except Exception as exc:                        # noqa: BLE001
                print(f"[!] {player.name} (#{player.id}) отвалился: "
                      f"{type(exc).__name__}", flush=True)
                dead.append(player.id)
        for pid in dead:
            self.players.pop(pid, None)

    # ------------------------------------------------------------- the loop

    async def run_ticks(self) -> None:
        step = 1.0 / TICK_HZ
        while True:
            await asyncio.sleep(step)
            self.tick += 1
            if not self.players:
                # A farm nobody is standing on does not rot: left running
                # empty, the scarecrow fell apart and the crows stripped
                # every ripe bed with nobody there to mend it.
                continue
            try:
                events = self.world.update(step)
                if events:
                    self._pending.extend(events)
                await self.broadcast(protocol.state(self.tick, self.deltas()))
                if self._pending:
                    await self.broadcast(protocol.events(self._pending))
                    self._pending.clear()
                if time.monotonic() - self._last_save > SAVE_EVERY:
                    self.save()
            except asyncio.CancelledError:
                raise
            except Exception as exc:                        # noqa: BLE001
                # The tick loop is gathered with the listener, so an
                # exception here does not just skip a frame -- it stops the
                # world for everyone still on the farm. Losing one tick is
                # a hiccup; losing the loop is the end of the session.
                print(f"[!] тик пропущен: {type(exc).__name__}: {exc}",
                      flush=True)

    def load(self) -> bool:
        """Read the shared world back, or start a new farm."""
        try:
            raw = self.save_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[!] сохранённый мир не читается ({exc}) — начинаю новый",
                  flush=True)
            return False
        self.world.from_dict(data)
        self._last_plots = []          # everyone gets a full snapshot
        self._last_inventory = {}
        print(f"мир загружен: день {self.world.cycle.day + 1}, "
              f"{self.world.state.coins} мон.", flush=True)
        return True

    def save(self) -> None:
        self._last_save = time.monotonic()
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            self.save_path.write_text(
                json.dumps(self.world.to_dict(), ensure_ascii=False),
                encoding="utf-8")
        except OSError as exc:
            print(f"[!] мир не сохранился: {exc}", flush=True)


async def main_async(host: str, port: int, save: Path | None) -> None:
    server = FarmServer(save)
    tcp = await asyncio.start_server(server.serve_client, host, port)
    where = ", ".join(str(s.getsockname()) for s in tcp.sockets)
    print(f"Ферма открыта на {where} (протокол v{protocol.PROTOCOL_VERSION}, "
          f"{TICK_HZ:.0f} тиков/с)", flush=True)
    async with tcp:
        await asyncio.gather(tcp.serve_forever(), server.run_ticks())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Выделенный сервер «Патиссон гейм»")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=protocol.DEFAULT_PORT)
    parser.add_argument("--save", default=None,
                        help="куда писать общий мир")
    args = parser.parse_args(argv)
    try:
        asyncio.run(main_async(args.host, args.port,
                               Path(args.save) if args.save else None))
    except KeyboardInterrupt:
        print("\nферма закрыта", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

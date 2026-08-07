"""Talking to a hosted farm from inside the game.

The renderer owns the main loop and will not give it up, so the socket
lives on its own thread with two queues between it and the game: one for
what the player wants to do, one for what the farm says happened. The
game never blocks on the network — a frame drawn while the server is
quiet is simply a frame with no news in it.

Applying that news is the other half of this module. The server sends
beds as plain numbers; `apply_state` writes them onto a real Farm so the
same models, the same wilting and the same weed tufts appear as in a
single-player game. Only the fields the server owns are copied: it
decides how crops grow, and the client decides nothing.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time

from . import protocol

# How long to wait for a farm to answer before giving up on it.
CONNECT_TIMEOUT = 8.0


class NetClient:
    """A connection to a farm, safe to poke from the render thread."""

    def __init__(self, host: str, port: int = protocol.DEFAULT_PORT,
                 name: str = "Фермер"):
        self.host, self.port, self.name = host, port, name
        self.status = "connecting"      # connecting | online | failed | closed
        self.error: str | None = None
        self.player_id: int | None = None
        self.snapshot: dict | None = None

        self._inbox: queue.Queue = queue.Queue()
        self._outbox: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="patisson-net",
                                        daemon=True)
        self._thread.start()

    # ------------------------------------------------------- render thread

    def poll(self) -> list[dict]:
        """Everything the farm has said since the last frame."""
        out = []
        while True:
            try:
                out.append(self._inbox.get_nowait())
            except queue.Empty:
                return out

    def send(self, message: dict) -> None:
        if self.status in ("connecting", "online"):
            self._outbox.put(message)

    def act(self, action: str, plot: int | None = None,
            arg: str | None = None) -> None:
        self.send(protocol.act(action, plot, arg))

    def move(self, pos, heading: float, pitch: float) -> None:
        self.send(protocol.move(pos.x, pos.y, pos.z, heading, pitch))

    def close(self) -> None:
        self._stop.set()
        self.status = "closed"

    @property
    def online(self) -> bool:
        return self.status == "online"

    # ------------------------------------------------------- socket thread

    def _run(self) -> None:
        try:
            asyncio.run(self._session())
        except Exception as exc:                     # noqa: BLE001
            self._fail(str(exc))

    def _fail(self, reason: str) -> None:
        self.error = reason
        self.status = "failed"
        self._inbox.put({"t": "bye", "reason": reason})

    async def _session(self) -> None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=CONNECT_TIMEOUT)
        except (OSError, asyncio.TimeoutError) as exc:
            self._fail(f"Ферма не отвечает: {exc}")
            return

        try:
            await protocol.write_message(writer, protocol.hello(self.name))
            first = await asyncio.wait_for(protocol.read_message(reader),
                                           timeout=CONNECT_TIMEOUT)
            if first.get("t") == "bye":
                self._fail(first.get("reason", "Ферма отказала"))
                return
            if first.get("t") != "welcome":
                self._fail("Ферма ответила чем-то непонятным")
                return
            self.player_id = first.get("id")
            self.snapshot = first.get("world")
            self.status = "online"
            self._inbox.put(first)

            await asyncio.gather(self._pump_in(reader), self._pump_out(writer))
        except (asyncio.IncompleteReadError, ConnectionResetError):
            self._fail("Связь с фермой оборвалась")
        except protocol.ProtocolError as exc:
            self._fail(f"Ферма говорит не по-нашему: {exc}")
        finally:
            writer.close()
            if self.status == "online":
                self.status = "closed"

    async def _pump_in(self, reader) -> None:
        while not self._stop.is_set():
            message = await protocol.read_message(reader)
            self._inbox.put(message)

    async def _pump_out(self, writer) -> None:
        while not self._stop.is_set():
            try:
                message = self._outbox.get_nowait()
            except queue.Empty:
                await asyncio.sleep(1.0 / 30.0)
                continue
            await protocol.write_message(writer, message)


# ------------------------------------------------------------- applying

def apply_state(farm, message: dict, state=None, cycle=None) -> None:
    """Write what the server says onto a local farm.

    Only the fields the server owns are touched, and each changed bed is
    asked to refresh its model, so a crop that ripened on someone else's
    screen grows on this one too.
    """
    for row in message.get("plots", []):
        index = row.get("i")
        if not isinstance(index, int) or not 0 <= index < len(farm.plots):
            continue
        plot = farm.plots[index]
        was_crop, was_stage = plot.crop, plot.stage
        plot.crop = row.get("crop")
        plot.progress = float(row.get("pr", 0.0))
        plot.water = float(row.get("w", 0.0))
        plot.food = float(row.get("f", 0.0))
        plot.health = float(row.get("hp", 1.0))
        plot.weeds = float(row.get("wd", 0.0))
        plot.blight = float(row.get("bl", 0.0))
        plot.tilled = bool(row.get("t", True))
        if plot.crop is None:
            if was_crop is not None:
                farm._clear_model(plot)
                plot.stage = -1
        else:
            from ..game.farming import CROPS
            stage = farm._stage_for(CROPS[plot.crop], plot.progress)
            if plot.crop != was_crop or stage != was_stage:
                farm._refresh_model(plot)
        farm._refresh_weeds(plot)

    if state is not None and "coins" in message:
        state.coins = int(message["coins"])
    if state is not None:
        # The barn belongs to the farm. Without this the toolbar counted
        # the seeds this machine happened to have — so it could offer
        # "Патиссон x3" on a farm whose last patisson seed went into the
        # ground an hour ago, and the press would be refused with no
        # explanation. The server sends the barn only when it changes.
        stock = message.get("inv")
        if stock is None:
            stock = message.get("inventory")
        if isinstance(stock, dict):
            state.inventory = {str(k): int(v) for k, v in stock.items()
                               if isinstance(v, (int, float))}
    clock = message.get("clock")
    if cycle is not None and isinstance(clock, dict):
        # The farm's clock belongs to the server too, or two players would
        # be standing in the same field at different hours.
        day = int(clock.get("day", cycle.day))
        hour = float(clock.get("hour", 0.0))
        cycle.total_time = day * cycle.day_length + hour / 24.0 * cycle.day_length


def wait_online(client: NetClient, timeout: float = CONNECT_TIMEOUT) -> bool:
    """Block until the farm answers — for menus and for tests."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if client.status == "online":
            return True
        if client.status in ("failed", "closed"):
            return False
        time.sleep(0.02)
    return False

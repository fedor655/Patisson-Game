"""The phone's connection to a farm.

Deliberately thin. A phone has no Panda3D, no numpy and no room for the
whole game, so this imports exactly one thing from the project — the
message format — and keeps the rest to the standard library. That is why
the protocol was written as plain sockets and JSON in the first place.

Same shape as the desktop client: a background thread owns the socket,
the interface polls a queue. On a phone that matters more, not less; the
touch loop must never wait for a packet.
"""

from __future__ import annotations

import json
import queue
import socket
import struct
import threading

PROTOCOL_VERSION = 1
DEFAULT_PORT = 7777
_HEADER = struct.Struct(">I")


class FarmLink:
    """Connect, listen, ask. Everything else is drawing."""

    def __init__(self, host: str, port: int = DEFAULT_PORT,
                 name: str = "Телефон"):
        self.host, self.port, self.name = host, int(port), name
        self.status = "connecting"       # connecting | online | failed | closed
        self.error: str | None = None
        self.player_id: int | None = None

        # The farm as the phone currently believes it to be.
        self.plots: dict[int, dict] = {}
        self.layout: list = []
        self.coins = 0
        self.clock: dict = {}
        self.players: list = []
        self.scarecrow = 1.0
        self.crow_ok = True          # пугало ещё пугает
        self.crow_fix = False        # и чинить его пока нечего
        # Амбар на общей ферме тоже общий: семена, которые тут
        # показаны, мог посадить кто-то другой минуту назад.
        self.inventory: dict = {}
        self.lines: list[str] = []

        self._sock: socket.socket | None = None
        self._out: queue.Queue = queue.Queue()
        self._in: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    # ------------------------------------------------------------ interface

    def act(self, action: str, plot: int | None = None,
            arg: str | None = None) -> None:
        message = {"t": "act", "a": action}
        if plot is not None:
            message["plot"] = int(plot)
        if arg is not None:
            message["arg"] = str(arg)
        self._out.put(message)

    def pump(self) -> list[str]:
        """Fold everything that arrived into the local picture.

        Returns the lines worth showing the player.
        """
        fresh: list[str] = []
        while True:
            try:
                message = self._in.get_nowait()
            except queue.Empty:
                break
            kind = message.get("t")
            if kind == "welcome":
                world = message.get("world") or {}
                self.player_id = message.get("id")
                self.layout = world.get("layout") or []
                self.plots = {p["i"]: p for p in world.get("plots", [])}
                self.coins = world.get("coins", 0)
                self.clock = world.get("clock") or {}
                self.players = world.get("players") or []
                self.scarecrow = world.get("scarecrow", 1.0)
                self.crow_ok = bool(world.get("crow_ok", True))
                self.crow_fix = bool(world.get("crow_fix", False))
                self.inventory = dict(world.get("inventory") or {})
            elif kind == "state":
                for plot in message.get("plots", []):
                    self.plots[plot["i"]] = plot
                self.coins = message.get("coins", self.coins)
                self.clock = message.get("clock") or self.clock
                self.players = message.get("players") or self.players
                self.scarecrow = message.get("scarecrow", self.scarecrow)
                self.crow_ok = bool(message.get("crow_ok", self.crow_ok))
                self.crow_fix = bool(message.get("crow_fix",
                                                 self.crow_fix))
                if isinstance(message.get("inv"), dict):
                    self.inventory = dict(message["inv"])
            elif kind == "event":
                fresh.extend(message.get("lines", []))
            elif kind == "bye":
                self.error = message.get("reason", "Ферма попрощалась")
                self.status = "failed"
        self.lines = (self.lines + fresh)[-6:]
        return fresh

    def close(self) -> None:
        self._stop.set()
        self.status = "closed"
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

    # --------------------------------------------------------------- socket

    def _run(self) -> None:
        try:
            self._sock = socket.create_connection((self.host, self.port),
                                                  timeout=8.0)
            self._sock.settimeout(0.2)
            self._send({"t": "hello", "v": PROTOCOL_VERSION,
                        "name": self.name})
            first = self._recv()
            if first is None or first.get("t") != "welcome":
                reason = (first or {}).get("reason", "Ферма не поздоровалась")
                self.error = reason
                self.status = "failed"
                return
            self._in.put(first)
            self.status = "online"
        except OSError as exc:
            self.error = f"Не дозвонился до фермы: {exc}"
            self.status = "failed"
            return

        while not self._stop.is_set():
            try:
                message = self._out.get_nowait()
            except queue.Empty:
                pass
            else:
                try:
                    self._send(message)
                except OSError as exc:
                    self.error = f"Связь оборвалась: {exc}"
                    self.status = "failed"
                    return
            try:
                message = self._recv()
            except OSError as exc:
                self.error = f"Связь оборвалась: {exc}"
                self.status = "failed"
                return
            if message is not None:
                self._in.put(message)

    def _send(self, message: dict) -> None:
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        self._sock.sendall(_HEADER.pack(len(body)) + body)

    def _recv(self) -> dict | None:
        """One message, or None if the farm simply had nothing to say."""
        header = self._read_exactly(_HEADER.size)
        if header is None:
            return None
        (size,) = _HEADER.unpack(header)
        if size > (1 << 20):
            raise OSError("ферма прислала слишком большое сообщение")
        body = self._read_exactly(size, blocking=True)
        if body is None:
            raise OSError("сообщение оборвалось на середине")
        return json.loads(body.decode("utf-8"))

    def _read_exactly(self, count: int, blocking: bool = False):
        chunks, left = [], count
        while left:
            try:
                part = self._sock.recv(left)
            except socket.timeout:
                if chunks or blocking:
                    continue          # mid-message: keep waiting for the rest
                return None           # nothing at all: come back next frame
            if not part:
                raise OSError("ферма закрыла соединение")
            chunks.append(part)
            left -= len(part)
        return b"".join(chunks)

"""How a client and a hosted farm talk to each other.

Every message is a JSON object behind a four-byte big-endian length, so a
reader always knows where one ends — a plain stream would leave it
guessing, and half a message looks exactly like a whole one until it does
not.

The shape of the conversation:

    client -> hello    name, protocol version
    server -> welcome  your id, and the whole farm as it stands
    client -> move     where you are and where you are looking
    client -> act      what you want to do, and to which bed
    server -> state    what actually changed since last tick
    server -> event    the lines the game would have shown you
    server -> bye      why you are being dropped

Only the server decides what happened. A client says "I want to water bed
seven"; whether the bed gets watered is not its call. That is the whole
reason the simulation was pulled out of the renderer: two machines
guessing at crop growth would drift apart within a day.

The version travels in the handshake and a mismatch is refused in words,
not by hanging: an old client meeting a new farm is the most likely
failure this will ever see, and "your version is old" beats a silent
freeze.
"""

from __future__ import annotations

import asyncio
import json
import struct

# Bump on any change to the fields below. Clients that do not match are
# turned away with an explanation.
PROTOCOL_VERSION = 1

DEFAULT_PORT = 7777

# A single message may not be larger than this. Nothing legitimate comes
# close -- a full snapshot of the farm is a few kilobytes -- so anything
# bigger is either a bug or someone poking at the port.
MAX_MESSAGE = 1 << 20

_HEADER = struct.Struct(">I")


class ProtocolError(Exception):
    """The other side said something that is not a message."""


def encode(message: dict) -> bytes:
    """One message, ready to put on the wire."""
    body = json.dumps(message, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_MESSAGE:
        raise ProtocolError(f"сообщение слишком велико: {len(body)} байт")
    return _HEADER.pack(len(body)) + body


def decode(body: bytes) -> dict:
    """The payload of one message, checked to be an object."""
    try:
        message = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"не разобрать сообщение: {exc}") from exc
    if not isinstance(message, dict):
        raise ProtocolError("сообщение должно быть объектом")
    if not isinstance(message.get("t"), str):
        raise ProtocolError("у сообщения нет типа")
    return message


async def read_message(reader: asyncio.StreamReader) -> dict:
    """Read exactly one message, or raise when the stream ends."""
    header = await reader.readexactly(_HEADER.size)
    (size,) = _HEADER.unpack(header)
    if size > MAX_MESSAGE:
        raise ProtocolError(f"заявлен размер {size} байт — это не наш клиент")
    return decode(await reader.readexactly(size))


async def write_message(writer: asyncio.StreamWriter, message: dict) -> None:
    writer.write(encode(message))
    await writer.drain()


# --------------------------------------------------------------- messages
# Constructors rather than bare dicts: the field names then exist in one
# place, and a typo is a missing function instead of a message the other
# side quietly ignores.

def hello(name: str) -> dict:
    return {"t": "hello", "v": PROTOCOL_VERSION, "name": name[:24] or "Фермер"}


def welcome(player_id: int, snapshot: dict) -> dict:
    return {"t": "welcome", "v": PROTOCOL_VERSION, "id": player_id,
            "world": snapshot}


def bye(reason: str) -> dict:
    return {"t": "bye", "reason": reason}


def move(x: float, y: float, z: float, heading: float, pitch: float) -> dict:
    return {"t": "move", "p": [round(x, 3), round(y, 3), round(z, 3)],
            "h": round(heading, 1), "pi": round(pitch, 1)}


def act(action: str, plot: int | None = None, arg: str | None = None) -> dict:
    """What the player wants to do. `plot` indexes the shared bed list."""
    message = {"t": "act", "a": action}
    if plot is not None:
        message["plot"] = int(plot)
    if arg is not None:
        message["arg"] = str(arg)[:32]
    return message


def state(tick: int, changes: dict) -> dict:
    return {"t": "state", "n": tick, **changes}


def events(lines: list[str]) -> dict:
    return {"t": "event", "lines": lines[:8]}


def version_error(theirs) -> dict:
    return bye(f"Версия игры не подходит: у сервера {PROTOCOL_VERSION}, "
               f"у вас {theirs}. Обновите игру.")

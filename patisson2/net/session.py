"""The game's side of a hosted farm: joining, drawing the others, leaving.

Kept out of `app.py` deliberately. The single-player path is long and
well worn, and threading network branches through every action would put
the two modes in each other's way. Instead the app grows one attribute —
`net` — which is None almost always; where behaviour has to differ, one
question is asked and answered here.

What differs is smaller than it sounds. The world is already simulated
somewhere; joining a farm means letting *that* copy be the truth. So the
local simulation stops advancing, the player's own actions become
requests instead of results, and everyone else appears as a villager
model with their name over it.
"""

from __future__ import annotations

import math

from ..game.view import place
from .client import NetClient, apply_state

ROSTER_LIMIT = 5           # names in the corner before it starts counting


def roster_lines(players: list, me_id, x: float, y: float,
                 limit: int = ROSTER_LIMIT) -> list[str]:
    """Who is on the farm: you first, then the others, nearest first.

    A name floating over somebody's head only helps while they are on
    screen, and a farm is mostly not on screen — the person you are
    looking for is as likely to be behind the barn as in front of you.
    So the corner carries the whole roster, and every name carries the
    distance to its owner: that is the number that turns "Борис is here
    somewhere" into "Борис is over by the pond".

    Kept a plain function, away from the renderer, so the arithmetic can
    be checked without a window open.
    """
    if not players:
        return []
    mine: list[str] = []
    others: list[tuple[float, str]] = []
    for entry in players:
        name = str(entry.get("name") or "Фермер")
        if entry.get("id") == me_id:
            mine.append(f"{name} — вы")
            continue
        pos = entry.get("p") or (0.0, 0.0, 0.0)
        try:
            dx, dy = float(pos[0]) - x, float(pos[1]) - y
        except (TypeError, ValueError, IndexError, KeyError):
            dx = dy = 0.0
        others.append((math.hypot(dx, dy), name))
    others.sort()
    lines = [f"На ферме: {len(players)}"] + mine
    lines += [f"{name} — {dist:.0f} м" for dist, name in others[:limit]]
    hidden = len(others) - len(others[:limit])
    if hidden > 0:
        # Never quietly drop somebody: a roster that shows five of nine
        # and says nothing is worse than no roster at all.
        lines.append(f"и ещё {hidden}")
    return lines


def parse_address(text: str, default_port: int) -> tuple[str, int]:
    """'host', 'host:port' or an IPv6 literal in brackets."""
    text = (text or "").strip()
    if text.startswith("["):                       # [::1]:7777
        host, _, rest = text[1:].partition("]")
        port = rest.lstrip(":")
        return host, int(port) if port.isdigit() else default_port
    host, _, port = text.rpartition(":")
    if not host:                                    # bare host
        return text, default_port
    return host, int(port) if port.isdigit() else default_port


class Avatar:
    """Somebody else, standing on the farm."""

    __slots__ = ("node", "label", "name")

    def __init__(self, node, label, name):
        self.node, self.label, self.name = node, label, name

    def remove(self):
        if self.node is not None:
            self.node.removeNode()
        if self.label is not None:
            self.label.removeNode()


class NetSession:
    """One visit to somebody's farm."""

    def __init__(self, app, client: NetClient):
        self.app = app
        self.client = client
        self.avatars: dict[int, Avatar] = {}
        self.last_error: str | None = None
        self._since_move = 0.0

    # ------------------------------------------------------------- helpers

    @property
    def online(self) -> bool:
        return self.client.online

    def act(self, action: str, plot=None, arg: str | None = None) -> None:
        """Ask the farm to do something. It may decline; that is its right."""
        self.client.act(action, plot, arg)

    def plot_index(self, plot) -> int | None:
        try:
            return self.app.farm.plots.index(plot)
        except ValueError:
            return None

    # -------------------------------------------------------------- update

    def update(self, dt: float) -> None:
        if self.client.status == "failed":
            self.leave(self.client.error or "Связь потеряна")
            return

        # Tell the farm where we are, ten times a second — often enough to
        # look alive, seldom enough that the socket stays quiet.
        self._since_move += dt
        if self.online and self._since_move >= 0.1:
            self._since_move = 0.0
            p = self.app.player.pos
            self.client.move(p, self.app.player.heading, self.app.player.pitch)

        for message in self.client.poll():
            kind = message.get("t")
            if kind == "welcome":
                apply_state(self.app.farm, message.get("world", {}),
                            self.app.state, self.app.cycle)
                self._sync_avatars(message.get("world", {}).get("players", []))
            elif kind == "state":
                apply_state(self.app.farm, message, self.app.state,
                            self.app.cycle)
                self._sync_avatars(message.get("players", []))
                self.app.weather = (message.get("clock") or {}).get(
                    "weather", self.app.weather)
            elif kind == "event":
                for line in message.get("lines", []):
                    self.app.state.notify(line)
            elif kind == "bye":
                self.leave(message.get("reason", "Ферма попрощалась"))
                return

    def _sync_avatars(self, players: list) -> None:
        seen = set()
        for entry in players:
            pid = entry.get("id")
            if pid is None or pid == self.client.player_id:
                continue                      # that one is us
            seen.add(pid)
            pos = entry.get("p") or [0, 0, 0]
            avatar = self.avatars.get(pid)
            if avatar is None:
                avatar = self._make_avatar(entry.get("name", "Фермер"), pos)
                self.avatars[pid] = avatar
            avatar.node.setPos(pos[0], pos[1], pos[2])
            avatar.node.setH(entry.get("h", 0.0))
            if avatar.label is not None:
                avatar.label.setPos(pos[0], pos[1], pos[2] + 2.05)
        for pid in [p for p in self.avatars if p not in seen]:
            self.avatars.pop(pid).remove()
        me = self.app.player.pos
        self._show_roster(roster_lines(players, self.client.player_id,
                                       me.x, me.y))

    def _show_roster(self, lines: list[str]) -> None:
        hud = getattr(self.app, "hud", None)
        if hud is not None and hasattr(hud, "set_players"):
            hud.set_players(lines)

    def _make_avatar(self, name: str, pos) -> Avatar:
        # There is no generic "villager" model: the three of them are
        # separate figures, assembled from parts for walking. Borrow
        # Bogdan's whole-body one for visitors.
        node = place(self.app.props.dynamic, "villager_bogdan",
                     (pos[0], pos[1], pos[2]), 0.0, 1.0)
        label = None
        try:
            # Built as a TextNode rather than by borrowing the node out of
            # an OnscreenText. That trick left the text owned by aspect2d,
            # where its scale lived: hung under render it kept its size but
            # not its shading, and the tag was in the scene, unhidden, in
            # the right place, and invisible on screen. Here the geometry,
            # the scale and the render state all belong to one node.
            from panda3d.core import TextNode
            text = TextNode(f"name-{name}")
            text.setText(name)
            text.setAlign(TextNode.ACenter)
            text.setTextColor(1, 1, 1, 1)
            text.setShadow(0.06, 0.06)
            text.setShadowColor(0, 0, 0, 0.85)
            if self.app.hud.font is not None:
                text.setFont(self.app.hud.font)
            label = self.app.render.attachNewNode(text)
            label.setScale(0.34)
            label.setBillboardPointEye()
            label.setLightOff()
            label.setShaderOff(10)             # the scene shader wants
            label.setDepthWrite(False)         # normals; text has none
            label.setBin("fixed", 40)
        except Exception:                      # noqa: BLE001 — a name tag is
            label = None                       # not worth failing a join for
        return Avatar(node, label, name)

    # --------------------------------------------------------------- leave

    def leave(self, reason: str | None = None) -> None:
        for avatar in self.avatars.values():
            avatar.remove()
        self.avatars.clear()
        # The corner belongs to the visit, not to the game: leaving it
        # behind would list company on a farm you are alone on.
        self._show_roster([])
        self.client.close()
        self.last_error = reason
        if self.app.net is self:
            self.app.net = None
        if reason:
            self.app.state.notify(reason, 6.0)

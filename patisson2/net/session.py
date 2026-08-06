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

from ..game.view import place
from .client import NetClient, apply_state


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

    def _make_avatar(self, name: str, pos) -> Avatar:
        # There is no generic "villager" model: the three of them are
        # separate figures, assembled from parts for walking. Borrow
        # Bogdan's whole-body one for visitors.
        node = place(self.app.props.dynamic, "villager_bogdan",
                     (pos[0], pos[1], pos[2]), 0.0, 1.0)
        label = None
        try:
            from direct.gui.OnscreenText import OnscreenText
            from panda3d.core import TextNode
            label = self.app.render.attachNewNode(
                OnscreenText(text=name, scale=0.34, fg=(1, 1, 1, 1),
                             align=TextNode.ACenter, font=self.app.hud.font,
                             mayChange=False,
                             shadow=(0, 0, 0, 0.7)).node())
            label.setBillboardPointEye()
            label.setLightOff()
            label.setDepthOffset(1)
        except Exception:                      # noqa: BLE001 — a name tag is
            label = None                       # not worth failing a join for
        return Avatar(node, label, name)

    # --------------------------------------------------------------- leave

    def leave(self, reason: str | None = None) -> None:
        for avatar in self.avatars.values():
            avatar.remove()
        self.avatars.clear()
        self.client.close()
        self.last_error = reason
        if self.app.net is self:
            self.app.net = None
        if reason:
            self.app.state.notify(reason, 6.0)

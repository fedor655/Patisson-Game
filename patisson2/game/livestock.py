"""Chickens and cows: feed them, and they give eggs and milk.

State lives here rather than on the Wanderer so the wandering behaviour stays
purely about movement.
"""

from __future__ import annotations

from dataclasses import dataclass

from .view import Vec3, place


# kind -> (product item, in-game days between products, feed cost in wheat,
#          how long one feeding lasts in days, interact range)
SPECIES = {
    "chicken": ("egg", 0.42, 1, 1.2, 2.2),
    "cow": ("milk", 0.95, 2, 1.6, 3.2),
}

PRODUCT_NAMES = {"egg": "Яйцо", "milk": "Молоко"}
PRODUCT_PRICE = {"egg": 9, "milk": 17}
FEED_ITEM = "wheat"


@dataclass
class AnimalState:
    kind: str
    fed: float = 0.0            # days of feeding left
    progress: float = 0.0       # 0..1 towards the next product
    ready: bool = False

    @property
    def hungry(self) -> bool:
        return self.fed <= 0.05


class Livestock:
    """Tracks every farm animal and the little marker over a ready one."""

    def __init__(self, base, world, props, day_length: float):
        self.base = base
        self.world = world
        self.props = props
        self.day_length = day_length
        self.states: dict[int, AnimalState] = {}
        self.markers: dict[int, object] = {}
        self.root = world.root.attachNewNode("livestock-markers")
        props.pipeline.apply_scene_shader(self.root)

        for animal in props.animals:
            kind = animal.node.getName().split("-")[0]
            if kind in SPECIES:
                self.states[id(animal)] = AnimalState(kind)

    # ------------------------------------------------------------ lookup

    def animals(self):
        for animal in self.props.animals:
            state = self.states.get(id(animal))
            if state is not None:
                yield animal, state

    def nearest(self, pos: Vec3):
        best, best_state, best_d = None, None, 1e9
        for animal, state in self.animals():
            reach = SPECIES[state.kind][4]
            p = animal.node.getPos()
            d = (p.x - pos.x) ** 2 + (p.y - pos.y) ** 2
            if d < reach * reach and d < best_d:
                best, best_state, best_d = animal, state, d
        return best, best_state

    # ------------------------------------------------------------ actions

    def feed(self, state: AnimalState, inventory) -> bool:
        _product, _period, cost, lasts, _reach = SPECIES[state.kind]
        if inventory.count(FEED_ITEM) < cost:
            return False
        inventory.take(FEED_ITEM, cost)
        state.fed = max(state.fed, lasts)
        return True

    def collect(self, state: AnimalState) -> str | None:
        if not state.ready:
            return None
        state.ready = False
        state.progress = 0.0
        return SPECIES[state.kind][0]

    # ------------------------------------------------------------- update

    def update(self, dt: float) -> None:
        day_frac = dt / self.day_length
        for animal, state in self.animals():
            # Feed is only consumed while the animal is working towards its
            # next product. It used to drain while one stood waiting to be
            # collected, so a player who fed the barn and spent the day
            # fishing came back to half the eggs the wheat had paid for —
            # punished for not standing next to the coop.
            if state.fed > 0.0 and not state.ready:
                state.fed = max(0.0, state.fed - day_frac)
                period = SPECIES[state.kind][1]
                state.progress = min(1.0, state.progress + day_frac / period)
                if state.progress >= 1.0:
                    state.ready = True
            self._sync_marker(animal, state)

    def _sync_marker(self, animal, state: AnimalState) -> None:
        """Float the product above an animal that has one waiting."""
        key = id(animal)
        marker = self.markers.get(key)
        if state.ready and marker is None:
            model = "patisson_0" if state.kind == "chicken" else "bucket"
            node = place(self.root, model, (0, 0, 0), 0,
                         0.55 if state.kind == "chicken" else 0.45)
            self.markers[key] = node
            marker = node
        elif not state.ready and marker is not None:
            marker.removeNode()
            del self.markers[key]
            marker = None
        if marker is not None:
            p = animal.node.getPos()
            lift = 0.75 if state.kind == "chicken" else 1.85
            marker.setPos(p.x, p.y, p.z + lift)
            marker.setH((marker.getH() + 40.0 * 0.016) % 360.0)

    # --------------------------------------------------------------- save

    def to_dict(self) -> dict:
        out = []
        for animal, state in self.animals():
            out.append({"fed": state.fed, "progress": state.progress,
                        "ready": state.ready})
        return {"animals": out}

    def from_dict(self, data: dict) -> None:
        from .state import as_dict, as_float, as_list

        entries = as_list(as_dict(data).get("animals"))
        for (animal, state), entry in zip(self.animals(), entries):
            entry = as_dict(entry)
            state.fed = min(1.0, max(0.0, as_float(entry.get("fed"))))
            state.progress = min(1.0, max(0.0, as_float(entry.get("progress"))))
            state.ready = bool(entry.get("ready", False))
            self._sync_marker(animal, state)

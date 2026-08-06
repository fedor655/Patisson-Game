"""Run the farm with Panda3D forcibly absent.

    python -m patisson2.tools.headless_check

The dedicated server and any future phone client have to run the same
farming, weather and pest code the desktop game runs, on machines that
have no renderer at all. Importing Panda3D is blocked here at the import
hook, so this cannot pass by accident: if any simulation module reaches
for the engine again, the import fails outright.

It is a separate entry point because the smoke suite has Panda3D loaded
long before it starts — the block has to happen in a fresh interpreter.
The smoke suite runs this as a subprocess.
"""

from __future__ import annotations

import sys


class _NoEngine:
    """Import hook that makes `import panda3d...` fail like it is not there."""

    def find_module(self, name, path=None):
        return self if name == "panda3d" or name.startswith("panda3d.") else None

    def load_module(self, name):
        raise ImportError(f"panda3d заблокирован для этой проверки ({name})")

    # Python 3 path
    def find_spec(self, name, path=None, target=None):
        if name == "panda3d" or name.startswith("panda3d."):
            raise ImportError(f"panda3d заблокирован для этой проверки ({name})")
        return None


def main() -> int:
    for name in [m for m in sys.modules if m.startswith("panda3d")]:
        del sys.modules[name]
    sys.meta_path.insert(0, _NoEngine())

    # --- the simulation must import at all -----------------------------
    from ..game.view import HAVE_ENGINE, NullNode, Vec3, place
    assert not HAVE_ENGINE, "движок всё-таки импортировался — проверка слепа"

    from ..game import cooking, dialogue, farming, fishing, state, tutorial
    from ..game.farming import CROPS, CROP_ORDER, days_to_ripe, growth_rate

    # --- and it must actually simulate ---------------------------------
    v = Vec3(3.0, 4.0, 0.0)
    assert abs(v.length() - 5.0) < 1e-9, "вектор без движка считает неверно"
    node = place(None, "patisson_3", (1.0, 2.0, 3.0), 90.0, 1.0)
    assert isinstance(node, NullNode)
    node.setPos(4.0, 5.0, 6.0)
    node.setColorScale(1, 1, 1, 1)          # must be silently ignored
    assert node.getPos().x == 4.0
    node.removeNode()

    # A crop has to ripen on the same schedule the desktop game gets, or
    # the server and the client would disagree about the world.
    for key in CROP_ORDER:
        days = days_to_ripe(CROPS[key])
        assert 1.0 < days < 12.0, f"{key}: срок без движка вышел {days}"
    assert growth_rate(CROPS["patisson"], 1.0, 1.0, 0.0, True) > 0.0

    # The bits with no engine ties at all still have to work headless.
    quests = state.default_quests()
    assert quests and all(q.reward > 0 for q in quests)
    assert dialogue.TOPICS and fishing.SPECIES and cooking.RECIPES
    assert tutorial.STEPS if hasattr(tutorial, "STEPS") else True

    # --- and the whole shared world has to run, not just the pieces ----
    from ..net.world import SharedWorld

    world = SharedWorld()
    assert len(world.farm.plots) == 24, \
        f"грядок на сервере {len(world.farm.plots)}, ждали 24"
    bed = world.farm.plots[0]
    assert world.farm.plant(bed, "wheat"), "на сервере нельзя посадить"
    day = world.cfg.game.day_length
    ripened = False
    for _ in range(int(day * 4 / 0.1)):
        world.update(0.1)
        if bed.crop is None:
            break                      # ripened and a crow took it
        if bed.progress >= 1.0:
            ripened = True
            break
        if bed.water < 0.5:
            world.farm.water_plot(bed)
    grew = ripened or any("созрел" in e for e in world.events)
    assert grew, (f"пшеница не выросла на сервере: прогресс "
                  f"{bed.progress:.2f}, события {world.events[-3:]}")
    assert world.cycle.day >= 1, "часы сервера стоят"
    snapshot = world.to_dict()
    assert snapshot["farm"] and "state" in snapshot, "мир не сериализуется"

    print(f"без движка: {len(CROP_ORDER)} культур, {len(quests)} заданий, "
          f"{len(dialogue.TOPICS)} тем, {len(fishing.SPECIES)} рыб, "
          f"общий мир на {len(world.farm.plots)} грядок дожил до дня "
          f"{world.cycle.day + 1} — симуляция поднялась", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

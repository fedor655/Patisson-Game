"""The two things the simulation borrows from the renderer, and what it
does when there is no renderer at all.

The farm, the weather, the pests, the livestock and the villagers all run
the same code in three places now: the desktop game, which draws them; the
dedicated server, which only simulates them; and — once it exists — a
phone, which draws them another way entirely. Only the desktop has
Panda3D, so the simulation may not import it directly.

Two seams cover every use the game logic had:

* `Vec3` — a position. Panda's is used when it is there, because the
  renderer passes its own vectors straight into these modules; a small
  pure-Python stand-in with the same surface is used when it is not.
* `place()` — put a model in the world. Without a scene there is nothing
  to put anywhere, so it hands back a node that quietly accepts being
  moved, tinted and removed. The simulation is then free to keep saying
  what *should* be visible without caring whether anything is.

Nothing here changes what the desktop game does: with Panda3D present,
both seams forward to exactly what was called before.
"""

from __future__ import annotations

import math

try:                                    # the desktop game
    from panda3d.core import Vec3       # noqa: F401  (re-exported)
    HAVE_ENGINE = True
except ImportError:                     # the server, or a phone
    HAVE_ENGINE = False

    class Vec3:                         # type: ignore[no-redef]
        """Just enough of Panda's vector for the simulation to run.

        The game logic reads .x/.y/.z, subtracts positions, scales them
        and measures lengths — nothing more exotic — so this is the whole
        surface rather than a partial imitation of a big class.
        """

        __slots__ = ("x", "y", "z")

        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.x, self.y, self.z = float(x), float(y), float(z)

        def __iter__(self):
            return iter((self.x, self.y, self.z))

        def __getitem__(self, i):
            return (self.x, self.y, self.z)[i]

        def __len__(self):
            return 3

        def __repr__(self):
            return f"Vec3({self.x:.3f}, {self.y:.3f}, {self.z:.3f})"

        def __eq__(self, other):
            try:
                return (self.x, self.y, self.z) == (other.x, other.y, other.z)
            except AttributeError:
                return NotImplemented

        def __add__(self, o):
            return Vec3(self.x + o.x, self.y + o.y, self.z + o.z)

        def __sub__(self, o):
            return Vec3(self.x - o.x, self.y - o.y, self.z - o.z)

        def __mul__(self, k):
            return Vec3(self.x * k, self.y * k, self.z * k)

        __rmul__ = __mul__

        def length(self):
            return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

        def lengthSquared(self):
            return self.x ** 2 + self.y ** 2 + self.z ** 2

        def normalized(self):
            n = self.length()
            return Vec3(self.x / n, self.y / n, self.z / n) if n else Vec3()

        def getX(self):
            return self.x

        def getY(self):
            return self.y

        def getZ(self):
            return self.z


class NullNode:
    """A model that was never drawn.

    Everything the simulation does to a node — move it, turn it, tint it,
    take it away — is accepted and forgotten. Returning this instead of
    None means the game logic needs no `if we have a renderer` branches,
    which is what kept the farm code readable while it learned to run
    without a screen.
    """

    __slots__ = ("_name", "_pos", "_h", "_scale")

    def __init__(self, name="", pos=(0.0, 0.0, 0.0), h=0.0, scale=1.0):
        self._name = name
        self._pos = Vec3(*pos)
        self._h, self._scale = h, scale

    # --- the handful of getters the logic actually reads ---------------
    def getName(self):
        return self._name

    def getPos(self, *_a):
        return self._pos

    def getX(self):
        return self._pos.x

    def getY(self):
        return self._pos.y

    def getH(self):
        return self._h

    def setPos(self, *a):
        self._pos = Vec3(*a) if len(a) == 3 else Vec3(*a[0])
        return self

    def setH(self, h):
        self._h = h
        return self

    def setScale(self, s, *_r):
        self._scale = s
        return self

    def removeNode(self):
        return None

    def isEmpty(self):
        return True

    def __getattr__(self, _name):
        """Anything else — setColorScale, reparentTo, setBin — is a no-op."""
        def ignore(*_a, **_k):
            return None
        return ignore


# What a placed model is, whichever world we are in. Used for the type
# hints on Plot.node and friends.
if HAVE_ENGINE:
    from panda3d.core import NodePath as Node    # noqa: F401
else:
    Node = NullNode


def place(parent, name, pos, h=0.0, scale=1.0, p=0.0):
    """Put a model in the world, or pretend to when there is no world."""
    if not HAVE_ENGINE or parent is None or isinstance(parent, NullNode):
        return NullNode(name, pos, h, scale)
    from ..world.props import place as _place
    return _place(parent, name, pos, h, scale, p)

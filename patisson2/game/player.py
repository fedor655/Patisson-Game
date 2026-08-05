"""First-person player: movement over the heightfield, look, stamina, reach."""

from __future__ import annotations

import math

from panda3d.core import Vec3

EYE_HEIGHT = 1.68
WALK_SPEED = 4.4
SPRINT_SPEED = 7.8
ACCEL = 22.0
FRICTION = 14.0
GRAVITY = 20.0
JUMP_SPEED = 6.4
REACH = 3.4


class Player:
    def __init__(self, base, world, cfg, start=(0.0, -6.0)):
        self.base = base
        self.world = world
        self.cfg = cfg
        self.pos = Vec3(start[0], start[1], world.height_at(*start))
        self.vel = Vec3(0, 0, 0)
        self.heading = 0.0        # degrees, 0 = +Y
        self.pitch = -6.0
        self.on_ground = True
        self.stamina = cfg.stamina_max
        self.sensitivity = 0.14
        self.head_bob = 0.0
        self.locked = False       # true while a menu owns the mouse
        self.frozen = False       # screenshot tool parks the camera

    # ------------------------------------------------------------------ look

    def add_look(self, dx: float, dy: float):
        if self.locked:
            return
        self.heading -= dx * self.sensitivity
        self.pitch = max(-88.0, min(88.0, self.pitch - dy * self.sensitivity))
        self.heading %= 360.0

    def forward(self) -> Vec3:
        a = math.radians(self.heading)
        return Vec3(-math.sin(a), math.cos(a), 0.0)

    def right(self) -> Vec3:
        a = math.radians(self.heading)
        return Vec3(math.cos(a), math.sin(a), 0.0)

    def look_dir(self) -> Vec3:
        a = math.radians(self.heading)
        p = math.radians(self.pitch)
        cp = math.cos(p)
        return Vec3(-math.sin(a) * cp, math.cos(a) * cp, math.sin(p))

    @property
    def eye(self) -> Vec3:
        return Vec3(self.pos.x, self.pos.y, self.pos.z + EYE_HEIGHT + self.head_bob)

    # ---------------------------------------------------------------- update

    def update(self, dt: float, keys: dict, blocked: bool = False):
        if self.frozen:
            return
        want = Vec3(0, 0, 0)
        if not blocked and not self.locked:
            if keys.get("forward"):
                want += self.forward()
            if keys.get("back"):
                want -= self.forward()
            if keys.get("right"):
                want += self.right()
            if keys.get("left"):
                want -= self.right()

        sprinting = bool(keys.get("sprint")) and want.length() > 0.01 and self.stamina > 1.0
        speed = SPRINT_SPEED if sprinting else WALK_SPEED

        if sprinting:
            self.stamina = max(0.0, self.stamina - dt * 13.0)
        else:
            self.stamina = min(self.cfg.stamina_max, self.stamina + dt * 8.5)

        if want.length_squared() > 1e-6:
            want.normalize()
            target = want * speed
            self.vel.x += (target.x - self.vel.x) * min(ACCEL * dt, 1.0)
            self.vel.y += (target.y - self.vel.y) * min(ACCEL * dt, 1.0)
        else:
            damp = max(0.0, 1.0 - FRICTION * dt)
            self.vel.x *= damp
            self.vel.y *= damp

        if keys.get("jump") and self.on_ground and not blocked:
            self.vel.z = JUMP_SPEED
            self.on_ground = False

        self.vel.z -= GRAVITY * dt

        nx = self.pos.x + self.vel.x * dt
        ny = self.pos.y + self.vel.y * dt

        # Refuse to walk into deep water or up cliffs.
        ground = self.world.height_at(nx, ny)
        too_steep = self.world.terrain.slope_at(nx, ny) > 0.62
        too_deep = ground < self.world.cfg.water_level - 0.45
        if too_steep or too_deep:
            # Slide along whichever axis is still legal.
            if not (self.world.terrain.slope_at(nx, self.pos.y) > 0.62
                    or self.world.height_at(nx, self.pos.y) < self.world.cfg.water_level - 0.45):
                ny = self.pos.y
            elif not (self.world.terrain.slope_at(self.pos.x, ny) > 0.62
                      or self.world.height_at(self.pos.x, ny) < self.world.cfg.water_level - 0.45):
                nx = self.pos.x
            else:
                nx, ny = self.pos.x, self.pos.y
            self.vel.x *= 0.4
            self.vel.y *= 0.4

        # Walls, trunks and fences. Doorways are simply gaps in the blockers.
        nx, ny = self.world.blockers.resolve(nx, ny, 0.34, self.pos.z)

        limit = self.world.terrain.half_span * 0.85
        nx = max(-limit, min(limit, nx))
        ny = max(-limit, min(limit, ny))

        self.pos.x, self.pos.y = nx, ny
        self.pos.z += self.vel.z * dt

        ground = self.world.height_at(self.pos.x, self.pos.y)
        if self.pos.z <= ground:
            self.pos.z = ground
            self.vel.z = 0.0
            self.on_ground = True
        else:
            self.on_ground = False

        # Head bob while walking, so movement has weight.
        planar = math.hypot(self.vel.x, self.vel.y)
        if self.on_ground and planar > 0.4:
            self.head_bob = math.sin(globals().setdefault("_t", 0.0)) * 0.0
        self._bob_phase = getattr(self, "_bob_phase", 0.0) + dt * planar * 2.1
        self.head_bob = math.sin(self._bob_phase) * 0.035 * min(planar / WALK_SPEED, 1.2)

    def apply_to_camera(self, camera):
        e = self.eye
        camera.setPos(e.x, e.y, e.z)
        camera.setHpr(self.heading, self.pitch, 0)

    # ------------------------------------------------------------ interaction

    def aim_point(self, distance: float = 2.2) -> Vec3:
        d = self.look_dir()
        e = self.eye
        return Vec3(e.x + d.x * distance, e.y + d.y * distance, e.z + d.z * distance)

    def ground_aim(self) -> Vec3 | None:
        """Where the view ray meets the ground, if it does so within reach."""
        e = self.eye
        d = self.look_dir()
        if d.z >= -0.02:
            return None
        t = 0.4
        while t < REACH * 1.7:
            p = Vec3(e.x + d.x * t, e.y + d.y * t, e.z + d.z * t)
            if p.z <= self.world.height_at(p.x, p.y):
                return p
            t += 0.12
        return None

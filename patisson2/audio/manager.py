"""Runtime audio: cache generation, playback, ambience and music.

The sound bank is rendered to WAV in a user cache the first time the game runs.
Effects and ambience are quick enough to make the player wait for; the music
takes far longer, so it renders on a background thread and fades in when ready.
"""

from __future__ import annotations

import random
import threading
from pathlib import Path

from panda3d.core import Filename

from . import bank
from .synth import write_wav

CACHE_ROOT = Path.home() / ".patisson2" / "audio"

# Sounds that can legitimately overlap need more than one voice.
POOLED = {"step1": 3, "step2": 3, "step3": 3, "step4": 3,
          "cluck": 2, "coin": 2, "click": 2, "splash": 2,
          "bird1": 2, "bird2": 2, "bird3": 2, "frog": 2}

MUSIC_FOR_HOUR = (
    (5.0, "music_morning"),
    (10.0, "music_day"),
    (17.5, "music_evening"),
    (21.5, "music_night"),
)


def music_for_hour(hour: float) -> str:
    chosen = MUSIC_FOR_HOUR[-1][1]
    for start, name in MUSIC_FOR_HOUR:
        if hour >= start:
            chosen = name
    return chosen


class AudioManager:
    def __init__(self, base, master=0.9, sfx_volume=0.85, music_volume=0.45):
        self.base = base
        self.enabled = bool(base.sfxManagerList) and base.sfxManagerList[0].isValid()
        self.master = master
        self.sfx_volume = sfx_volume
        self.music_volume = music_volume
        self.rng = random.Random(1234)

        self.sounds: dict[str, list] = {}
        self._pool_index: dict[str, int] = {}
        self.music: dict[str, object] = {}
        self.current_music: str | None = None
        self._music_level: dict[str, float] = {}
        self._music_fade = 0.0
        self._pending_music: str | None = None

        self.ambience: dict[str, object] = {}
        self._amb_target: dict[str, float] = {}
        self._amb_level: dict[str, float] = {}

        self._step_timer = 0.0
        self._music_ready = threading.Event()
        self._critter_timer = 6.0

        if not self.enabled:
            return

        mgr = base.sfxManagerList[0]
        mgr.setConcurrentSoundLimit(32)

        self.dir = CACHE_ROOT / str(bank.BANK_VERSION)
        # Sound is a nicety; a home directory that cannot be written to is not
        # a reason to refuse to start the game. An unwritable cache used to
        # raise straight out of the constructor and take the launch with it.
        try:
            fresh = self._ensure_cache()
        except OSError as exc:
            print(f"[audio] нет кэша звуков ({exc}); играем без звука", flush=True)
            self.enabled = False
            return
        self._load_effects()
        self._load_ambience()
        if fresh:
            print("[audio] generating music in the background…", flush=True)
        threading.Thread(target=self._ensure_music, daemon=True).start()

    # ------------------------------------------------------------- caching

    def _path(self, name: str) -> Path:
        return self.dir / f"{name}.wav"

    def _ensure_cache(self) -> bool:
        """Render effects and ambience. Returns True if anything was generated."""
        self.dir.mkdir(parents=True, exist_ok=True)
        generated = False
        quick = {**bank.SFX, **bank.AMBIENCE}
        missing = [n for n in quick if not self._path(n).exists()]
        if missing:
            print(f"[audio] generating {len(missing)} sounds…", flush=True)
        for name in missing:
            write_wav(self._path(name), quick[name]())
            generated = True
        return generated

    def _ensure_music(self):
        """Background thread: render any missing music, then load it."""
        try:
            for name, fn in bank.MUSIC.items():
                if not self._path(name).exists():
                    write_wav(self._path(name), fn())
            self._pending_music = "load"
        except Exception as exc:                     # never take the game down
            print(f"[audio] music generation failed: {exc}", flush=True)
        finally:
            self._music_ready.set()

    # -------------------------------------------------------------- loading

    def _make(self, name: str):
        mgr = self.base.sfxManagerList[0]
        return mgr.getSound(Filename.fromOsSpecific(str(self._path(name))).getFullpath())

    def _load_effects(self):
        for name in bank.SFX:
            count = POOLED.get(name, 1)
            voices = [self._make(name) for _ in range(count)]
            self.sounds[name] = [v for v in voices if v]
            self._pool_index[name] = 0

    def _load_ambience(self):
        for name in bank.AMBIENCE:
            snd = self._make(name)
            if not snd:
                continue
            snd.setLoop(True)
            snd.setVolume(0.0)
            snd.play()
            self.ambience[name] = snd
            self._amb_target[name] = 0.0
            self._amb_level[name] = 0.0

    def _load_music(self):
        for name in bank.MUSIC:
            if name in self.music or not self._path(name).exists():
                continue
            snd = self._make(name)
            if snd:
                snd.setLoop(True)
                snd.setVolume(0.0)
                self.music[name] = snd

    # ------------------------------------------------------------- playback

    def play(self, name: str, volume: float = 1.0, pitch: float = 0.0):
        """Fire a one-shot. ``pitch`` is a +/- fraction of random detune."""
        if not self.enabled:
            return
        voices = self.sounds.get(name)
        if not voices:
            return
        i = self._pool_index[name]
        self._pool_index[name] = (i + 1) % len(voices)
        snd = voices[i]
        snd.setVolume(max(0.0, min(1.0, volume * self.sfx_volume * self.master)))
        if pitch:
            snd.setPlayRate(1.0 + self.rng.uniform(-pitch, pitch))
        snd.play()

    def play_at(self, name: str, pos, listener, falloff: float = 22.0,
                volume: float = 1.0, pitch: float = 0.0):
        """One-shot attenuated by distance — used for animals and weather."""
        dx = pos[0] - listener[0]
        dy = pos[1] - listener[1]
        dz = pos[2] - listener[2]
        dist = (dx * dx + dy * dy + dz * dz) ** 0.5
        if dist > falloff:
            return
        self.play(name, volume * (1.0 - dist / falloff) ** 1.5, pitch)

    def footstep(self):
        which = self.rng.choice(("step1", "step2", "step3", "step4"))
        self.play(which, self.rng.uniform(0.55, 0.85), pitch=0.10)

    # ---------------------------------------------------------------- music

    def set_music(self, name: str | None):
        if name == self.current_music:
            return
        self.current_music = name

    # ---------------------------------------------------------------- mixer

    def set_volumes(self, master=None, sfx=None, music=None):
        if master is not None:
            self.master = max(0.0, min(1.0, master))
        if sfx is not None:
            self.sfx_volume = max(0.0, min(1.0, sfx))
        if music is not None:
            self.music_volume = max(0.0, min(1.0, music))

    def nudge_master(self, delta: float) -> float:
        self.set_volumes(master=self.master + delta)
        return self.master

    def nudge_music(self, delta: float) -> float:
        self.set_volumes(music=self.music_volume + delta)
        return self.music_volume

    def update(self, dt: float, *, hour: float, is_night: bool, weather: str,
               indoors: bool = False, moving: float = 0.0, on_ground: bool = True,
               paused: bool = False, places: dict | None = None):
        if not self.enabled:
            return

        if self._pending_music == "load":
            self._pending_music = None
            self._load_music()

        # --- music: pick a track for the time of day and crossfade to it ---
        want = None if paused else music_for_hour(hour)
        self.set_music(want)
        for name, snd in self.music.items():
            target = (self.music_volume * self.master) if name == self.current_music else 0.0
            # Panda's AudioSound is a C++ object and won't hold Python
            # attributes, so fade levels live here.
            level = self._music_level.get(name, 0.0)
            level += (target - level) * min(dt * 0.55, 1.0)
            self._music_level[name] = level
            snd.setVolume(max(0.0, min(1.0, level)))
            if level > 0.002 and snd.status() != snd.PLAYING:
                snd.play()
            elif level <= 0.002 and snd.status() == snd.PLAYING:
                snd.stop()

        # --- ambience beds ---
        raining = weather == "rain"
        snowing = weather == "snow"
        for name in self.ambience:
            self._amb_target[name] = 0.0
        if not indoors:
            self._amb_target["amb_wind"] = 0.5 if not (raining or snowing) else 0.75
            if is_night:
                self._amb_target["amb_night"] = 0.75
            else:
                self._amb_target["amb_day"] = 0.0 if raining else 0.7
            if raining:
                self._amb_target["amb_rain"] = 0.95
            # Place-based layers: the pond and the trees are mixed by where the
            # player is standing, so their targets come from outside.
            for name, level in (places or {}).items():
                if name in self._amb_target:
                    self._amb_target[name] = max(0.0, min(1.0, level))

        for name, snd in self.ambience.items():
            level = self._amb_level[name]
            level += (self._amb_target[name] - level) * min(dt * 0.9, 1.0)
            self._amb_level[name] = level
            snd.setVolume(max(0.0, min(1.0, level * self.sfx_volume * self.master)))

        # --- footsteps, paced by how fast the player is actually moving ---
        if moving > 0.4 and on_ground and not paused:
            self._step_timer -= dt * moving
            if self._step_timer <= 0.0:
                self.footstep()
                self._step_timer = 2.1

        # --- occasional animal noises ---
        self._critter_timer -= dt
        if self._critter_timer <= 0.0 and not paused:
            # Faster than it used to be because most ticks now find nothing
            # suitable nearby and stay silent.
            self._critter_timer = self.rng.uniform(5.0, 13.0)
            return "critter" if not indoors else None
        return None

    def stop_all(self):
        if not self.enabled:
            return
        for snd in list(self.ambience.values()) + list(self.music.values()):
            snd.stop()

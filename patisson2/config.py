"""Tunables for Patisson 2.0 — graphics quality, world size and game balance."""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass
class GraphicsConfig:
    width: int = 1600
    height: int = 900
    fullscreen: bool = False
    vsync: bool = True
    msaa: int = 0                 # post-AA handles edges; MSAA costs too much here

    shadow_size: int = 2048
    shadow_extent: float = 48.0   # half-width of the sun's ortho frustum, metres
    shadow_bias: float = 0.0022

    ssao: bool = True
    ssao_radius: float = 0.75
    ssao_intensity: float = 0.95

    bloom: bool = True
    bloom_threshold: float = 1.15
    bloom_knee: float = 0.55
    bloom_strength: float = 0.055

    godrays: bool = True
    godray_strength: float = 0.55

    fxaa: bool = True
    exposure: float = 1.05
    vignette: float = 0.30
    grain: float = 0.010
    saturation: float = 1.06
    fog_density: float = 0.0016

    grass_density: int = 170_000
    grass_radius: float = 38.0
    view_distance: float = 420.0

    # Path-traced photo mode.
    pt_samples_per_frame: int = 2
    pt_max_bounces: int = 4
    pt_target_samples: int = 512

    @staticmethod
    def preset(name: str) -> "GraphicsConfig":
        """The parts of a preset that have no entry in the settings file.

        Shadow size, SSAO, bloom, god rays and the grass count all belong to
        settings.PRESETS, which the options screen writes and the app applies
        after this — setting them here as well only produced two answers to
        the same question, and the settings file always won.
        """
        base = GraphicsConfig()
        if name == "low":
            return replace(base, ssao_radius=0.5, grass_radius=28.0,
                           view_distance=260.0, pt_samples_per_frame=1)
        if name == "medium":
            return replace(base, ssao_radius=0.6, grass_radius=36.0,
                           view_distance=360.0)
        if name == "ultra":
            return replace(base, ssao_radius=0.9, grass_radius=54.0,
                           view_distance=520.0, pt_samples_per_frame=3)
        return base


@dataclass
class WorldConfig:
    size: float = 320.0           # world is size x size metres
    heightmap_res: int = 257      # power of two + 1
    terrain_res: int = 264        # mesh resolution
    max_height: float = 9.0
    water_level: float = -1.5
    seed: int = 20250825          # the original game's release date


@dataclass
class GameConfig:
    day_length: float = 480.0     # seconds of real time per in-game day
    start_hour: float = 7.0
    season_days: int = 7
    start_coins: int = 40
    stamina_max: float = 100.0


@dataclass
class Config:
    graphics: GraphicsConfig = field(default_factory=GraphicsConfig)
    world: WorldConfig = field(default_factory=WorldConfig)
    game: GameConfig = field(default_factory=GameConfig)

"""Player settings that outlive the session.

Kept separate from Config: Config is what the game was *launched* with, this is
what the player chose. Loaded before the pipeline is built so the expensive
choices (shadow resolution, grass count) are right from the first frame.
"""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_PATH = Path.home() / ".patisson2" / "settings.json"

DEFAULTS = {
    "preset": "high",
    "shadow_size": 2048,
    "ssao": True,
    "bloom": True,
    "godrays": True,
    "grass_scale": 1.0,
    "master_volume": 0.9,
    "music_volume": 0.45,
    "sfx_volume": 0.85,
}

# Preset -> the graphics values it implies. Volumes are never touched by these.
PRESETS = {
    "low": {"shadow_size": 1024, "ssao": False, "bloom": True,
            "godrays": False, "grass_scale": 0.25},
    "medium": {"shadow_size": 2048, "ssao": True, "bloom": True,
               "godrays": False, "grass_scale": 0.5},
    "high": {"shadow_size": 2048, "ssao": True, "bloom": True,
             "godrays": True, "grass_scale": 1.0},
    "ultra": {"shadow_size": 4096, "ssao": True, "bloom": True,
              "godrays": True, "grass_scale": 2.0},
}

PRESET_NAMES = {"low": "низкое", "medium": "среднее", "high": "высокое",
                "ultra": "ультра", "custom": "своё"}


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    for key, value in stored.items():
        if key in DEFAULTS:
            data[key] = value
    return data


def save(data: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        pass          # settings are a convenience, never a reason to crash


def apply_preset(data: dict, preset: str) -> dict:
    data["preset"] = preset
    data.update(PRESETS.get(preset, {}))
    return data


def matching_preset(data: dict) -> str:
    """Which preset these values correspond to, or 'custom'."""
    for name, values in PRESETS.items():
        if all(data.get(k) == v for k, v in values.items()):
            return name
    return "custom"


def apply_to_config(cfg, data: dict) -> None:
    """Fold the stored choices into a Config before anything is built."""
    g = cfg.graphics
    g.shadow_size = int(data["shadow_size"])
    g.ssao = bool(data["ssao"])
    g.bloom = bool(data["bloom"])
    g.godrays = bool(data["godrays"])
    g.grass_density = max(1000, int(g.grass_density * float(data["grass_scale"])))

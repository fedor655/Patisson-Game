"""GLSL loading with `#include` support and compile-time defines.

Panda3D hands raw source to the driver, so the include expansion happens here.
Sources are cached per (path, defines) so repeated Shader.make calls are cheap.
"""

from __future__ import annotations

import re
from pathlib import Path

from panda3d.core import Shader

SHADER_DIR = Path(__file__).parent / "shaders"

_INCLUDE_RE = re.compile(r'^\s*#include\s+"([^"]+)"\s*$', re.MULTILINE)
_source_cache: dict[tuple[str, tuple[tuple[str, str], ...]], str] = {}
_shader_cache: dict[tuple, Shader] = {}


def _read(path: Path, seen: set[Path]) -> str:
    path = path.resolve()
    if path in seen:
        return ""  # include guard fallback
    seen.add(path)
    text = path.read_text(encoding="utf-8")

    def expand(match: re.Match) -> str:
        target = (SHADER_DIR / match.group(1)).resolve()
        if not target.exists():
            raise FileNotFoundError(f"{path.name}: #include \"{match.group(1)}\" not found")
        return f"// --- begin {match.group(1)} ---\n{_read(target, seen)}\n// --- end {match.group(1)} ---"

    return _INCLUDE_RE.sub(expand, text)


def load_source(name: str, defines: dict[str, object] | None = None) -> str:
    """Return fully expanded GLSL for ``name`` (relative to the shaders dir)."""
    key = (name, tuple(sorted((k, str(v)) for k, v in (defines or {}).items())))
    if key in _source_cache:
        return _source_cache[key]

    text = _read(SHADER_DIR / name, set())

    if defines:
        lines = text.split("\n")
        # The #version directive must stay first, so inject right after it.
        insert_at = 0
        for i, line in enumerate(lines):
            if line.lstrip().startswith("#version"):
                insert_at = i + 1
                break
        block = [f"#define {k} {v}" for k, v in defines.items()]
        lines[insert_at:insert_at] = block
        text = "\n".join(lines)

    _source_cache[key] = text
    return text


def make_shader(vert: str, frag: str, defines: dict[str, object] | None = None) -> Shader:
    """Compile a vertex/fragment pair by filename."""
    key = ("vf", vert, frag, tuple(sorted((k, str(v)) for k, v in (defines or {}).items())))
    if key in _shader_cache:
        return _shader_cache[key]
    shader = Shader.make(
        Shader.SL_GLSL,
        vertex=load_source(vert, defines),
        fragment=load_source(frag, defines),
    )
    if shader is None:
        raise RuntimeError(f"failed to compile {vert} + {frag}")
    _shader_cache[key] = shader
    return shader


def make_compute(name: str, defines: dict[str, object] | None = None) -> Shader:
    """Compile a compute shader by filename."""
    key = ("c", name, tuple(sorted((k, str(v)) for k, v in (defines or {}).items())))
    if key in _shader_cache:
        return _shader_cache[key]
    shader = Shader.make_compute(Shader.SL_GLSL, load_source(name, defines))
    if shader is None:
        raise RuntimeError(f"failed to compile compute shader {name}")
    _shader_cache[key] = shader
    return shader


def dump_expanded(name: str, out: Path, defines: dict[str, object] | None = None) -> None:
    """Write expanded source to disk — used when a driver reports a line number."""
    out.write_text(load_source(name, defines), encoding="utf-8")

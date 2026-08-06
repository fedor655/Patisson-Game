"""Build the game's icon out of the game's own ripe patisson.

    python -m patisson2.tools.make_icon

Nothing is drawn by hand. The model that stands on a ripe bed is rendered
offscreen with an alpha channel, then composed onto a farm-green tile with
a band of soil, and written as a multi-resolution `assets/icon.ico`.

The icon therefore always shows the vegetable the game is actually about,
and it stays legible at 16 px because the silhouette is one pale blob on a
dark green field. Windows shows it on the desktop shortcut, in the taskbar
while the game runs, and in the list of installed programs; the launcher
`.exe` carries it in its own resources.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "assets" / "models" / "patisson_3.glb"
OUT_ICO = ROOT / "assets" / "icon.ico"
SIZES = (256, 128, 64, 48, 32, 24, 16)

# The tile the vegetable sits on, in the palette the world already uses.
FIELD = (58, 98, 44, 255)
SOIL = (84, 58, 38, 255)


def render_patisson(px: int = 512) -> "Image.Image":
    """The ripe patisson, lit and cut out against transparency."""
    from panda3d.core import (AmbientLight, DirectionalLight, Filename,
                              loadPrcFileData)
    loadPrcFileData("", "window-type offscreen\n"
                        "audio-library-name null\n"
                        f"win-size {px} {px}\n"
                        "framebuffer-alpha #t\n"
                        "alpha-bits 8\n"
                        "notify-level-glgsg warning\n")
    from direct.showbase.ShowBase import ShowBase
    from PIL import Image

    base = ShowBase()
    base.win.setClearColor((0, 0, 0, 0))
    root, cam = base.render, base.camera

    model = base.loader.loadModel(Filename.fromOsSpecific(str(MODEL)))
    model.reparentTo(root)
    lo, hi = model.getTightBounds()
    size = max(hi - lo)
    model.setPos(-(lo + hi) * 0.5)
    holder = root.attachNewNode("holder")
    model.reparentTo(holder)
    holder.setHpr(28, 0, 0)
    # The mesh carries pale flesh; warm it so it reads as a vegetable.
    model.setColorScale(1.02, 0.97, 0.62, 1.0)

    for hpr, colour in (((-35, -38, 0), (1.15, 1.12, 0.98, 1)),
                        ((150, -18, 0), (0.30, 0.36, 0.42, 1))):
        light = DirectionalLight("light")
        light.setColor(colour)
        np_ = root.attachNewNode(light)
        np_.setHpr(*hpr)
        root.setLight(np_)
    amb = AmbientLight("amb")
    amb.setColor((0.40, 0.43, 0.36, 1))
    root.setLight(root.attachNewNode(amb))

    cam.setPos(0, -size * 2.05, size * 1.55)
    cam.lookAt(0, 0, 0.0)
    base.camLens.setFov(30)

    base.graphicsEngine.renderFrame()
    base.graphicsEngine.renderFrame()
    tmp = ROOT / "assets" / "_icon_render.png"
    base.win.saveScreenshot(Filename.fromOsSpecific(str(tmp)))
    img = Image.open(tmp).convert("RGBA").copy()
    tmp.unlink(missing_ok=True)
    return img


def compose(veg: "Image.Image", px: int = 1024) -> "Image.Image":
    from PIL import Image, ImageDraw, ImageFilter

    veg = veg.crop(veg.split()[3].getbbox())      # tight around the flesh
    tile = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    radius = int(px * 0.22)
    ImageDraw.Draw(tile).rounded_rectangle((0, 0, px - 1, px - 1),
                                           radius=radius, fill=FIELD)
    band = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    ImageDraw.Draw(band).rounded_rectangle(
        (0, int(px * 0.70), px - 1, px - 1), radius=radius, fill=SOIL)
    tile.alpha_composite(band)

    glow = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-px * 0.3, -px * 0.45, px * 0.85, px * 0.5),
                                 fill=(255, 255, 255, 42))
    tile.alpha_composite(glow.filter(ImageFilter.GaussianBlur(px * 0.06)))

    scale = int(px * 0.80) / max(veg.size)
    veg = veg.resize((max(1, int(veg.width * scale)),
                      max(1, int(veg.height * scale))), Image.LANCZOS)
    x, y = (px - veg.width) // 2, int(px * 0.52) - veg.height // 2

    shadow = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    sw, sh = int(veg.width * 0.86), int(veg.height * 0.30)
    ImageDraw.Draw(shadow).ellipse(
        (px // 2 - sw // 2, y + veg.height - sh // 2,
         px // 2 + sw // 2, y + veg.height + sh // 2),
        fill=(24, 34, 18, 150))
    tile.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(px * 0.022)))
    tile.alpha_composite(veg, (x, y))
    return tile


def main() -> None:
    tile = compose(render_patisson())
    OUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    tile.save(OUT_ICO, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"{OUT_ICO.relative_to(ROOT)}  "
          f"{OUT_ICO.stat().st_size / 1024:.0f} КБ  "
          f"размеры: {', '.join(str(s) for s in SIZES)}", flush=True)
    sys.stdout.flush()
    os._exit(0)          # Panda's ShowBase keeps threads alive


if __name__ == "__main__":
    main()

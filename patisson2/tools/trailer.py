"""Render a trailer for the game, straight out of the game.

    python -m patisson2.tools.trailer            # mp4 + gif
    python -m patisson2.tools.trailer --gif-only

A scripted camera flies through the same world the player walks, at the
same times of day and in the same weather, and the game's own procedural
music is rendered underneath it. Nothing is captured by hand and nothing
is edited afterwards, so the trailer cannot show a build that no longer
exists — re-run it after a change and it tells the truth again.

Frames are piped to ffmpeg as raw video instead of being written out as
files: a minute of 720p is a couple of gigabytes on disk and only a few
tens of megabytes once encoded.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

from panda3d.core import GraphicsOutput, Texture

from .shots import look_at

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "media"
FPS = 30
WIDTH, HEIGHT = 1280, 720


def ease(t: float) -> float:
    """Smooth start and stop, so no shot begins with a jerk."""
    return t * t * (3.0 - 2.0 * t)


class Shot:
    """One camera move: where it starts, where it ends, what it watches."""

    def __init__(self, seconds, eye0, eye1, target0, target1=None,
                 hour=None, season=None, weather=None, caption=None,
                 setup=None):
        self.seconds = seconds
        self.eye0, self.eye1 = eye0, eye1
        self.target0 = target0
        self.target1 = target1 or target0
        self.hour, self.season, self.weather = hour, season, weather
        self.caption = caption
        self.setup = setup


def shot_list():
    """The tour, in the order it plays."""
    return [
        Shot(5.0, (14.0, 16.0, 7.5), (6.0, 9.0, 4.2), (0.0, 3.0, 0.6),
             hour=7.0, season=0, weather="clear",
             caption="Ферма с патиссонами"),
        Shot(4.5, (-4.0, -2.2, 2.2), (3.5, -1.6, 1.9), (0.6, 3.0, 0.5),
             hour=9.5, season=0, caption="Грядки, борозды, всходы"),
        Shot(4.0, (-24.0, 14.0, 3.0), (-27.0, 19.0, 2.2), (-30.0, 24.0, 0.2),
             hour=11.0, season=0, caption="Пруд отражает небо"),
        Shot(4.0, (-8.0, -8.5, 3.4), (-10.0, -5.8, 2.6), (-13.0, -2.0, 1.2),
             hour=13.0, season=1, caption="Жители живут по распорядку"),
        # Far enough back that the barn stays whole in frame: flying at
        # its wall filled the shot with a flat red plank.
        Shot(4.0, (-8.5, -5.0, 6.2), (-12.0, -8.6, 4.8),
             (-19.0, -16.0, 1.6), hour=15.0, season=1,
             caption="Амбар, коровы и куры"),
        Shot(4.5, (10.0, 12.0, 6.0), (2.0, 12.0, 4.0), (0.0, 4.0, 0.8),
             hour=19.6, season=2, caption="Осень"),
        Shot(4.0, (8.0, 8.0, 3.4), (2.0, 6.0, 2.6), (2.0, -7.0, 1.4),
             hour=22.5, season=2, caption="Ночь: фонари на столбах"),
        Shot(4.0, (12.0, 10.0, 5.0), (4.0, 8.0, 3.4), (0.0, 3.0, 0.6),
             hour=12.0, season=3, weather="snow", caption="Зима"),
        Shot(5.0, (10.0, 14.0, 6.5), (14.0, 18.0, 8.0), (0.0, 3.0, 0.6),
             hour=17.4, season=0, weather="clear",
             caption="Патиссон гейм 2.0"),
    ]


def render(app, path_mp4: Path, quiet: bool = False):
    from ..world.daynight import SEASONS

    shots = shot_list()
    total = sum(int(s.seconds * FPS) for s in shots)
    tex = Texture()
    app.win.addRenderTexture(tex, GraphicsOutput.RTMCopyRam)

    ff = shutil.which("ffmpeg")
    if not ff:
        raise SystemExit("ffmpeg не найден — без него трейлер не собрать")
    proc = subprocess.Popen(
        [ff, "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pixel_format", "bgra",
         "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", str(FPS),
         "-i", "-", "-vf", "vflip", "-c:v", "libx264", "-preset", "medium",
         "-crf", "20", "-pix_fmt", "yuv420p", str(path_mp4)],
        stdin=subprocess.PIPE)

    day = app.cfg.game.day_length
    done = 0
    for shot in shots:
        if shot.season is not None:
            app.cycle.total_time = (shot.season * app.cfg.game.season_days
                                    * day)
        if shot.hour is not None:
            base = int(app.cycle.total_time / day) * day
            app.cycle.total_time = base + shot.hour / 24.0 * day
        if shot.weather is not None:
            app.weather_state.set_weather(shot.weather) \
                if hasattr(app.weather_state, "set_weather") \
                else setattr(app.weather_state, "weather", shot.weather)
        if shot.setup:
            shot.setup(app)
        app.hud.root.hide()
        frames = int(shot.seconds * FPS)
        for i in range(frames):
            t = ease(i / max(frames - 1, 1))
            eye = tuple(a + (b - a) * t for a, b in zip(shot.eye0, shot.eye1))
            tgt = tuple(a + (b - a) * t
                        for a, b in zip(shot.target0, shot.target1))
            look_at(app.player, tgt, eye)
            app.taskMgr.step()
            app.graphicsEngine.renderFrame()
            data = tex.getRamImage()
            proc.stdin.write(bytes(data))
            done += 1
            if not quiet and done % 30 == 0:
                print(f"  кадр {done}/{total}", flush=True)
    proc.stdin.close()
    proc.wait()


def render_music(path_wav: Path):
    """The trailer's soundtrack is the game's own morning theme."""
    import numpy as np
    import wave

    from ..audio.bank import MUSIC
    from ..audio.synth import SR

    track = MUSIC["music_morning"]()
    pcm = np.clip(track, -1.0, 1.0)
    data = (pcm * 32767).astype("<i2").tobytes()
    with wave.open(str(path_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    gif_only = "--gif-only" in argv

    from ..app import PatissonApp, configure
    from ..config import Config

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    silent = OUT_DIR / "_trailer-silent.mp4"
    music = OUT_DIR / "_trailer-music.wav"
    final = OUT_DIR / "trailer.mp4"
    gif = OUT_DIR / "trailer.gif"

    cfg = Config()
    cfg.graphics.width, cfg.graphics.height = WIDTH, HEIGHT
    cfg.graphics.vsync = False
    configure(cfg, offscreen=True)
    app = PatissonApp(cfg, offscreen=True, audio=False, use_settings=False)
    for _ in range(6):
        app.taskMgr.step()
    app.menu_new_game()
    for _ in range(8):
        app.taskMgr.step()

    print("рендер кадров...", flush=True)
    render(app, silent)

    ff = shutil.which("ffmpeg")
    if not gif_only:
        print("подкладываю музыку...", flush=True)
        render_music(music)
        # Which AAC encoder exists depends on how ffmpeg was built; older
        # builds carry libvo_aacenc and no "aac" at all, and mp3 in mp4 is
        # the last resort that every player still opens.
        for codec in ("aac", "libvo_aacenc", "libmp3lame"):
            done = subprocess.run(
                [ff, "-y", "-loglevel", "error", "-i", str(silent),
                 "-i", str(music), "-c:v", "copy", "-c:a", codec,
                 "-b:a", "160k", "-shortest", str(final)])
            if done.returncode == 0:
                print(f"  звук: {codec}", flush=True)
                break
        else:
            raise SystemExit("ffmpeg не смог закодировать звук")
        music.unlink(missing_ok=True)

    print("собираю gif для README...", flush=True)
    scale = "fps=12,scale=720:-1:flags=lanczos"
    palette = OUT_DIR / "_palette.png"
    # The two-pass palette gives a far better gif, but palettegen only
    # exists in ffmpeg 2.6 and later; fall back to a straight conversion
    # rather than shipping no gif at all.
    two_pass = subprocess.run(
        [ff, "-y", "-loglevel", "error", "-i", str(silent),
         "-vf", f"{scale},palettegen=stats_mode=diff", str(palette)])
    if two_pass.returncode == 0:
        subprocess.run(
            [ff, "-y", "-loglevel", "error", "-i", str(silent),
             "-i", str(palette), "-lavfi",
             f"{scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
             str(gif)], check=True)
    else:
        print("  palettegen недоступен — обычная конвертация", flush=True)
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(silent),
                        "-vf", scale, str(gif)], check=True)
    palette.unlink(missing_ok=True)
    silent.unlink(missing_ok=True)

    for p in (final, gif):
        if p.exists():
            print(f"{p.relative_to(ROOT)}  {p.stat().st_size / 1e6:.1f} МБ",
                  flush=True)
    sys.stdout.flush()
    import os
    os._exit(0)


if __name__ == "__main__":
    main()

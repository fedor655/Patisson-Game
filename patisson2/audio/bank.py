"""Definitions for every sound in the game.

Nothing here is recorded — each entry is a function that renders a buffer. The
runtime bakes them to WAV in a user cache on first launch, so the repository
carries the generator (a few kilobytes) instead of the audio (tens of megabytes).
"""

from __future__ import annotations

import math
import random

import numpy as np

from .synth import (
    SR,
    Track,
    adsr,
    bandpass,
    fade,
    highpass_fast,
    loopable,
    lowpass_fast,
    mix,
    midi,
    noise,
    normalize,
    note,
    perc_env,
    reverb,
    saw,
    seconds,
    silence,
    sine,
    soft_clip,
    square,
    time_axis,
    triangle,
)

# --------------------------------------------------------------- effects


def sfx_dig() -> np.ndarray:
    """Hoe biting into soil: a dull thud with a gritty scrape."""
    body = sine(np.linspace(150, 62, seconds(0.22)), 0.22) * perc_env(0.22, 0.002, 6.0)
    grit = bandpass(noise(0.26, 11), 260, 2600) * perc_env(0.26, 0.001, 5.0) * 0.55
    tail = lowpass_fast(noise(0.18, 12), 900) * perc_env(0.18, 0.02, 7.0) * 0.3
    out = mix(body, grit, tail, gains=(0.8, 1.0, 1.0))
    return normalize(fade(out, 0.001, 0.03), 0.85)


def sfx_water() -> np.ndarray:
    """Watering can pouring onto a bed."""
    dur = 1.15
    stream = bandpass(noise(dur, 21), 700, 5200)
    wobble = 1.0 + 0.35 * np.sin(2 * np.pi * 7.5 * time_axis(dur)).astype(np.float32)
    env = adsr(dur, 0.10, 0.15, 0.85, 0.30)
    out = stream * wobble * env * 0.6
    # A few droplet pings on the way down.
    t = Track(dur)
    t.add(0, out)
    rng = random.Random(4)
    for _ in range(9):
        at = rng.uniform(0.12, dur - 0.15)
        f = rng.uniform(900, 2200)
        t.add(at, sine(f, 0.07) * perc_env(0.07, 0.001, 9.0) * 0.16)
    return normalize(fade(t.result(), 0.02, 0.12), 0.7)


def sfx_plant() -> np.ndarray:
    """Pressing a seed into the ground."""
    rustle = bandpass(noise(0.28, 31), 900, 4800) * perc_env(0.28, 0.004, 6.5) * 0.45
    pat = sine(np.linspace(210, 110, seconds(0.14)), 0.14) * perc_env(0.14, 0.002, 8.0)
    return normalize(fade(mix(rustle, pat, gains=(1.0, 0.7)), 0.002, 0.05), 0.65)


def sfx_harvest() -> np.ndarray:
    """Stem snapping, then leaves settling."""
    snap = bandpass(noise(0.09, 41), 1400, 6500) * perc_env(0.09, 0.001, 12.0)
    thump = sine(np.linspace(320, 150, seconds(0.16)), 0.16) * perc_env(0.16, 0.002, 7.0)
    leaves = bandpass(noise(0.34, 42), 1800, 7000) * perc_env(0.34, 0.02, 4.5) * 0.30
    return normalize(
        fade(mix(snap, thump, leaves, gains=(0.9, 0.6, 1.0)), 0.001, 0.06), 0.8)


def sfx_cast() -> np.ndarray:
    """Fishing line whistling out over the pond."""
    dur = 0.55
    sweep = np.linspace(2600, 700, seconds(dur))
    air = bandpass(noise(dur, 51), 800, 6000)
    whistle = sine(sweep, dur) * 0.25
    env = adsr(dur, 0.03, 0.10, 0.55, 0.30)
    return normalize(fade(mix(air, whistle, gains=(0.5, 1.0)) * env, 0.01, 0.10), 0.55)


def sfx_splash() -> np.ndarray:
    body = lowpass_fast(noise(0.45, 61), 2600) * perc_env(0.45, 0.002, 5.0)
    plop = sine(np.linspace(700, 190, seconds(0.13)), 0.13) * perc_env(0.13, 0.001, 8.0)
    drops = Track(0.5)
    drops.add(0, body * 0.7).add(0, plop * 0.55)
    rng = random.Random(7)
    for _ in range(5):
        drops.add(rng.uniform(0.08, 0.4),
                  sine(rng.uniform(1200, 2600), 0.05) * perc_env(0.05, 0.001, 10.0) * 0.14)
    return normalize(fade(drops.result(), 0.002, 0.08), 0.75)


def sfx_catch() -> np.ndarray:
    """Bright three-note flourish for landing a fish."""
    t = Track(0.85)
    for i, n in enumerate((note("D", 5), note("F#", 5), note("A", 5))):
        v = (sine(n, 0.42) * 0.7 + triangle(n * 2, 0.42) * 0.25) * perc_env(0.42, 0.004, 4.5)
        t.add(0.09 * i, v, 0.8)
    return normalize(reverb(t.result(), 0.5, 0.25), 0.7)


def sfx_coin() -> np.ndarray:
    t = Track(0.7)
    for i, n in enumerate((note("A", 5), note("E", 6))):
        v = (sine(n, 0.35) + sine(n * 2.01, 0.35) * 0.4) * perc_env(0.35, 0.001, 7.0)
        t.add(0.06 * i, v, 0.55)
    return normalize(reverb(t.result(), 0.35, 0.2), 0.6)


def sfx_click() -> np.ndarray:
    tick = sine(np.linspace(1500, 900, seconds(0.045)), 0.045) * perc_env(0.045, 0.001, 12.0)
    return normalize(fade(tick, 0.001, 0.01), 0.4)


def sfx_error() -> np.ndarray:
    a = sine(note("E", 3), 0.13) * perc_env(0.13, 0.004, 5.0)
    b = sine(note("D#", 3), 0.20) * perc_env(0.20, 0.004, 5.0)
    t = Track(0.36).add(0, a, 0.6).add(0.11, b, 0.6)
    return normalize(t.result(), 0.45)


def sfx_achieve() -> np.ndarray:
    """Short fanfare for achievements and completed quests."""
    t = Track(1.7)
    melody = [("C", 5, 0.00), ("E", 5, 0.13), ("G", 5, 0.26), ("C", 6, 0.40)]
    for name, octv, at in melody:
        f = note(name, octv)
        v = (triangle(f, 0.85) * 0.6 + sine(f * 2, 0.85) * 0.2) * perc_env(0.85, 0.006, 3.0)
        t.add(at, v, 0.7)
    pad = triangle(note("C", 3), 1.5) * adsr(1.5, 0.08, 0.4, 0.35, 0.6)
    t.add(0.0, pad, 0.22)
    return normalize(reverb(t.result(), 0.7, 0.3), 0.75)


def _footstep(seed: int) -> np.ndarray:
    rng = random.Random(seed)
    dur = 0.20
    crunch = bandpass(noise(dur, seed), rng.uniform(400, 700), rng.uniform(3200, 5200))
    body = sine(np.linspace(rng.uniform(130, 175), 60, seconds(dur)), dur)
    env = perc_env(dur, 0.002, rng.uniform(7.0, 11.0))
    return normalize(
        fade(mix(crunch * env, body * env, gains=(0.5, 0.45)), 0.001, 0.04), 0.32)


def sfx_well() -> np.ndarray:
    """Rope drum creaking as the handle turns."""
    dur = 1.5
    t = Track(dur)
    rng = random.Random(9)
    for i in range(7):
        at = i * 0.19 + rng.uniform(-0.02, 0.02)
        f = rng.uniform(320, 470)
        creak = (saw(f, 0.16, 7) * perc_env(0.16, 0.01, 5.0)
                 * (0.5 + 0.5 * math.sin(i)))
        t.add(at, bandpass(creak, 250, 2400), 0.35)
    rope = bandpass(noise(dur, 71), 200, 1400) * adsr(dur, 0.1, 0.2, 0.4, 0.4) * 0.2
    t.add(0, rope)
    return normalize(t.result(), 0.5)


def sfx_cluck() -> np.ndarray:
    t = Track(0.55)
    rng = random.Random(13)
    for i in range(3):
        f0 = rng.uniform(700, 1050)
        seg = 0.075
        sweep = np.linspace(f0, f0 * rng.uniform(0.55, 0.8), seconds(seg))
        v = square(sweep, seg, 5) * perc_env(seg, 0.004, 6.0)
        t.add(0.14 * i, bandpass(v, 400, 4200), 0.4)
    return normalize(t.result(), 0.45)


def sfx_moo() -> np.ndarray:
    dur = 1.35
    base = np.concatenate([
        np.linspace(150, 132, seconds(0.5)),
        np.linspace(132, 118, seconds(0.55)),
        np.linspace(118, 96, seconds(dur - 1.05)),
    ])
    v = saw(base, dur, 10) * adsr(dur, 0.12, 0.25, 0.75, 0.45)
    v = lowpass_fast(v, 1500)
    breath = bandpass(noise(dur, 81), 300, 1800) * adsr(dur, 0.2, 0.3, 0.4, 0.4) * 0.12
    return normalize(reverb(mix(v, breath, gains=(0.7, 1.0)), 0.4, 0.18), 0.6)


def _warble(f0: float, f1: float, dur: float, gain: float = 1.0) -> np.ndarray:
    """One swooping whistle — the building block of every bird here.

    Used to be a bare sine sweep with a whisper of second harmonic — a
    signal generator, not a throat, and the player said so: "птицы поют
    немного по цифровому". A songbird's tone carries a fast shallow
    vibrato, real harmonic colour, a breath of air, and an attack that
    is not a click.
    """
    n = seconds(dur)
    t = np.arange(n, dtype=np.float64) / SR
    sweep = np.linspace(f0, f1, n)
    vib = 1.0 + 0.022 * np.sin(2 * np.pi * 11.3 * t + f0 * 0.013)
    f = sweep * vib
    body = (sine(f, dur) * 0.76 + sine(f * 2.0, dur) * 0.34
            + sine(f * 3.0, dur) * 0.10)
    breath = bandpass(noise(dur, int(f0) % 997), f0 * 0.8, f0 * 2.6) * 0.14
    out = (body + breath) * perc_env(dur, 0.014, 4.2) * gain
    return lowpass_fast(out, 7800)


def sfx_bird(seed: int = 0) -> np.ndarray:
    """A single songbird phrase, meant to come out of one particular tree."""
    rng = random.Random(301 + seed)
    dur = 1.1
    t = Track(dur)
    at = 0.02
    for _ in range(rng.randint(2, 4)):
        f = rng.uniform(2300, 3900)
        seg = rng.uniform(0.07, 0.13)
        t.add(at, _warble(f, f * rng.uniform(0.75, 1.45), seg), rng.uniform(0.5, 1.0))
        at += seg + rng.uniform(0.04, 0.14)
    if rng.random() < 0.6:                       # closing trill
        f = rng.uniform(2800, 4200)
        for k in range(rng.randint(3, 6)):
            t.add(at + k * 0.055, _warble(f, f * 1.05, 0.045), 0.5)
    return normalize(reverb(t.result(), 0.45, 0.16), 0.55)


def sfx_frog() -> np.ndarray:
    """Croak: a low buzzing pulse train, the way a real one stutters."""
    dur = 0.75
    t = Track(dur)
    rng = random.Random(311)
    at = 0.02
    for _ in range(rng.randint(2, 3)):
        seg = rng.uniform(0.14, 0.22)
        f = rng.uniform(115, 165)
        buzz = saw(f, seg, 9)
        # Amplitude-modulate hard: that rattle is what makes it a frog.
        am = (0.55 + 0.45 * np.sign(np.sin(2 * np.pi * 42.0 * time_axis(seg)))
              ).astype(np.float32)
        v = lowpass_fast(buzz * am, 1300) * adsr(seg, 0.02, 0.05, 0.8, 0.08)
        t.add(at, v, rng.uniform(0.6, 0.95))
        at += seg + rng.uniform(0.05, 0.12)
    return normalize(reverb(t.result(), 0.5, 0.2), 0.5)


def sfx_owl() -> np.ndarray:
    """Two soft hoots, an octave apart in feel if not in pitch."""
    t = Track(1.6)
    for i, (f, at, gain) in enumerate(((392.0, 0.0, 1.0), (352.0, 0.62, 0.8))):
        dur = 0.42
        bend = np.concatenate([
            np.linspace(f * 0.94, f, seconds(0.10)),
            np.full(seconds(dur) - seconds(0.10), f, dtype=np.float32),
        ])
        v = sine(bend, dur) * 0.8 + sine(bend * 2.0, dur) * 0.06
        breath = lowpass_fast(noise(dur, 321 + i), 700) * 0.08
        t.add(at, lowpass_fast(v + breath, 1200) * adsr(dur, 0.09, 0.12, 0.75, 0.20),
              gain * 0.9)
    return normalize(reverb(t.result(), 0.8, 0.3), 0.5)


def sfx_caw() -> np.ndarray:
    """The crow, when it lands on your beds. Harsh on purpose."""
    dur = 0.9
    t = Track(dur)
    rng = random.Random(331)
    at = 0.0
    for _ in range(2):
        seg = rng.uniform(0.16, 0.24)
        f = rng.uniform(620, 780)
        harsh = saw(np.linspace(f, f * 0.72, seconds(seg)), seg, 14)
        rasp = bandpass(noise(seg, 332), 900, 5200) * 0.5
        v = bandpass(harsh + rasp, 500, 5000) * perc_env(seg, 0.008, 4.0)
        t.add(at, v, rng.uniform(0.7, 1.0))
        at += seg + rng.uniform(0.12, 0.2)
    return normalize(t.result(), 0.55)


def sfx_thunder() -> np.ndarray:
    dur = 2.8
    rumble = lowpass_fast(noise(dur, 91), 260)
    env = adsr(dur, 0.03, 0.5, 0.45, 1.6)
    crack = bandpass(noise(0.3, 92), 600, 5000) * perc_env(0.3, 0.001, 6.0) * 0.4
    out = Track(dur).add(0, rumble * env * 0.9).add(0.02, crack)
    return normalize(reverb(out.result(), 0.9, 0.35), 0.8)


# ------------------------------------------------------------- ambience


def amb_wind(duration: float = 14.0) -> np.ndarray:
    """A steady bed of moving air, not surf.

    The gust envelope used to be two pure sines (0.07 and 0.031 Hz) at
    almost 70 % depth over a 520 Hz rumble — a swell rolling in every
    twelve seconds, which is the signature of waves on a beach, and the
    player heard exactly that. Real wind wanders: the envelope is now
    slow smoothed noise at a fraction of the depth, gusts brighten the
    hiss more than they raise the rumble, and the bed sits a little
    higher so it reads as air in leaves rather than water on sand.
    """
    base = lowpass_fast(noise(duration, 101), 640)
    # Irregular slow wander instead of a metronomic swell.
    slow = lowpass_fast(noise(duration, 103), 0.35)
    slow = slow / (float(np.abs(slow).max()) + 1e-9)
    # A touch of faster flutter so held air feels alive.
    flutter = lowpass_fast(noise(duration, 104), 2.5)
    flutter = flutter / (float(np.abs(flutter).max()) + 1e-9)
    gust = (1.0 + 0.17 * slow + 0.06 * flutter).astype(np.float32)
    hiss = bandpass(noise(duration, 102), 800, 4600) * 0.22
    # Gusts sharpen the hiss (squared) more than the low bed (linear).
    out = mix(base * gust, hiss * gust * gust, gains=(0.62, 1.0))
    return normalize(loopable(out, 1.6), 0.42)


def amb_birds(duration: float = 16.0) -> np.ndarray:
    """Daytime: distant birdsong over a soft bed of wind."""
    t = Track(duration)
    t.add(0, amb_wind(duration) * 0.55)
    rng = random.Random(23)
    for _ in range(46):
        at = rng.uniform(0.2, duration - 1.2)
        kind = rng.random()
        if kind < 0.5:
            # Two-note whistle, from the same throat as the tree birds —
            # these used to be raw sine sweeps with no harmonics at all.
            f = rng.uniform(2200, 3600)
            t.add(at, _warble(f, f * rng.uniform(1.1, 1.4), 0.09),
                  rng.uniform(0.05, 0.12))
            t.add(at + 0.13, _warble(f * 1.2, f * 0.85, 0.11),
                  rng.uniform(0.04, 0.10))
        else:
            # Trill.
            f = rng.uniform(2600, 4200)
            for k in range(rng.randint(3, 6)):
                fk = f * (1.0 + 0.06 * (k % 2))
                t.add(at + k * 0.062, _warble(fk, fk, 0.05),
                      rng.uniform(0.03, 0.08))
    return normalize(loopable(t.result(), 1.8), 0.40)


def amb_crickets(duration: float = 12.0) -> np.ndarray:
    t = Track(duration)
    t.add(0, lowpass_fast(noise(duration, 111), 300) * 0.25)
    rng = random.Random(29)
    # A chorus of chirpers, each with its own steady rhythm.
    for _ in range(14):
        f = rng.uniform(3800, 5200)
        period = rng.uniform(0.28, 0.5)
        gain = rng.uniform(0.03, 0.09)
        offset = rng.uniform(0, period)
        at = offset
        while at < duration - 0.1:
            burst = seconds(0.028)
            chirp = sine(f, 0.028) * np.hanning(burst).astype(np.float32)
            t.add(at, chirp, gain)
            at += period
    out = mix(bandpass(t.result(), 1800, 7000),
              lowpass_fast(noise(duration, 112), 240), gains=(1.0, 0.12))
    return normalize(loopable(out, 1.4), 0.34)


def amb_rain(duration: float = 12.0) -> np.ndarray:
    hiss = bandpass(noise(duration, 121), 700, 7500)
    body = lowpass_fast(noise(duration, 122), 1400) * 0.5
    t = time_axis(duration)
    swell = (0.75 + 0.25 * np.sin(2 * np.pi * 0.05 * t)).astype(np.float32)
    out = mix(hiss, body, gains=(0.7, 1.0)) * swell
    # Occasional heavy drops on the roof.
    tr = Track(duration).add(0, out)
    rng = random.Random(31)
    for _ in range(70):
        at = rng.uniform(0, duration - 0.1)
        f = rng.uniform(1100, 2800)
        tr.add(at, sine(f, 0.03) * perc_env(0.03, 0.001, 10.0), rng.uniform(0.02, 0.06))
    return normalize(loopable(tr.result(), 1.5), 0.5)


def amb_water(duration: float = 10.0) -> np.ndarray:
    """Pond edge: small waves, and the odd drip off a reed."""
    t = time_axis(duration)
    lap = lowpass_fast(noise(duration, 131), 900)
    # Two slow swells at incommensurate rates so the loop never obviously ticks.
    swell = (0.6 + 0.4 * np.sin(2 * np.pi * 0.21 * t)
             + 0.2 * np.sin(2 * np.pi * 0.13 * t + 0.7)).astype(np.float32)
    body = bandpass(noise(duration, 132), 180, 2400) * 0.35
    tr = Track(duration).add(0, lap * swell * 0.8).add(0, body * swell)
    rng = random.Random(37)
    for _ in range(22):
        at = rng.uniform(0, duration - 0.1)
        f = rng.uniform(900, 2400)
        tr.add(at, sine(f, 0.045) * perc_env(0.045, 0.001, 9.0), rng.uniform(0.02, 0.07))
    return normalize(loopable(tr.result(), 1.4), 0.34)


def amb_leaves(duration: float = 11.0) -> np.ndarray:
    """Under the trees: the wind bed, but with leaves in it."""
    t = time_axis(duration)
    gust = (0.45 + 0.55 * np.sin(2 * np.pi * 0.09 * t + 0.4)
            + 0.2 * np.sin(2 * np.pi * 0.037 * t)).astype(np.float32)
    rustle = bandpass(noise(duration, 141), 1600, 8000) * gust
    trunk = lowpass_fast(noise(duration, 142), 340) * gust * 0.45
    # Creaking branches, sparse and low.
    tr = Track(duration).add(0, rustle * 0.7).add(0, trunk)
    rng = random.Random(43)
    for _ in range(6):
        at = rng.uniform(0, duration - 0.6)
        f = rng.uniform(180, 340)
        creak = saw(np.linspace(f, f * 0.9, seconds(0.5)), 0.5, 6)
        tr.add(at, bandpass(creak, 150, 1600) * perc_env(0.5, 0.08, 3.0),
               rng.uniform(0.03, 0.08))
    return normalize(loopable(tr.result(), 1.5), 0.30)


# ---------------------------------------------------------------- music

BPM = 88.0
BEAT = 60.0 / BPM
BAR = BEAT * 4


def _pad(freq: float, duration: float) -> np.ndarray:
    a = triangle(freq, duration)
    b = triangle(freq * 1.004, duration)
    c = sine(freq * 0.5, duration) * 0.5
    env = adsr(duration, 0.35, 0.5, 0.72, 0.9)
    return lowpass_fast((a + b) * 0.5 + c, 2200.0) * env


def _pluck(freq: float, duration: float) -> np.ndarray:
    body = sine(freq, duration) * 0.7 + triangle(freq * 2.0, duration) * 0.18
    body += sine(freq * 3.01, duration) * 0.07
    return lowpass_fast(body * perc_env(duration, 0.004, 4.2), 5200.0)


def _bass(freq: float, duration: float) -> np.ndarray:
    v = sine(freq, duration) * 0.85 + triangle(freq, duration) * 0.15
    return v * adsr(duration, 0.02, 0.15, 0.6, 0.25)


def _bell(freq: float, duration: float) -> np.ndarray:
    v = (sine(freq, duration) + sine(freq * 2.76, duration) * 0.35
         + sine(freq * 5.4, duration) * 0.12)
    return v * perc_env(duration, 0.003, 2.6)


# Chord = (root midi note, [scale degrees as semitone offsets])
MAJOR = [0, 4, 7]
MINOR = [0, 3, 7]
SUS = [0, 5, 7]

PROGRESSIONS = {
    # (root midi, chord shape) — 4 chords, two bars each.
    "morning": [(60, MAJOR), (67, MAJOR), (69, MINOR), (65, MAJOR)],
    "day": [(60, MAJOR), (65, MAJOR), (67, MAJOR), (64, MINOR)],
    "evening": [(65, MAJOR), (60, MAJOR), (62, MINOR), (67, SUS)],
    "night": [(57, MINOR), (64, MINOR), (65, MAJOR), (60, MAJOR)],
}

PENTATONIC = [0, 2, 4, 7, 9, 12, 14, 16]


def music(name: str, cycles: int = 3, seed: int = 0) -> np.ndarray:
    """Render a looping music bed for one time of day."""
    prog = PROGRESSIONS[name]
    bars_per_chord = 2
    total_bars = len(prog) * bars_per_chord * cycles
    duration = total_bars * BAR + 2.0
    t = Track(duration)
    rng = random.Random(seed if seed else hash(name) & 0xFFFF)

    night = name == "night"
    evening = name == "evening"
    pad_gain = 0.30 if not night else 0.34
    pluck_gain = 0.24 if not night else 0.16

    for cycle in range(cycles):
        for ci, (root, shape) in enumerate(prog):
            bar_index = (cycle * len(prog) + ci) * bars_per_chord
            at = bar_index * BAR
            chord_len = BAR * bars_per_chord

            # Pad: the chord held underneath everything.
            for k, semi in enumerate(shape):
                f = midi(root + semi)
                t.add(at, _pad(f, chord_len * 0.98), pad_gain * (0.9 if k else 1.0))

            # Bass: root on the downbeat, fifth halfway through.
            t.add(at, _bass(midi(root - 24), BAR * 0.9), 0.32)
            if not night:
                t.add(at + BAR, _bass(midi(root + shape[2] - 24), BAR * 0.8), 0.22)

            # Arpeggio.
            steps = 8 if not night else 4
            for s in range(steps * bars_per_chord):
                if night and rng.random() < 0.45:
                    continue
                if not night and rng.random() < 0.12:
                    continue
                semi = shape[s % len(shape)] + 12 * (1 if (s // len(shape)) % 2 else 0)
                f = midi(root + semi)
                when = at + s * (chord_len / (steps * bars_per_chord))
                length = chord_len / (steps * bars_per_chord) * rng.uniform(1.4, 2.4)
                t.add(when, _pluck(f, length), pluck_gain * rng.uniform(0.7, 1.05))

            # Melody: a phrase over the first bar of every other chord.
            if (cycle * len(prog) + ci) % 2 == 0:
                pos = at + BEAT * rng.choice([0, 1, 2])
                for _ in range(rng.randint(2, 4)):
                    semi = rng.choice(PENTATONIC)
                    f = midi(root + semi + 12)
                    length = BEAT * rng.choice([0.5, 1.0, 1.0, 1.5])
                    voice = _bell(f, length * 1.6) if night else _pluck(f, length * 1.5)
                    t.add(pos, voice, (0.14 if night else 0.20) * rng.uniform(0.8, 1.1))
                    pos += length
                    if pos > at + chord_len:
                        break

    out = t.result()
    out = lowpass_fast(out, 6000.0 if not evening else 4600.0)
    out = reverb(out, 0.75 if night else 0.55, 0.30 if night else 0.22)
    out = soft_clip(out, 1.1)
    return normalize(loopable(out, 1.9), 0.62)


# ------------------------------------------------------------------ index

SFX = {
    "dig": sfx_dig,
    "water": sfx_water,
    "plant": sfx_plant,
    "harvest": sfx_harvest,
    "cast": sfx_cast,
    "splash": sfx_splash,
    "catch": sfx_catch,
    "coin": sfx_coin,
    "click": sfx_click,
    "error": sfx_error,
    "achieve": sfx_achieve,
    "well": sfx_well,
    "cluck": sfx_cluck,
    "moo": sfx_moo,
    "thunder": sfx_thunder,
    # Three birds rather than one: a single phrase repeating from the same
    # wood is the fastest way to make a soundscape feel canned.
    "bird1": lambda: sfx_bird(1),
    "bird2": lambda: sfx_bird(2),
    "bird3": lambda: sfx_bird(3),
    "frog": sfx_frog,
    "owl": sfx_owl,
    "caw": sfx_caw,
    "step1": lambda: _footstep(201),
    "step2": lambda: _footstep(202),
    "step3": lambda: _footstep(203),
    "step4": lambda: _footstep(204),
}

AMBIENCE = {
    "amb_day": amb_birds,
    "amb_night": amb_crickets,
    "amb_wind": amb_wind,
    "amb_rain": amb_rain,
    # These two are mixed by where the player is standing, not by the clock.
    "amb_water": amb_water,
    "amb_leaves": amb_leaves,
}

MUSIC = {
    "music_morning": lambda: music("morning", 3, 11),
    "music_day": lambda: music("day", 3, 22),
    "music_evening": lambda: music("evening", 3, 33),
    "music_night": lambda: music("night", 3, 44),
}

ALL = {**SFX, **AMBIENCE, **MUSIC}

# Bumping this regenerates the cache on the next launch.
BANK_VERSION = 4

"""A small numpy synthesiser.

Every sound in the game is generated from this — there are no recorded assets.
Output is mono float32 in [-1, 1] at :data:`SR`, written out as 16-bit WAV.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import numpy as np

SR = 22050


# ------------------------------------------------------------------ helpers


def seconds(n: float) -> int:
    return max(1, int(round(n * SR)))


def silence(duration: float) -> np.ndarray:
    return np.zeros(seconds(duration), dtype=np.float32)


def time_axis(duration: float) -> np.ndarray:
    return np.arange(seconds(duration), dtype=np.float64) / SR


def note(name: str, octave: int = 4) -> float:
    """Note name -> frequency. 'A4' is 440 Hz."""
    semis = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4,
             "F#": -3, "G": -2, "G#": -1, "A": 0, "A#": 1, "B": 2}
    return 440.0 * 2.0 ** ((semis[name] + (octave - 4) * 12) / 12.0)


def midi(n: int) -> float:
    return 440.0 * 2.0 ** ((n - 69) / 12.0)


# -------------------------------------------------------------- oscillators


def sine(freq, duration: float, phase: float = 0.0) -> np.ndarray:
    t = time_axis(duration)
    f = np.asarray(freq, dtype=np.float64)
    if f.ndim == 0:
        ph = 2 * np.pi * f * t + phase
    else:
        ph = 2 * np.pi * np.cumsum(f) / SR + phase
    return np.sin(ph).astype(np.float32)


def triangle(freq, duration: float) -> np.ndarray:
    s = sine(freq, duration)
    # Odd harmonics with 1/n^2 falloff — soft, flute-like.
    out = s.copy()
    for k, amp in ((3, -1 / 9), (5, 1 / 25), (7, -1 / 49)):
        out += amp * sine(np.asarray(freq) * k, duration)
    return (out / 1.16).astype(np.float32)


def saw(freq, duration: float, harmonics: int = 12) -> np.ndarray:
    out = np.zeros(seconds(duration), dtype=np.float32)
    for k in range(1, harmonics + 1):
        out += (sine(np.asarray(freq) * k, duration) / k).astype(np.float32)
    return (out / math.log(harmonics + 1) * 0.6).astype(np.float32)


def square(freq, duration: float, harmonics: int = 9) -> np.ndarray:
    out = np.zeros(seconds(duration), dtype=np.float32)
    for k in range(1, harmonics + 1, 2):
        out += (sine(np.asarray(freq) * k, duration) / k).astype(np.float32)
    return (out * 0.8).astype(np.float32)


def noise(duration: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, seconds(duration)).astype(np.float32)


# --------------------------------------------------------------- envelopes


def adsr(duration: float, attack=0.01, decay=0.08, sustain=0.7,
         release=0.15) -> np.ndarray:
    n = seconds(duration)
    env = np.zeros(n, dtype=np.float32)
    a = min(seconds(attack), n)
    d = min(seconds(decay), max(n - a, 0))
    r = min(seconds(release), max(n - a - d, 0))
    s = max(n - a - d - r, 0)
    idx = 0
    if a:
        env[idx:idx + a] = np.linspace(0.0, 1.0, a)
        idx += a
    if d:
        env[idx:idx + d] = np.linspace(1.0, sustain, d)
        idx += d
    if s:
        env[idx:idx + s] = sustain
        idx += s
    if r:
        env[idx:idx + r] = np.linspace(sustain, 0.0, r)
    return env


def perc_env(duration: float, attack=0.004, curve=4.0) -> np.ndarray:
    """Sharp attack, exponential decay — plucks, hits, clicks."""
    n = seconds(duration)
    env = np.ones(n, dtype=np.float32)
    a = min(seconds(attack), n)
    if a:
        env[:a] = np.linspace(0.0, 1.0, a)
    tail = np.linspace(0.0, 1.0, max(n - a, 1))
    env[a:] = np.exp(-curve * tail)
    return env


def fade(sig: np.ndarray, fade_in=0.005, fade_out=0.02) -> np.ndarray:
    out = sig.copy()
    a = min(seconds(fade_in), len(out) // 2)
    b = min(seconds(fade_out), len(out) // 2)
    if a:
        out[:a] *= np.linspace(0.0, 1.0, a)
    if b:
        out[-b:] *= np.linspace(1.0, 0.0, b)
    return out


# ----------------------------------------------------------------- filters


def lowpass(sig: np.ndarray, cutoff: float) -> np.ndarray:
    """One-pole lowpass. cutoff in Hz."""
    if cutoff >= SR / 2:
        return sig
    x = math.exp(-2.0 * math.pi * cutoff / SR)
    b = 1.0 - x
    # Vectorised IIR via lfilter-style recursion.
    out = np.empty_like(sig)
    acc = 0.0
    for i in range(len(sig)):
        acc = b * sig[i] + x * acc
        out[i] = acc
    return out


def lowpass_fast(sig: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    """Frequency-domain lowpass — much faster than the recursion for long
    buffers, which matters when rendering minutes of music."""
    n = len(sig)
    spec = np.fft.rfft(sig)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    with np.errstate(divide="ignore"):
        resp = 1.0 / np.sqrt(1.0 + (freqs / max(cutoff, 1e-3)) ** (2 * order))
    return np.fft.irfft(spec * resp, n).astype(np.float32)


def highpass_fast(sig: np.ndarray, cutoff: float, order: int = 2) -> np.ndarray:
    n = len(sig)
    spec = np.fft.rfft(sig)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    ratio = np.divide(max(cutoff, 1e-3), np.maximum(freqs, 1e-6))
    resp = 1.0 / np.sqrt(1.0 + ratio ** (2 * order))
    return np.fft.irfft(spec * resp, n).astype(np.float32)


def bandpass(sig: np.ndarray, low: float, high: float) -> np.ndarray:
    return highpass_fast(lowpass_fast(sig, high), low)


# ----------------------------------------------------------------- effects


def delay(sig: np.ndarray, time: float, feedback: float = 0.35,
          mix: float = 0.3, taps: int = 4) -> np.ndarray:
    out = sig.copy()
    step = seconds(time)
    gain = feedback
    for i in range(1, taps + 1):
        shift = step * i
        if shift >= len(sig):
            break
        out[shift:] += sig[:-shift] * gain * mix
        gain *= feedback
    return out


def reverb(sig: np.ndarray, room: float = 0.6, mix: float = 0.28,
           seed: int = 3) -> np.ndarray:
    """Cheap Schroeder-ish reverb: a few detuned delay taps, then smoothed."""
    rng = np.random.default_rng(seed)
    wet = np.zeros(len(sig) + seconds(0.6), dtype=np.float32)
    wet[: len(sig)] += sig
    for _ in range(9):
        t = rng.uniform(0.017, 0.115) * (0.5 + room)
        g = rng.uniform(0.18, 0.45) * room
        shift = seconds(t)
        if shift < len(sig):
            wet[shift:shift + len(sig)] += sig * g
    wet = lowpass_fast(wet, 4200.0)
    out = np.zeros(len(sig), dtype=np.float32)
    out += sig * (1.0 - mix)
    out += wet[: len(sig)] * mix
    return out.astype(np.float32)


def soft_clip(sig: np.ndarray, drive: float = 1.0) -> np.ndarray:
    return np.tanh(sig * drive).astype(np.float32)


def pan_stub(sig: np.ndarray) -> np.ndarray:
    return sig


def mix(*sigs: np.ndarray, gains: tuple[float, ...] | None = None) -> np.ndarray:
    """Sum buffers of differing lengths, padding to the longest."""
    sigs = [s for s in sigs if len(s)]
    if not sigs:
        return np.zeros(1, dtype=np.float32)
    n = max(len(s) for s in sigs)
    out = np.zeros(n, dtype=np.float32)
    for i, s in enumerate(sigs):
        g = 1.0 if gains is None else gains[i]
        out[: len(s)] += s * g
    return out


def normalize(sig: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(sig))) if len(sig) else 0.0
    if m < 1e-9:
        return sig
    return (sig * (peak / m)).astype(np.float32)


def loopable(sig: np.ndarray, crossfade: float = 0.35) -> np.ndarray:
    """Wrap the tail over the head so the buffer loops without a click."""
    n = seconds(crossfade)
    if n * 2 >= len(sig):
        return fade(sig, 0.01, 0.01)
    out = sig.copy()
    tail = out[-n:].copy()
    ramp = np.linspace(0.0, 1.0, n).astype(np.float32)
    out[:n] = out[:n] * ramp + tail * (1.0 - ramp)
    return out[:-n]


# ---------------------------------------------------------------- sequencer


class Track:
    """Mix events into a fixed-length buffer at sample-accurate offsets."""

    def __init__(self, duration: float):
        self.buf = np.zeros(seconds(duration), dtype=np.float32)

    def add(self, at: float, sig: np.ndarray, gain: float = 1.0) -> "Track":
        start = seconds(at) if at > 0 else 0
        if start >= len(self.buf):
            return self
        end = min(start + len(sig), len(self.buf))
        self.buf[start:end] += sig[: end - start] * gain
        return self

    def result(self) -> np.ndarray:
        return self.buf


# ------------------------------------------------------------------- output


def write_wav(path: str | Path, sig: np.ndarray, peak: float = 0.85) -> Path:
    """Write mono 16-bit WAV, atomically.

    Music renders on a daemon thread; if the game exits mid-render a partially
    written file would be loaded as a valid cache entry on the next launch, so
    the file only appears under its real name once it is complete.
    """
    import os

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    data = np.clip(normalize(sig, peak), -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    os.replace(tmp, path)
    return path

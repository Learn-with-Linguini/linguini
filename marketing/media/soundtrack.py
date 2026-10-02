"""Voiceover, music and sound effects for the Linguini explainer.

The voice is Kokoro-82M (Apache-2.0), run locally through kokoro-onnx. The music is
an original 120 BPM track synthesised here, so it has no licence to clear and its
beat grid is exact: scene cuts in explainer.py sit on beats, and the key cuts sit
on downbeats. Sound effects are placed at the burst and transition times that the
renderer records while drawing frames.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

SR = 48000
BPM = 120
BEAT = 60 / BPM
BAR = 4 * BEAT
FIRST_DOWNBEAT = 0.5
CACHE = Path(__file__).resolve().parent / ".cache"
RNG = np.random.default_rng(3216)

# D major: I - V - vi - IV, voiced to move smoothly.
CHORDS = [(62, 66, 69), (61, 64, 69), (62, 66, 71), (62, 67, 71)]
ROOTS = [38, 33, 35, 31]
HOOK = [(0, 78), (0.5, 81), (1, 83), (1.5, 81), (2, 86), (3, 83), (3.5, 81), (4, 78), (5, 81), (6, 74)]


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def env_t(dur):
    return np.arange(int(dur * SR)) / SR


def place(buf, t, sig, gain=1.0, pan=0.0):
    """Mix a mono signal into a stereo buffer at time t with constant-power pan."""
    start = round(t * SR)
    if start >= len(buf) or len(sig) == 0:
        return
    if start < 0:
        sig, start = sig[-start:], 0
    sig = sig[: len(buf) - start] * gain
    angle = (pan + 1) * np.pi / 4
    buf[start:start + len(sig), 0] += sig * np.cos(angle)
    buf[start:start + len(sig), 1] += sig * np.sin(angle)


def highpass(x):
    return np.diff(x, prepend=0.0)


def smooth(x, seconds):
    n = max(1, int(seconds * SR))
    return np.convolve(x, np.ones(n) / n, mode="same")


def noise(dur):
    return RNG.uniform(-1, 1, int(dur * SR))


def fade_in(sig, seconds=0.003):
    n = min(len(sig), max(1, int(seconds * SR)))
    sig[:n] *= np.linspace(0, 1, n)
    return sig


# ---------------------------------------------------------------- instruments

def pluck(f, dur=0.5):
    t = env_t(dur)
    sig = sum(np.sin(2 * np.pi * n * f * t) * np.exp(-t * (5 + 3.5 * n)) / n ** 1.3 for n in range(1, 9))
    return fade_in(sig * 0.6)


def glock(f, dur=1.4):
    t = env_t(dur)
    sig = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t * d) for r, a, d in ((1, 1, 2.6), (2.756, 0.35, 6), (5.404, 0.15, 12)))
    return fade_in(sig * 0.5)


def pad(chord, dur):
    t = env_t(dur)
    sig = np.zeros_like(t)
    for m in chord:
        for detune in (-0.08, 0, 0.08):
            f = hz(m - 12 + detune)
            sig += sum(np.sin(2 * np.pi * n * f * t + n) / n for n in range(1, 7))
    envelope = np.minimum(1, t / 0.25) * np.minimum(1, (dur - t) / 0.3)
    return sig * envelope / 18


def bass(midi, dur=0.24):
    t = env_t(dur)
    f = hz(midi)
    return fade_in((np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 7), 0.005)


def kick():
    t = env_t(0.4)
    phase = 2 * np.pi * np.cumsum(46 + 110 * np.exp(-t * 32)) / SR
    return np.sin(phase) * np.exp(-t * 8) + 0.2 * noise(0.4) * np.exp(-t * 300)


def clap():
    t = env_t(0.25)
    x = noise(0.25)
    burst = (smooth(x, 0.00012) - smooth(x, 0.0008)) * 2.5
    envelope = sum(np.exp(-np.maximum(t - o, 0) * 28) * (t >= o) for o in (0, 0.011, 0.023))
    return burst * envelope * 0.55


def hat(open_=False):
    t = env_t(0.14 if open_ else 0.04)
    x = highpass(noise(len(t) / SR))
    return (x - smooth(x, 0.00012)) * np.exp(-t * (22 if open_ else 80)) * 0.3


def crash():
    t = env_t(1.8)
    x = highpass(noise(1.8))
    return smooth(x, 0.00008) * np.exp(-t * 3) * 0.4


def riser(dur):
    t = env_t(dur)
    u = t / dur
    sweep = np.sin(2 * np.pi * np.cumsum(200 + 1200 * u ** 2) / SR)
    return (highpass(noise(dur)) * 0.5 + sweep * 0.15) * u ** 2.2


def reverb(x):
    out = x.copy()
    for delay, gain in ((0.031, 0.5), (0.047, 0.42), (0.067, 0.35), (0.089, 0.3), (0.113, 0.24), (0.151, 0.18), (0.197, 0.12)):
        n = int(delay * SR)
        out[n:] += x[:-n] * gain
    return out


# ---------------------------------------------------------------- music

def music(duration, breakdown=(), outro=None):
    """Intro until the first drop, then the full groove; breakdown bars drop kick and bass."""
    n = int(duration * SR)
    drums, tonal, pads = np.zeros((n, 2)), np.zeros((n, 2)), np.zeros((n, 2))
    drop = FIRST_DOWNBEAT + 3 * BAR
    outro = outro or duration
    place(tonal, 0.0, glock(hz(74)), 0.5, -0.3)
    bar = 0
    while FIRST_DOWNBEAT + bar * BAR < duration:
        b0 = FIRST_DOWNBEAT + bar * BAR
        chord, root = CHORDS[bar % 4], ROOTS[bar % 4]
        full = drop <= b0 < outro and not any(a <= b0 < z for a, z in breakdown)
        if b0 < outro:
            place(pads, b0, pad(chord, BAR + 0.1), 0.9 if full else 1.5)
            tones = [*chord, chord[0] + 12]
            for step, idx in enumerate((0, 2, 1, 3, 2, 1, 3, 2)):
                place(tonal, b0 + step * BEAT / 2, pluck(hz(tones[idx] + 12)), 0.55 if b0 >= drop else 0.8, -0.35 if step % 2 else 0.35)
            for step in range(8):
                if b0 >= FIRST_DOWNBEAT + BAR:
                    place(drums, b0 + step * BEAT / 2, hat(open_=step % 2 == 1), 0.3 if step % 2 else 0.18, 0.25)
        if full:
            for beat in range(4):
                place(drums, b0 + beat * BEAT, kick(), 0.95)
                place(tonal, b0 + beat * BEAT + BEAT / 2, bass(root + 12 * (beat % 2 == 1)), 0.7)
            for beat in (1, 3):
                place(drums, b0 + beat * BEAT, clap(), 0.8, -0.1)
        bar += 1
    for start in (drop, outro):
        if start < duration:
            place(drums, start, crash(), 0.9)
            place(drums, start, kick(), 1.0)
            place(tonal, start, bass(ROOTS[0], 1.2), 0.8)
            for beat, midi in HOOK:
                place(tonal, start + beat * BEAT, glock(hz(midi)), 0.45, -0.2)
    place(drums, drop - BAR, riser(BAR), 0.5)
    for _, z in breakdown:
        place(drums, z - BAR, riser(BAR), 0.45)
        place(drums, z, crash(), 0.6)
    if outro < duration:
        place(pads, outro, pad(CHORDS[0], duration - outro), 1.1)
        place(tonal, outro, pluck(hz(74), 2.5), 0.6)
    # Sidechain the pads to the kick grid for the modern pumping feel.
    t = np.arange(n) / SR
    beat_phase = np.mod(t - FIRST_DOWNBEAT, BEAT)
    pump = np.where((t >= drop) & (t < outro), 1 - 0.55 * np.exp(-beat_phase * 9), 1.0)
    pads *= pump[:, None]
    tonal[:, 0], tonal[:, 1] = reverb(tonal[:, 0]), reverb(tonal[:, 1])
    mix = drums + tonal + pads
    if outro < duration:
        tail = t >= duration - 1.6
        mix[tail] *= np.linspace(1, 0, tail.sum())[:, None]
    return mix / np.max(np.abs(mix))


# ---------------------------------------------------------------- sound effects

def pop_sfx(big, index):
    t = env_t(0.14)
    f0 = 520 * 2 ** ((index % 5) / 12)
    chirp = np.sin(2 * np.pi * np.cumsum(f0 + 900 * (1 - np.exp(-t * 40))) / SR) * np.exp(-t * 38)
    if big:
        tt = env_t(0.3)
        thump = np.sin(2 * np.pi * np.cumsum(80 + 120 * np.exp(-tt * 30)) / SR) * np.exp(-tt * 11)
        chirp = np.pad(chirp, (0, len(tt) - len(t))) + 0.8 * thump + 0.25 * highpass(noise(0.3)) * np.exp(-tt * 60)
    return fade_in(chirp, 0.002)


def whoosh(dur=0.55):
    u = env_t(dur) / dur
    x = noise(dur)
    band = smooth(x, 0.0004) - smooth(x, 0.004)
    return band * np.sin(np.pi * u ** 0.8) ** 2 * 2.2


def effects(duration, bursts, transitions):
    n = int(duration * SR)
    buf = np.zeros((n, 2))
    for i, (t, radius, x) in enumerate(sorted(bursts)):
        place(buf, t, pop_sfx(radius >= 180, i), 0.4 if radius >= 180 else 0.25, (x / 960 - 1) * 0.6)
    for t, horizontal in transitions:
        place(buf, t - 0.3, whoosh(), 0.35, 0.0 if not horizontal else -0.2)
    return buf


# ---------------------------------------------------------------- voiceover

def upsample2(x):
    spec = np.fft.rfft(x)
    return np.fft.irfft(np.concatenate([spec, np.zeros(len(x) - len(spec) + 1)]), 2 * len(x)) * 2


def trim(x, threshold=0.012):
    loud = np.flatnonzero(np.abs(x) > threshold)
    if not len(loud):
        return x
    a, b = max(0, loud[0] - int(0.03 * SR)), min(len(x), loud[-1] + int(0.09 * SR))
    return x[a:b]


def voiceover(cues, voice="af_heart", speed=1.05):
    """Synthesise each (start, text) cue; returns [(start, text, mono 48 kHz audio)]."""
    from kokoro_onnx import Kokoro

    kokoro = Kokoro(str(CACHE / "kokoro-v1.0.onnx"), str(CACHE / "voices-v1.0.bin"))
    clips = []
    for start, text in cues:
        audio, rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
        if rate != SR // 2:
            raise SystemExit(f"Unexpected Kokoro sample rate {rate}")
        audio = trim(upsample2(np.asarray(audio, dtype=np.float64)))
        clips.append((start, text, audio / np.max(np.abs(audio)) * 0.9))
    return clips


def mix(duration, clips, bursts, transitions, breakdown, outro):
    n = int(duration * SR)
    vo = np.zeros((n, 2))
    for start, _, audio in clips:
        place(vo, start, audio)
    level = smooth(np.abs(vo[:, 0]), 0.05)
    duck = 1 - 0.6 * smooth(np.clip(level / (level.max() + 1e-9) * 5, 0, 1), 0.18)
    out = vo + music(duration, breakdown, outro) * 0.34 * duck[:, None] + effects(duration, bursts, transitions)
    return out / np.max(np.abs(out)) * 0.95


def write_wav(path, audio):
    import soundfile as sf

    sf.write(str(path), audio.astype(np.float32), SR, subtype="PCM_24")

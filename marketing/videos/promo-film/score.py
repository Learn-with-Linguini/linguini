"""Compose the launch-film score from real piano recordings.

Every note is placed on the same beat grid the edit uses, so cuts land on notes
by construction. Samples: University of Iowa Electronic Music Studios, Musical
Instrument Samples (Steinway B piano), free to use without restriction.

Usage: python3 score.py <piano-wav-dir> <sfx-dir> <out.wav> <timeline.json> [notes.json]
The optional notes.json receives the list of samples used, for fetch.py.
"""
import json
import sys

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
PIANO, SFX, OUT, TIMELINE = sys.argv[1:5]
T = json.load(open(TIMELINE))
BEAT = T["beat"]
rng = np.random.default_rng(7)

FLAT = {"C#": "Db", "F#": "Gb", "G#": "Ab", "D#": "Eb", "A#": "Bb"}
ORDER = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_cache = {}
USED = set()


def load(note, dyn):
    key = (note, dyn)
    if key not in _cache:
        name, octave = note[:-1], note[-1]
        x, sr = sf.read(f"{PIANO}/Piano.{dyn}.{FLAT.get(name, name)}{octave}.wav", dtype="float32")
        USED.add(f"Piano.{dyn}.{FLAT.get(name, name)}{octave}")
        peak = np.abs(x).max()
        start = max(0, int(np.argmax(np.abs(x).max(axis=1) > peak * 0.04)) - 24)
        x = x[start:start + 9 * SR]
        fade = np.linspace(1, 0, SR)[:, None] ** 2
        x[-SR:] *= fade
        _cache[key] = x / peak
    return _cache[key]


def midi(note):
    return ORDER.index(note[:-1]) + 12 * (int(note[-1]) + 1)


def name(m):
    return f"{ORDER[m % 12]}{m // 12 - 1}"


music = np.zeros((int(34 * SR), 2), np.float32)
logo = np.zeros_like(music)


def play(bus, t, note, vel, length=6.0, jitter=0.004):
    dyn = "pp" if vel < 0.38 else "mf" if vel < 0.72 else "ff"
    ref = {"pp": 0.38, "mf": 0.72, "ff": 1.0}[dyn]
    layer = {"pp": 0.30, "mf": 0.55, "ff": 0.85}[dyn]
    x = load(note, dyn).copy() * layer * (0.55 + 0.45 * vel / ref)
    n = min(len(x), int(length * SR))
    rel = min(int(0.28 * SR), n)
    x = x[:n]
    x[n - rel:] *= np.linspace(1, 0, rel)[:, None]
    # gentle stereo placement: low notes centre-left, high notes centre-right
    pan = np.clip((midi(note) - 60) / 60, -0.35, 0.35)
    x[:, 0] *= 1 - max(pan, 0)
    x[:, 1] *= 1 + min(pan, 0)
    i = int((t + rng.uniform(-jitter, jitter)) * SR)
    i = max(i, 0)
    bus[i:i + n] += x[: len(bus) - i]


CH = {
    "D": ["D", "F#", "A"],
    "Bm": ["B", "D", "F#"],
    "G": ["G", "B", "D"],
    "Em": ["E", "G", "B", "D"],
    "A": ["A", "C#", "E"],
}


def tones(ch, lo, count):
    """Chord tones ascending from midi `lo`."""
    out, m = [], lo
    while len(out) < count:
        if ORDER[m % 12] in CH[ch]:
            out.append(name(m))
        m += 1
    return out


def arp(bus, t0, ch, step, count, lo, vel, pattern, length):
    tt = tones(ch, lo, max(pattern) + 1)
    for k in range(count):
        v = vel * (1.0 if k == 0 else 0.82 + 0.08 * rng.random())
        play(bus, t0 + k * step, tt[pattern[k % len(pattern)]], min(v, 1), length)


shots = T["shots"]
sec = {s["section"]: [] for s in shots}
for s in shots:
    sec[s["section"]].append(s)

# Intro: one high note wakes the viewfinder.
play(music, T["intro_note"], "A5", 0.26, 5)
play(music, T["intro_note"] + 0.6, "D6", 0.2, 5)

# Act 1: 3/4 bars, one shot per bar, piano alone and close.
act1 = ["D", "Bm", "G", "Em", "A"]
for i, s in enumerate(sec["act1"]):
    t0, ch = s["start"], act1[i]
    vel = 0.26 + 0.05 * i
    play(music, t0, f"{CH[ch][0]}2", vel + 0.06, 3.6)
    if i < 2:
        arp(music, t0, ch, BEAT, 3, 62, vel, [0, 2, 4], 3.2)
    else:
        arp(music, t0, ch, BEAT / 2, 6, 62, vel, [0, 2, 4, 5, 4, 2], 2.6)

# Act 2a: two beats a shot, sixteenths, a melody on the downbeats.
act2a, mel2a = ["D", "Bm", "G", "A"], ["A5", "B5", "B5", "C#6"]
for i, s in enumerate(sec["act2a"]):
    t0, ch = s["start"], act2a[i]
    vel = 0.5 + 0.05 * i
    for b in range(2):
        play(music, t0 + b * BEAT, f"{CH[ch][0]}2", vel, 1.4)
        play(music, t0 + b * BEAT, f"{CH[ch][0]}3", vel * 0.8, 1.4)
    arp(music, t0, ch, BEAT / 4, 8, 62, vel * 0.85, [0, 1, 2, 3, 4, 3, 2, 1], 0.9)
    play(music, t0, mel2a[i], vel + 0.15, 2.2)

# Act 2b: a shot per beat, eighth-note bass, rising line.
act2b, mel2b = ["Bm", "G", "D", "A", "Bm", "A"], ["D6", "B5", "D6", "E6", "F#6", "E6"]
for i, s in enumerate(sec["act2b"]):
    t0, ch = s["start"], act2b[i]
    vel = 0.66 + 0.03 * i
    for b in range(2):
        play(music, t0 + b * BEAT / 2, f"{CH[ch][0]}2", vel, 0.6)
    play(music, t0, f"{CH[ch][0]}1", vel * 0.7, 0.9)
    arp(music, t0, ch, BEAT / 4, 4, 66, vel * 0.85, [0, 1, 2, 3], 0.7)
    play(music, t0, mel2b[i], vel + 0.12, 1.2)

# Act 2c: two shots a beat, both hands driving, crescendo into the last shot.
act2c = ["G", "G", "A", "A", "Bm", "Bm", "A", "A"]
for i, s in enumerate(sec["act2c"]):
    t0, ch = s["start"], act2c[i]
    vel = 0.8 + 0.025 * i
    play(music, t0, f"{CH[ch][0]}1", vel, 0.5)
    play(music, t0, f"{CH[ch][0]}2", vel, 0.5)
    arp(music, t0, ch, BEAT / 4, 2, 74, vel * 0.9, [0, 2], 0.5)
    arp(music, t0, ch, BEAT / 4, 2, 62, vel * 0.8, [0, 1], 0.5)

# Final shot: the big chord, then keep pushing until the hard cut.
fin = sec["final"][0]
for n in ["D1", "D2", "A2", "D3", "F#3", "A3", "D4", "F#4", "A4", "D5"]:
    play(music, fin["start"], n, 0.95, 3)
t = fin["start"]
k = 0
while t < T["cut"] - 1e-6:
    if k % 4 == 0 and k:
        play(music, t, "D2", 0.9, 0.6)
        play(music, t, "D1", 0.8, 0.6)
    tt = tones("D", 74, 6)
    play(music, t, tt[[0, 1, 2, 3, 4, 5, 4, 3][k % 8]], 0.92, 0.5)
    t += BEAT / 4
    k += 1

# Logo: an open, quiet chord after the silence, then two single notes.
for j, (n, v) in enumerate([("D2", 0.42), ("A2", 0.36), ("E4", 0.3), ("F#4", 0.3), ("A4", 0.3), ("D5", 0.32)]):
    play(logo, T["logo_chord"] + j * 0.035, n, v, 9, 0)
play(logo, T["tagline"], "F#5", 0.24, 6, 0)
play(logo, T["ph_line"], "A5", 0.2, 5, 0)


def reverb(x, seconds, wet, seed):
    r = np.random.default_rng(seed)
    n = int(seconds * SR)
    env = np.exp(-np.arange(n) / (SR * seconds / 6.5))
    ir = r.standard_normal((n, 2)) * env[:, None]
    ir = sosfilt(butter(2, 5200, "low", fs=SR, output="sos"), ir, axis=0)
    ir[: int(0.012 * SR)] = 0
    ir /= np.sqrt((ir ** 2).sum(axis=0))
    y = np.stack([fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], axis=1)
    return x * (1 - wet) + y * wet * 2.2


music = reverb(music, 2.4, 0.24, 1)
logo = reverb(logo, 3.6, 0.32, 2)


def sfx(bus, t, f, gain):
    x, _ = sf.read(f"{SFX}/{f}", dtype="float32")
    i = int(t * SR)
    bus[i:i + len(x)] += x[: len(bus) - i] * gain


riser, _ = sf.read(f"{SFX}/sfx-riser2.wav", dtype="float32")
sfx(music, T["cut"] - len(riser) / SR, "sfx-riser2.wav", 0.32)

# The hard cut: everything stops, like the lights going out.
cut = int(T["cut"] * SR)
g = np.ones(len(music), np.float32)
g[cut:cut + int(0.045 * SR)] = np.linspace(1, 0, int(0.045 * SR))
g[cut + int(0.045 * SR):] = 0
music *= g[:, None]

mix = music + logo
end = int(T["end"] * SR)
mix = mix[:end]
fo = int(T["fade_out"] * SR)
mix[fo:] *= np.linspace(1, 0, end - fo)[:, None] ** 1.5
mix /= np.abs(mix).max() / 0.89
sf.write(OUT, mix, SR, subtype="FLOAT")
print("wrote", OUT, round(len(mix) / SR, 2), "s,", len(USED), "piano samples")
if len(sys.argv) > 5:
    json.dump(sorted(USED), open(sys.argv[5], "w"), indent=0)

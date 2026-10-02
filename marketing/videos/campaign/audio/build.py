"""Compose original cinematic audio for Linguini's campaign cuts.

No dependencies or third-party recordings. Run from any directory:
    python3 marketing/videos/campaign/audio/build.py

Exports stereo 32 kHz 16-bit PCM WAVs. At this rate the six deliverables total
about 16 MiB while retaining the low/mid frequency detail of this score.
"""

from __future__ import annotations

from array import array
import json
import math
from pathlib import Path
import random
import wave

OUT = Path(__file__).resolve().parent
RATE = 32000
TAU = math.tau
RANDOM = random.Random(3216)


def freq(midi_note):
    return 440 * 2 ** ((midi_note - 69) / 12)


class Bus:
    def __init__(self, duration):
        self.duration = duration
        self.n = round(duration * RATE)
        self.left = array("f", [0]) * self.n
        self.right = array("f", [0]) * self.n

    def add(self, at, samples, amp=1.0, pan=0.0):
        index = round(at * RATE)
        lgain = amp * math.sqrt((1 - pan) / 2)
        rgain = amp * math.sqrt((1 + pan) / 2)
        for j, v in enumerate(samples):
            i = index + j
            if 0 <= i < self.n:
                self.left[i] += v * lgain
                self.right[i] += v * rgain

    def peak(self):
        return max(max(abs(v) for v in self.left), max(abs(v) for v in self.right))


def bow(bus, at, note, length, amp=.028, pan=0.0, attack=.22):
    """Warm bowed synth: low harmonic density, gentle detuning and slow attack."""
    f = freq(note)
    samples = array("f")
    for i in range(round(length * RATE)):
        t = i / RATE
        env = (1 - math.exp(-t / attack)) * min(1, (length - t) / .43)
        trem = 1 + .065 * math.sin(TAU * 3.4 * t)
        p = TAU * f * t
        body = (math.sin(p) + .23 * math.sin(2.003 * p) +
                .08 * math.sin(3.008 * p) + .16 * math.sin(.997 * p + .4))
        samples.append(body * env * trem)
    bus.add(at, samples, amp, pan)


def pluck(bus, at, note, amp=.058, length=.75, pan=0.0, echo=.10):
    """Soft felt/plucked string; no square-wave edge."""
    f = freq(note)
    samples = array("f")
    for i in range(round(length * RATE)):
        t = i / RATE
        env = (1 - math.exp(-t * 210)) * math.exp(-t * 4.2)
        p = TAU * f * t
        body = (math.sin(p) + .31 * math.sin(2 * p) * math.exp(-t * 6)
                + .095 * math.sin(3 * p) * math.exp(-t * 12))
        samples.append(body * env)
    bus.add(at, samples, amp, pan)
    if echo:
        bus.add(at + .22, samples, amp * echo, -pan)


def sub(bus, at, note, amp=.20, length=.66):
    f = freq(note)
    samples = array("f")
    phase = 0.0
    for i in range(round(length * RATE)):
        t = i / RATE
        phase += TAU * f * (1 + .025 * math.exp(-t * 22)) / RATE
        env = (1 - math.exp(-t * 140)) * math.exp(-t * 3.4) * min(1, (length - t) / .05)
        samples.append((math.sin(phase) + .14 * math.sin(2 * phase)) * env)
    bus.add(at, samples, amp)


def low_tom(bus, at, amp=.14):
    samples = array("f")
    phase = 0.0
    for i in range(round(.29 * RATE)):
        t = i / RATE
        phase += TAU * (85 + 60 * math.exp(-t * 25)) / RATE
        samples.append(math.sin(phase) * math.exp(-t * 13))
    bus.add(at, samples, amp, -.08)


def breath(bus, at, length, amp=.055, rising=False, pan=0.0):
    """Filtered noise breath for risers, impact tails and cinematic air."""
    samples = array("f")
    smooth = 0.0
    n = max(1, round(length * RATE))
    for i in range(n):
        q = i / n
        raw = RANDOM.random() * 2 - 1
        cutoff = (.012 + q * .11) if rising else (.08 - q * .065)
        smooth += cutoff * (raw - smooth)
        env = (q ** 1.7 if rising else math.exp(-q * 4.0)) * min(1, (1 - q) / .035)
        samples.append(smooth * env)
    bus.add(at, samples, amp, pan)


def impact(bus, at, amp=.23, long=False):
    sub(bus, at, 33 if long else 36, amp * 1.3, .98 if long else .54)
    low_tom(bus, at + .018, amp * .45)
    breath(bus, at, .8 if long else .42, amp * .7, pan=.15)


def choir_chord(bus, at, chord, length, amp=.018, wide=False):
    for i, note in enumerate(chord):
        bow(bus, at, note, length, amp * (1.0 if i < 3 else .75),
            pan=(-.49 + i * .30) if wide else (-.30 + i * .20), attack=.33)


CHORDS = [
    ([50, 53, 57, 64], 38),  # D minor add 9
    ([46, 50, 53, 57], 34),  # B-flat major 7
    ([53, 57, 60, 67], 41),  # F add 9
    ([48, 52, 55, 62], 36),  # C add 9
]


def score(duration, marks):
    music = Bus(duration)
    sfx = Bus(duration)
    tense, build, lift, cta = (marks[k] for k in ("tense_end", "build_end", "lift_end", "cta"))

    # 0–6s in the hero edit: air, low strings and sparse felt notes.
    drone_end = max(.5, tense)
    choir_chord(music, 0, CHORDS[0][0], drone_end + .55, .014, wide=True)
    bow(music, 0, 38, drone_end + .5, .038, pan=-.12, attack=.9)
    for t in range(1, math.ceil(tense), 2):
        if t < tense:
            pluck(music, t, (62, 65, 69)[(t // 2) % 3], .032, pan=.19)
    breath(sfx, 0, min(1.7, max(.4, tense)), .022, pan=-.2)
    if tense >= 2:
        low_tom(music, 2, .060)
        if tense > 4:
            low_tom(music, 4, .073)

    # Build: clockwork low pulses under evolving minor-to-major strings.
    t = tense
    chord_i = 0
    while t < build - 1e-9:
        chord, root = CHORDS[chord_i % 4]
        span = min(2.0, build - t)
        choir_chord(music, t, chord, span + .5, .024 + .004 * min(chord_i, 3), wide=True)
        for p in range(math.ceil(span * 2)):
            pt = t + p * .5
            if pt >= build:
                break
            pluck(music, pt, (root + 12, root + 19, root + 15, root + 19)[p % 4],
                  .042 + min(.012, chord_i * .0025), length=.43, pan=(-.16 if p % 2 else .16))
            if p % 2 == 0:
                sub(music, pt, root, .118 + min(.03, chord_i * .006), .40)
            elif chord_i >= 2:
                low_tom(music, pt, .052)
        t += span
        chord_i += 1
    if build > tense:
        impact(sfx, tense, .095)
        if build - tense >= 5:
            breath(sfx, build - .7, .68, .095, rising=True, pan=.15)

    # Lift: harmonic opening and longer, wider bow strokes.
    t = build
    chord_i = 0
    while t < lift - 1e-9:
        chord, root = CHORDS[(2 + chord_i) % 4]
        span = min(2.0, lift - t)
        choir_chord(music, t, chord, span + .7, .038, wide=True)
        bow(music, t, chord[0] - 12, span + .65, .040, pan=.05, attack=.18)
        for off in (0, .5, 1.0, 1.5):
            if t + off >= lift:
                break
            pluck(music, t + off, (root + 24, root + 19, root + 27, root + 19)[int(off * 2)],
                  .047, length=.62, pan=(-.25 if off % 1 else .24))
            if off in (0, 1.0):
                sub(music, t + off, root, .14, .49)
        t += span
        chord_i += 1
    if lift > build:
        impact(sfx, build, .12)

    # Music-only drop in the final second before CTA. A riser lives on SFX stem.
    breath(sfx, lift, cta - lift, .18, rising=True, pan=-.1)

    # CTA: strong low F impact, major strings and three-note resolve.
    impact(sfx, cta, .31, long=True)
    choir_chord(music, cta, [41, 48, 53, 57, 60], duration - cta + .15, .051, wide=True)
    bow(music, cta, 29, duration - cta + .15, .069, pan=.02, attack=.12)
    for off, note, amp in ((.0, 65, .070), (.5, 69, .072), (1.0, 72, .078),
                           (1.75, 77, .063), (2.5, 72, .051)):
        if cta + off < duration - .1:
            pluck(music, cta + off, note, amp, length=.92, pan=(-.22 if int(off * 2) % 2 else .22))
    sub(music, cta, 41, .20, .9)
    if duration - cta >= 3.5:
        sub(music, cta + 2.0, 41, .13, .62)
        low_tom(music, cta + 2.5, .075)
    breath(sfx, cta + .03, 1.2, .11, pan=.27)

    # Silence the old tail during the 1s drop; the incoming CTA begins untouched.
    for i in range(round(lift * RATE), round(cta * RATE)):
        q = (i / RATE - lift) / max(.001, cta - lift)
        gain = .20 * (1 - q) + .012
        music.left[i] *= gain
        music.right[i] *= gain
    return music, sfx


def scale(bus, target_peak, end_fade=.16):
    gain = target_peak / max(bus.peak(), 1e-9)
    for i in range(bus.n):
        tail = min(1.0, (bus.n - i) / (end_fade * RATE))
        bus.left[i] *= gain * tail
        bus.right[i] *= gain * tail
    return bus


def combine(music, sfx):
    mixed = Bus(music.duration)
    for i in range(music.n):
        mixed.left[i] = music.left[i] + sfx.left[i]
        mixed.right[i] = music.right[i] + sfx.right[i]
    if mixed.peak() > .83:
        scale(mixed, .83, end_fade=0)
    return mixed


def save(path, bus):
    pcm = array("h")
    for l, r in zip(bus.left, bus.right):
        pcm.extend((round(max(-1, min(1, l)) * 32767), round(max(-1, min(1, r)) * 32767)))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm.tobytes())


VERSIONS = {
    30: {"tense_end": 6.0, "build_end": 18.0, "lift_end": 25.0, "cta": 26.0},
    20: {"tense_end": 3.0, "build_end": 11.0, "lift_end": 15.0, "cta": 16.0},
    15: {"tense_end": 2.0, "build_end": 7.0, "lift_end": 10.0, "cta": 11.0},
    6: {"tense_end": .5, "build_end": .5, "lift_end": 1.0, "cta": 2.0},
}


if __name__ == "__main__":
    for length, marks in VERSIONS.items():
        music, sfx = score(length, marks)
        scale(music, .46)
        scale(sfx, .46)
        mixed = combine(music, sfx)
        if length == 30:
            save(OUT / "music.wav", music)
            save(OUT / "sfx.wav", sfx)
            save(OUT / "mix.wav", mixed)
        else:
            save(OUT / f"mix-{length}.wav", mixed)
        print(length, "s", marks, "peak", round(mixed.peak(), 3))
    (OUT / "cues.json").write_text(json.dumps({
        "tempo_bpm": 120,
        "beat_grid_seconds": .5,
        "sample_rate_hz": RATE,
        "versions": VERSIONS,
        "notes": "Each cutdown is composed separately; CTA occupies its final four seconds after a one-second music drop.",
        "rights": "Original procedural score and SFX. No third-party samples or recordings.",
    }, indent=2) + "\n")

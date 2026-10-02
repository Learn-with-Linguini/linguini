"""Original, dependency-free score and sound design for the 30s Linguini ad.

Run: python3 marketing/videos/launch-film/audio/build_audio.py
Output: 44.1 kHz stereo PCM music.wav, sfx.wav and no-voice preview_mix.wav.
The music is original procedural synthesis; no samples or third-party recordings.
"""

from __future__ import annotations

from array import array
import json
import math
from pathlib import Path
import random
import wave

OUT = Path(__file__).resolve().parent
SR = 44100
DURATION = 30.0
N = int(SR * DURATION)
TAU = math.tau
RNG = random.Random(3216)


class Stereo:
    def __init__(self):
        self.l = array("f", [0.0]) * N
        self.r = array("f", [0.0]) * N

    def put(self, start: int, values, pan=0.0, gain=1.0):
        left = math.sqrt((1 - pan) / 2) * gain
        right = math.sqrt((1 + pan) / 2) * gain
        for j, value in enumerate(values):
            i = start + j
            if 0 <= i < N:
                self.l[i] += value * left
                self.r[i] += value * right

    def peak(self):
        return max(max(abs(v) for v in self.l), max(abs(v) for v in self.r))


def midi(n):
    return 440.0 * (2.0 ** ((n - 69) / 12.0))


def start(t):
    return round(t * SR)


def key(bus, t, note, amp=0.10, dur=0.72, pan=0.0):
    """Warm tine/electric-piano pluck, rounded enough to sit under speech."""
    f = midi(note)
    count = int(dur * SR)
    values = array("f")
    for i in range(count):
        x = i / SR
        attack = min(1.0, x / .012)
        env = attack * math.exp(-x * 2.5) * min(1.0, (dur - x) / .055)
        p = TAU * f * x
        value = (math.sin(p) + .22 * math.sin(2.003 * p) * math.exp(-2.0 * x)
                 + .075 * math.sin(3.01 * p) * math.exp(-5 * x)) * env * amp
        values.append(value)
    bus.put(start(t), values, pan)
    bus.put(start(t + .145), values, -pan * .45 + .22, .085)
    bus.put(start(t + .31), values, pan * .3 - .18, .042)


def pad(bus, t, note, amp=.023, dur=2.1, pan=0.0):
    f = midi(note)
    count = int(dur * SR)
    values = array("f")
    for i in range(count):
        x = i / SR
        env = (1 - math.exp(-x * 5)) * min(1.0, (dur - x) / .24)
        wobble = 1 + .045 * math.sin(TAU * .33 * x)
        p = TAU * f * x
        values.append((math.sin(p) + .17 * math.sin(2.001 * p)) * env * amp * wobble)
    bus.put(start(t), values, pan)


def bass(bus, t, note, amp=.16, dur=.43):
    f = midi(note)
    count = int(dur * SR)
    values = array("f")
    phase = 0.0
    for i in range(count):
        x = i / SR
        phase += TAU * f * (1 + .02 * math.exp(-35 * x)) / SR
        env = (1 - math.exp(-x * 180)) * math.exp(-x * 3.9) * min(1.0, (dur - x) / .025)
        values.append((math.sin(phase) + .20 * math.sin(2 * phase) * math.exp(-4 * x)) * env * amp)
    bus.put(start(t), values)


def mallet(bus, t, note, amp=.075, dur=.66, pan=.10):
    f = midi(note)
    count = int(dur * SR)
    values = array("f")
    for i in range(count):
        x = i / SR
        env = (1 - math.exp(-x * 280)) * math.exp(-x * 4.1)
        p = TAU * f * x
        values.append((math.sin(p) + .36 * math.sin(2.0 * p) * math.exp(-x * 10)
                       + .10 * math.sin(3.0 * p) * math.exp(-x * 18)) * env * amp)
    bus.put(start(t), values, pan)
    bus.put(start(t + .19), values, -pan, .12)


def kick(bus, t, amp=.21):
    count = int(.29 * SR)
    values = array("f")
    phase = 0.0
    for i in range(count):
        x = i / SR
        f = 52 + 82 * math.exp(-x * 29)
        phase += TAU * f / SR
        env = math.exp(-x * 19)
        click = (RNG.random() * 2 - 1) * math.exp(-x * 310) * .11
        values.append((math.sin(phase) * env + click) * amp)
    bus.put(start(t), values)


def snare(bus, t, amp=.125, rim=False):
    count = int((.12 if rim else .23) * SR)
    values = array("f")
    low = 0.0
    for i in range(count):
        x = i / SR
        noise = RNG.random() * 2 - 1
        low += .14 * (noise - low)
        crisp = noise - low
        env = math.exp(-x * (31 if rim else 17))
        tone = .22 * math.sin(TAU * 177 * x) * math.exp(-x * 24) if not rim else 0
        values.append((crisp * .52 + tone) * env * amp)
    bus.put(start(t), values, pan=.06)


def hat(bus, t, amp=.035, open_hat=False, pan=.22):
    count = int((.19 if open_hat else .076) * SR)
    values = array("f")
    low = 0.0
    for i in range(count):
        x = i / SR
        noise = RNG.random() * 2 - 1
        low += .09 * (noise - low)
        env = math.exp(-x * (21 if open_hat else 61))
        values.append((noise - low) * env * amp)
    bus.put(start(t), values, pan)


def clap(bus, t, amp=.065):
    count = int(.18 * SR)
    values = array("f")
    low = 0.0
    for i in range(count):
        x = i / SR
        noise = RNG.random() * 2 - 1
        low += .08 * (noise - low)
        pulse = sum(math.exp(-max(0, x - o) * 36) if x >= o else 0 for o in (0, .014, .031))
        values.append((noise - low) * pulse * amp * .37)
    bus.put(start(t), values, pan=-.13)


def noise_sweep(bus, t, dur=.28, amp=.05, pan=0.0, up=True):
    count = int(dur * SR)
    values = array("f")
    low = 0.0
    for i in range(count):
        x = i / max(1, count - 1)
        noise = RNG.random() * 2 - 1
        coefficient = .02 + (.18 * x if up else .18 * (1 - x))
        low += coefficient * (noise - low)
        env = math.sin(math.pi * x) ** 1.6
        values.append(low * env * amp)
    bus.put(start(t), values, pan)


def click(bus, t, amp=.16):
    count = int(.065 * SR)
    values = array("f")
    low = 0.0
    for i in range(count):
        x = i / SR
        noise = RNG.random() * 2 - 1
        low += .16 * (noise - low)
        envelope = math.exp(-x * 104)
        body = math.sin(TAU * 920 * x) * math.exp(-x * 150) * .19
        values.append(((noise - low) * .58 * envelope + body) * amp)
    bus.put(start(t), values, pan=.03)


def music_score():
    bus = Stereo()
    # 15 two-second bars at 120 BPM. The last chord resolves to D.
    roots = [38, 35, 31, 33, 38, 35, 31, 33, 38, 35, 31, 33, 35, 31, 38]
    chords = [
        [50, 54, 57, 61], [47, 50, 54, 57], [43, 47, 50, 57], [45, 49, 52, 57],
        [50, 54, 57, 61], [47, 50, 54, 57], [43, 47, 50, 57], [45, 49, 52, 57],
        [50, 54, 57, 61], [47, 50, 54, 57], [43, 47, 50, 57], [45, 49, 52, 57],
        [47, 50, 54, 57], [43, 47, 50, 57], [50, 54, 57, 61],
    ]
    top_notes = [74, 73, 71, 69, 76, 73, 71, 69, 74, 73, 71, 69, 73, 71, 74]
    for bar in range(15):
        t = bar * 2.0
        root, chord = roots[bar], chords[bar]
        for j, note in enumerate(chord):
            pad(bus, t, note, amp=.0105 if bar < 2 else .015, pan=(-.3 if j % 2 else .3))
        # Syncopated keys; lower two notes only on the first stroke under narration.
        for offset, velocity in ((0.0, .69), (.75, .56), (1.5, .67)):
            if bar == 0 and offset == 0:
                velocity *= .6
            for j, note in enumerate(chord):
                key(bus, t + offset, note + 12, amp=.027 * velocity, dur=.63,
                    pan=-.34 + j * .22)
        if bar < 14:
            for offset, note, vel in ((0, root, 1.0), (.75, root + 7, .70), (1.25, root, .76), (1.75, root + 7, .55)):
                bass(bus, t + offset, note, .095 * vel, dur=.38)
        else:
            bass(bus, t, root, .105, dur=1.25)
        if bar >= 2 and bar not in (9, 14):
            mallet(bus, t + .25, top_notes[bar], .041, pan=-.18)
            mallet(bus, t + 1.25, top_notes[bar] - 2, .029, pan=.26)
        if bar == 14:
            for off, note in ((0, 74), (.5, 78), (1.0, 81), (1.5, 86)):
                mallet(bus, t + off, note, .043, dur=.9, pan=.06)

    # Organic pocket: two-step kick, backbeat, lightly swung sixteenth hats.
    for beat in range(60):
        t = beat * .5
        if t >= 28:
            continue
        if beat % 4 in (0, 2):
            kick(bus, t, .16 if t < 2 else .205)
        if beat % 4 in (1, 3) and t >= 2:
            snare(bus, t, .09 if t < 8 else .12, rim=t < 8)
            if t >= 8 and (beat // 4) % 2 == 0:
                clap(bus, t, .041)
        if t >= 1:
            hat(bus, t, .026 if beat % 2 == 0 else .020, pan=.2 if beat % 2 else -.18)
            if beat % 2 == 1 and t + .26 < 28:
                hat(bus, t + .26, .013, pan=-.25)
        if beat % 8 == 7 and t < 27:
            hat(bus, t + .24, .023, open_hat=True, pan=.3)

    # A few intentional lift points; each editorial cut remains on the .5s beat grid.
    for t in (8, 16, 23, 27):
        if t < 27:
            noise_sweep(bus, t - .44, .42, .040, up=True, pan=-.18)
        kick(bus, t, .115)
    # Outro tail preserves space for sonic logo at 27–30.
    return bus


def sfx_score():
    bus = Stereo()
    # 0s: layered camera shutter, mechanical and soft rather than stock SFX.
    click(bus, 0.025, .45)
    click(bus, .086, .32)
    noise_sweep(bus, .015, .13, .17, pan=-.14, up=False)
    # Soft scene shifts at the editor's cuts.
    for t, note in ((2, 74), (8, 73), (12, 71), (19, 69)):
        noise_sweep(bus, t - .20, .26, .25, pan=(-.25 if t % 2 else .25))
        click(bus, t + .005, .21)
        mallet(bus, t, note, .072, dur=.38, pan=.18 if t % 2 else -.18)
    # 5–8s: photo-word labels pop in, each tuned to the D-major palette.
    for t, note, pan in ((5.0, 74, -.34), (5.5, 78, .12), (6.0, 81, .35), (6.5, 78, -.10), (7.0, 74, .2)):
        mallet(bus, t, note, .095, dur=.42, pan=pan)
        click(bus, t, .045)
    # 14.85s: I-Spy's actual correct-answer click; the 16s music cut remains.
    click(bus, 14.85, .10)
    mallet(bus, 14.85, 81, .14, dur=.9, pan=-.12)
    mallet(bus, 14.975, 86, .11, dur=1.0, pan=.15)
    # 19.2–21s: seven restrained taps as sentence tokens settle into place.
    for i, t in enumerate((19.2, 19.5, 19.8, 20.1, 20.4, 20.7, 21.0)):
        click(bus, t, .085)
        mallet(bus, t, (74, 78, 81, 78, 74, 71, 74)[i], .022,
               dur=.24, pan=-.21 if i % 2 else .21)
    # 23s: light paper-rustle page turn with low-end thump.
    noise_sweep(bus, 22.74, .42, .32, pan=-.27, up=True)
    noise_sweep(bus, 23.0, .31, .22, pan=.34, up=False)
    click(bus, 23.12, .11)
    # 27–30s: four-note Linguini mnemonic and a soft resolve.
    for t, note, amp, pan in ((27.0, 74, .105, -.28), (27.5, 78, .095, .23),
                               (28.0, 81, .095, -.10), (28.5, 86, .13, .08)):
        mallet(bus, t, note, amp, dur=1.10, pan=pan)
    noise_sweep(bus, 27.0, .32, .05, up=False)
    return bus


def finalize(bus, peak_target, fade_in=.0, fade_out=.20):
    peak = bus.peak()
    scale = peak_target / peak if peak else 1.0
    for i in range(N):
        t = i / SR
        fade = min(1.0, t / fade_in) if fade_in else 1.0
        fade *= min(1.0, (DURATION - t) / fade_out) if fade_out else 1.0
        bus.l[i] *= scale * fade
        bus.r[i] *= scale * fade
    return bus


def write_wav(path, bus):
    pcm = array("h")
    for l, r in zip(bus.l, bus.r):
        pcm.append(int(max(-1, min(1, l)) * 32767))
        pcm.append(int(max(-1, min(1, r)) * 32767))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes(pcm.tobytes())


def statistics(bus):
    power = sum(l * l + r * r for l, r in zip(bus.l, bus.r)) / (2 * N)
    return {"peak_dBFS": round(20 * math.log10(max(1e-9, bus.peak())), 1),
            "rms_dBFS": round(10 * math.log10(max(1e-9, power)), 1)}


if __name__ == "__main__":
    music = finalize(music_score(), .34, fade_out=.75)
    sfx = finalize(sfx_score(), .32, fade_out=.48)
    preview = Stereo()
    for i in range(N):
        preview.l[i] = music.l[i] + sfx.l[i]
        preview.r[i] = music.r[i] + sfx.r[i]
    # Preview gets a safety ceiling; source stems remain independent.
    if preview.peak() > .78:
        preview = finalize(preview, .78, fade_out=0)
    write_wav(OUT / "music.wav", music)
    write_wav(OUT / "sfx.wav", sfx)
    write_wav(OUT / "preview_mix.wav", preview)
    cues = {
        "tempo_bpm": 120,
        "duration_seconds": 30,
        "sample_rate_hz": SR,
        "editorial_cuts_seconds": [0, 2, 5, 8, 12, 16, 19, 23, 27, 30],
        "effects": [
            {"time": 0, "effect": "camera shutter"},
            {"time": 2, "effect": "soft scene move"},
            {"time": 5, "effect": "word-pop sequence, five pops at half-second intervals"},
            {"time": 8, "effect": "soft scene move"},
            {"time": 12, "effect": "soft scene move"},
            {"time": 14.85, "effect": "I-Spy correct click and paired ding"},
            {"time": 16, "effect": "music cut accent"},
            {"time": 19, "effect": "soft scene move"},
            {"time": 19.2, "effect": "seven restrained sentence-token taps through 21.0s, every 0.3s"},
            {"time": 23, "effect": "journal page turn"},
            {"time": 27, "effect": "four-note brand mnemonic to 29.5s"},
        ],
        "levels": {"music": statistics(music), "sfx": statistics(sfx), "preview": statistics(preview)},
    }
    (OUT / "cues.json").write_text(json.dumps(cues, indent=2) + "\n")
    print(json.dumps(cues["levels"], indent=2))

"""Assemble the locked 30 s narration from local Kokoro TTS clips.

Run with ../.venv/bin/python build.py from this directory after generating
raw-01..09.wav and part-{es,in-es,fr,in-fr}.wav using script.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf


HERE = Path(__file__).resolve().parent
SCRIPT = json.loads((HERE.parent / "script.json").read_text())
SAMPLE_RATE = 24_000
DURATION = 30
SILENCE_THRESHOLD = 0.006


def read(name: str) -> np.ndarray:
    audio, rate = sf.read(HERE / name, dtype="float32")
    if rate != SAMPLE_RATE or audio.ndim != 1:
        raise ValueError(f"Unexpected audio format: {name}: {rate} Hz, shape {audio.shape}")
    return audio


def active_bounds(audio: np.ndarray) -> tuple[int, int]:
    """Find the first/last audible 10 ms block, retaining short edge fades."""
    block = SAMPLE_RATE // 100
    blocks = np.sqrt(np.mean(audio[: len(audio) // block * block].reshape(-1, block) ** 2, axis=1))
    active = np.flatnonzero(blocks > SILENCE_THRESHOLD)
    if not len(active):
        return 0, 0
    return max(0, int(active[0] * block) - block), min(len(audio), int((active[-1] + 1) * block) + 5 * block)


def trim_part(name: str) -> np.ndarray:
    audio = read(name)
    start, end = active_bounds(audio)
    return audio[start:end]


def silence(seconds: float) -> np.ndarray:
    return np.zeros(round(seconds * SAMPLE_RATE), dtype=np.float32)


def srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    h, milliseconds = divmod(milliseconds, 3_600_000)
    m, milliseconds = divmod(milliseconds, 60_000)
    s, milliseconds = divmod(milliseconds, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milliseconds:03d}"


track = silence(DURATION)
timings: list[dict] = []
captions: list[tuple[float, float, str]] = []

for index, shot in enumerate(SCRIPT["shots"], 1):
    start = float(shot["start_seconds"])
    end = float(shot["end_seconds"])
    pad = 0.09
    parts: list[dict] = []

    if index == 2:
        # Keep one voice identity, but phonemize the Spanish and French nouns
        # in their languages. The connective words remain English.
        fragments = [
            ("part-es.wav", "El coche", "es"),
            ("part-in-es.wav", "in Spanish.", "en-us"),
            ("part-fr.wav", "La voiture", "fr-fr"),
            ("part-in-fr.wav", "in French.", "en-us"),
        ]
        clips: list[np.ndarray] = []
        cursor = start + pad
        for fragment_index, (filename, phrase, lang) in enumerate(fragments):
            clip = trim_part(filename)
            clips.append(clip)
            parts.append({
                "text": phrase,
                "language": lang,
                "start_seconds": round(cursor, 3),
                "end_seconds": round(cursor + len(clip) / SAMPLE_RATE, 3),
            })
            cursor += len(clip) / SAMPLE_RATE
            if fragment_index != len(fragments) - 1:
                clips.append(silence(0.04))
                cursor += 0.04
        clip = np.concatenate(clips)
        captions.extend([
            (parts[0]["start_seconds"], parts[1]["end_seconds"], "El coche in Spanish."),
            (parts[2]["start_seconds"], parts[3]["end_seconds"], "La voiture in French."),
        ])
    else:
        clip = read(f"raw-{index:02d}.wav")

    clip_start = round((start + pad) * SAMPLE_RATE)
    clip_end = clip_start + len(clip)
    if clip_end > round((end - 0.08) * SAMPLE_RATE):
        raise ValueError(f"Shot {index} narration overruns the required tail padding")
    track[clip_start:clip_end] += clip

    onset, offset = active_bounds(clip)
    spoken_start = clip_start / SAMPLE_RATE + onset / SAMPLE_RATE
    spoken_end = clip_start / SAMPLE_RATE + offset / SAMPLE_RATE
    if index != 2:
        captions.append((spoken_start, spoken_end, shot["voiceover"]))
    timings.append({
        "shot": index,
        "cut_start_seconds": start,
        "cut_end_seconds": end,
        "clip_start_seconds": round(clip_start / SAMPLE_RATE, 3),
        "clip_end_seconds": round(clip_end / SAMPLE_RATE, 3),
        "audible_start_seconds": round(spoken_start, 3),
        "audible_end_seconds": round(spoken_end, 3),
        "text": shot["voiceover"],
        "fragments": parts,
    })

# A voice-only mono WAV, ready to sit beneath the music mix.
sf.write(HERE / "voice.wav", track, SAMPLE_RATE, subtype="PCM_16")

metadata = {
    "duration_seconds": DURATION,
    "sample_rate_hz": SAMPLE_RATE,
    "channels": 1,
    "source_voice": "Kokoro af_heart",
    "generation": "local kokoro-onnx 0.6.1; base speed 1.0, bilingual fragments 1.15",
    "shots": timings,
}
(HERE / "timings.json").write_text(json.dumps(metadata, indent=2) + "\n")

srt = "\n".join(
    f"{i}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n"
    for i, (start, end, text) in enumerate(captions, 1)
)
(HERE / "narration.srt").write_text(srt)

# RMS mouth animation sampled once per video frame. The 0–1 curve includes
# actual silence and is lightly smoothed to avoid jaw chatter.
fps = 30
rms = []
for frame in range(DURATION * fps):
    window = track[frame * (SAMPLE_RATE // fps):(frame + 1) * (SAMPLE_RATE // fps)]
    rms.append(float(np.sqrt(np.mean(window * window))))
rms = np.asarray(rms, dtype=np.float32)
levels = np.clip((rms - 0.008) / 0.095, 0, 1)
levels = np.convolve(levels, [0.2, 0.6, 0.2], mode="same")
envelope = {
    "fps": fps,
    "duration_seconds": DURATION,
    "source": "voice.wav voice-only 30 Hz RMS envelope",
    "samples": [
        {"time": round(frame / fps, 3), "value": round(float(level), 3)}
        for frame, level in enumerate(levels)
    ],
}
(HERE / "envelope.json").write_text(json.dumps(envelope, separators=(",", ":")) + "\n")

print(f"voice.wav: {len(track) / SAMPLE_RATE:.3f}s, {len(captions)} SRT captions, {len(levels)} mouth frames")
for item in timings:
    print(item["shot"], item["clip_start_seconds"], item["clip_end_seconds"])

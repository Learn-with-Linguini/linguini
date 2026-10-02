"""Regenerate the raw local Kokoro narration clips used by build.py.

From marketing/videos/launch-film/:

    python3.12 -m venv .venv
    .venv/bin/python -m pip install -r voice/requirements.txt
    .venv/bin/python voice/generate.py
    .venv/bin/python voice/build.py

Place the official kokoro-v1.0.onnx and voices-v1.0.bin files in
marketing/videos/launch-film/.venv/models/ first. This script does not download a model or use
an API key. It overwrites only the 13 raw/phrase clips in this directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro


HERE = Path(__file__).resolve().parent
VIDEO = HERE.parent
MODEL = VIDEO / ".venv/models/kokoro-v1.0.onnx"
VOICES = VIDEO / ".venv/models/voices-v1.0.bin"
SCRIPT = json.loads((VIDEO / "script.json").read_text())

if not MODEL.is_file() or not VOICES.is_file():
    raise SystemExit(f"Kokoro model/voice data missing from {MODEL.parent}")

kokoro = Kokoro(str(MODEL), str(VOICES))


def write(name: str, text: str, *, speed: float, language: str, sentence_pause: float, clause_pause: float) -> None:
    audio, sample_rate = kokoro.create(
        text,
        voice="af_heart",
        speed=speed,
        lang=language,
        sentence_pause=sentence_pause,
        clause_pause=clause_pause,
    )
    if sample_rate != 24_000:
        raise ValueError(f"Unexpected Kokoro sample rate: {sample_rate}")
    sf.write(HERE / name, audio, sample_rate)
    print(f"{name}: {len(audio) / sample_rate:.3f} s")


for index, shot in enumerate(SCRIPT["shots"], 1):
    write(
        f"raw-{index:02d}.wav",
        shot["voiceover"],
        speed=1.0,
        language="en-us",
        sentence_pause=0.12,
        clause_pause=0.05,
    )

# Shot 2 uses the same af_heart timbre throughout. The foreign nouns use
# native-language phonemization; build.py trims and combines these fragments.
for name, phrase, language in (
    ("part-es.wav", "El coche", "es"),
    ("part-in-es.wav", "in Spanish", "en-us"),
    ("part-fr.wav", "La voiture", "fr-fr"),
    ("part-in-fr.wav", "in French", "en-us"),
):
    write(name, phrase, speed=1.15, language=language, sentence_pause=0, clause_pause=0)

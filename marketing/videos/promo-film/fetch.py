"""Download the footage and piano samples the film is built from into cache/.

Neither is committed: Mixkit's licence does not allow redistributing the clips
on their own, and the piano samples are large.

- Footage: Mixkit, Stock Video Free License (https://mixkit.co/license/).
- Piano: University of Iowa Electronic Music Studios, Musical Instrument Samples
  (https://theremin.music.uiowa.edu/MISpiano.html), free to use.

Usage: python3 fetch.py
"""
import json
import os
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
UA = {"User-Agent": "curl/8.5.0"}


def get(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
    except Exception:
        return False
    with open(path, "wb") as f:
        f.write(data)
    return True


def clip(mid):
    path = os.path.join(CACHE, "clips", f"{mid}.mp4")
    for size in ("1080", "720"):
        if get(f"https://assets.mixkit.co/videos/{mid}/{mid}-{size}.mp4", path):
            return mid, size
    raise SystemExit(f"could not download Mixkit clip {mid}")


def note(name):
    aiff = os.path.join(CACHE, "piano", f"{name}.aiff")
    wav = os.path.join(CACHE, "piano", f"{name}.wav")
    if not os.path.exists(wav):
        url = f"https://theremin.music.uiowa.edu/sound%20files/MIS/Piano_Other/piano/{name}.aiff"
        if not get(url, aiff):
            return name, False
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", aiff, "-ar", "48000", "-ac", "2",
                        "-c:a", "pcm_f32le", wav], check=True)
        os.remove(aiff)
    return name, True


if __name__ == "__main__":
    os.makedirs(os.path.join(CACHE, "clips"), exist_ok=True)
    os.makedirs(os.path.join(CACHE, "piano"), exist_ok=True)
    timeline = json.load(open(os.path.join(HERE, "timeline.json")))
    ids = sorted({s["clip"] for s in timeline["shots"]})
    with ThreadPoolExecutor(6) as ex:
        for mid, size in ex.map(clip, ids):
            print(f"clip {mid} ({size}p)")
    notes = json.load(open(os.path.join(HERE, "audio", "piano-notes.json")))
    with ThreadPoolExecutor(8) as ex:
        missing = [n for n, ok in ex.map(note, notes) if not ok]
    if missing:
        raise SystemExit(f"missing piano samples: {missing}")
    print(f"{len(ids)} clips and {len(notes)} piano samples in {CACHE}")

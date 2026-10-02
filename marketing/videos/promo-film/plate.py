"""Cut, grade and track the footage plate.

Reads timeline.json and the Mixkit clips, writes the graded 1920x1080 plate as
raw frames to ffmpeg, and boxes.json with the tracked object box for every
output frame (in output pixels, after the slow push-in).

Usage: python3 plate.py <clips-dir> <timeline.json> <plate.mp4> <boxes.json> [fps]
"""
import json
import subprocess
import sys

import cv2
import numpy as np

CLIPS, TIMELINE, PLATE, BOXES = sys.argv[1:5]
FPS = int(sys.argv[5]) if len(sys.argv) > 5 else 30
W, H = 1920, 1080
T = json.load(open(TIMELINE))
N = int(round(T["end"] * FPS))

yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / np.sqrt(2)
VIGNETTE = (1 - 0.32 * r ** 2.4)[..., None]


def grade(img):
    x = img.astype(np.float32) / 255
    luma = (x @ np.array([0.114, 0.587, 0.299], np.float32))[..., None]
    x = luma + (x - luma) * 0.88                        # a little less saturation
    x = 0.5 + (x - 0.5) * 1.05                          # a little more contrast
    x = x * np.array([0.965, 1.0, 1.03], np.float32)    # warm (BGR)
    x = 0.028 + x * 0.955                               # lifted blacks, soft whites
    x = x * VIGNETTE
    return np.clip(x * 255, 0, 255).astype(np.uint8)


def push(p, section):
    return 1.0 + {"act1": 0.045, "act2a": 0.04, "act2b": 0.03, "act2c": 0.02, "final": 0.06}[section] * p


def smooth(boxes, k=7):
    a = np.array(boxes, np.float32)
    pad = np.pad(a, ((k // 2, k // 2), (0, 0)), mode="edge")
    ker = np.ones(k) / k
    return np.stack([np.convolve(pad[:, i], ker, "valid") for i in range(4)], 1)


enc = subprocess.Popen(
    ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
     "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "10", "-pix_fmt", "yuv420p", PLATE],
    stdin=subprocess.PIPE)
boxes = [None] * N
black = np.zeros((H, W, 3), np.uint8)
frame = 0

for s in T["shots"]:
    f0 = int(round(s["start"] * FPS))
    f1 = int(round((s["start"] + s["dur"]) * FPS))
    while frame < f0:
        enc.stdin.write(black.tobytes())
        frame += 1
    cap = cv2.VideoCapture(f"{CLIPS}/{s['clip']}.mp4")
    sfps = cap.get(cv2.CAP_PROP_FPS)
    sw, sh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    first = int(round(s["tin"] * sfps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    ok, src = cap.read()
    cur = first
    tracker, raw = None, []
    x0, y0, x1, y1 = s["box"]
    box = np.array([x0 * sw, y0 * sh, x1 * sw, y1 * sh], np.float32)
    small = 960 / sw
    if s["track"]:
        tracker = cv2.TrackerCSRT_create()
        bx = (box * small).astype(int)
        tracker.init(cv2.resize(src, None, fx=small, fy=small), (bx[0], bx[1], bx[2] - bx[0], bx[3] - bx[1]))
    frames = []
    for f in range(f0, f1):
        want = first + int((f - f0) / FPS * sfps + 1e-6)
        while cur < want:
            ok2, nxt = cap.read()
            if not ok2:
                break
            src, cur = nxt, cur + 1
            if tracker is not None:
                okt, (bx, by, bw, bh) = tracker.update(cv2.resize(src, None, fx=small, fy=small))
                if okt:
                    box = np.array([bx, by, bx + bw, by + bh], np.float32) / small
        if "box_end" in s:
            q = (f - f0) / max(1, f1 - f0 - 1)
            q = q * q * (3 - 2 * q)
            e0 = np.array(s["box_end"], np.float32) * [sw, sh, sw, sh]
            s0 = np.array(s["box"], np.float32) * [sw, sh, sw, sh]
            box = s0 + (e0 - s0) * q
        raw.append(box.copy())
        frames.append(src)
    sm = smooth(raw)
    for k, (f, src) in enumerate(zip(range(f0, f1), frames)):
        p = k / max(1, f1 - f0 - 1)
        z = push(p, s["section"])
        base = max(W / sw, H / sh)
        sc = base * z * s.get("zoom", 1)
        fx, fy = s.get("focus", (0.5, 0.5))
        # centre on the focus point, never showing past the frame edge
        tx = min(0, max(W - sc * sw, W / 2 - sc * fx * sw))
        ty = min(0, max(H - sc * sh, H / 2 - sc * fy * sh))
        M = np.array([[sc, 0, tx], [0, sc, ty]], np.float32)
        out = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        enc.stdin.write(grade(out).tobytes())
        b = sm[k]
        boxes[f] = [float(b[0] * sc + M[0, 2]), float(b[1] * sc + M[1, 2]),
                    float(b[2] * sc + M[0, 2]), float(b[3] * sc + M[1, 2])]
        frame += 1
    cap.release()
    print(f"{s['clip']:>6} {s['word']:<14} frames {f0}-{f1} src {sw}x{sh}@{sfps:.2f}", flush=True)

while frame < N:
    enc.stdin.write(black.tobytes())
    frame += 1
enc.stdin.close()
enc.wait()
json.dump(dict(fps=FPS, boxes=boxes), open(BOXES, "w"))
print("plate", PLATE, N, "frames")

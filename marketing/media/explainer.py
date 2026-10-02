"""Render the Linguini explainer video, captions and style frames.

One-time setup (Python 3.12, ffmpeg on PATH):
  python3.12 -m venv marketing/media/.venv
  marketing/media/.venv/bin/pip install pillow numpy soundfile kokoro-onnx
  mkdir -p marketing/media/.cache && cd marketing/media/.cache && for f in kokoro-v1.0.onnx voices-v1.0.bin; do
    curl -fLO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/$f; done

Run from the repository root:
  marketing/media/.venv/bin/python marketing/media/explainer.py               # video, captions and style frames
  marketing/media/.venv/bin/python marketing/media/explainer.py --frames      # style frames only (Pillow only)
  marketing/media/.venv/bin/python marketing/media/explainer.py --still 19.4  # one review frame

Timings follow marketing/media/explainer-script.md. Outputs go to marketing/media/export/.
"""

from __future__ import annotations

import argparse
import math
import subprocess
import tempfile
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "export"
PHOTO = ROOT / "landing/public/photos"
BRAND = ROOT / "landing/public/brand"
PASTA_DIR = ROOT / "landing/public/pasta"
FONTS = ROOT / "landing/assets/fonts"

W, H, FPS, TRANSITION = 1920, 1080, 24, 0.5
# While the video renders, burst() records (global time, radius, x) here for the sound effects.
RECORDING: dict = {"on": False, "t": 0.0, "rate": 1.0, "bursts": set()}
INK = "#263238"
DEEP = "#17403F"
GROUND = "#1F2A2F"
SKYLINE = "#2F3F46"
TOMATO = "#E85D32"
TOMATO_PRESSED = "#C94E2C"
PASTA = "#F9B233"
TEAL = "#2E9C99"
TEAL_DARK = "#21716F"
BUTTER = "#FFF9ED"
CREAM = "#FFF1D2"
SAGE = "#DCEBDD"
MUTED = "#667579"
MIST = "#A9B4B7"
SKIN = "#E9B48E"
HAIR = "#3B2A26"


def rgba(color: str, alpha: float = 1.0):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4)) + (round(255 * max(0.0, min(1.0, alpha))),)


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def seg(t, a, b):
    return clamp((t - a) / (b - a))


def ease_out(u):
    return 1 - (1 - clamp(u)) ** 3


def ease_in(u):
    return clamp(u) ** 3


def ease_io(u):
    u = clamp(u)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def back(u, s=1.9):
    u = clamp(u) - 1
    return 1 + u * u * ((s + 1) * u + s)


def pop(t, t0, d=0.38):
    return back(seg(t, t0, t0 + d)) if t >= t0 else 0.0


@lru_cache(None)
def font(px: int, display=False):
    return ImageFont.truetype(str(FONTS / ("Baloo2-ExtraBold.ttf" if display else "NunitoSans-Bold.ttf")), max(1, px))


class Pen:
    """Draws in 1920 x 1080 logical coordinates onto a canvas scaled by k."""

    def __init__(self, k=1.0, bg=None):
        # Opaque canvases are RGB so translucent fills blend; transparent ones are RGBA sprites.
        self.k = k
        size = (round(W * k), round(H * k))
        self.img = Image.new("RGB", size, bg) if bg else Image.new("RGBA", size, (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img, "RGBA")

    def s(self, *v):
        return [x * self.k for x in v]

    def rr(self, box, r, fill=None, outline=None, w=0):
        x0, y0, x1, y1 = box
        if x1 - x0 < 1 or y1 - y0 < 1:
            return
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        self.d.rounded_rectangle(self.s(*box), radius=r * self.k, fill=fill, outline=outline, width=round(w * self.k))

    def circle(self, x, y, r, fill=None, outline=None, w=0):
        if r > 0.5:
            self.d.ellipse(self.s(x - r, y - r, x + r, y + r), fill=fill, outline=outline, width=max(1, round(w * self.k)) if outline else 0)

    def arc(self, x, y, r, a0, a1, fill, w):
        if r > 1:
            self.d.arc(self.s(x - r, y - r, x + r, y + r), a0, a1, fill=fill, width=max(1, round(w * self.k)))

    def line(self, pts, fill, w):
        if len(pts) > 1:
            self.d.line([(x * self.k, y * self.k) for x, y in pts], fill=fill, width=max(1, round(w * self.k)), joint="curve")

    def poly(self, pts, fill, outline=None, w=0):
        self.d.polygon([(x * self.k, y * self.k) for x, y in pts], fill=fill, outline=outline, width=round(w * self.k))

    def text(self, xy, s, size, fill, display=False, anchor="la"):
        if size < 2:
            return
        f, (x, y) = font(round(size * self.k), display), self.s(*xy)
        alpha = fill[3] if isinstance(fill, tuple) and len(fill) == 4 else 255
        if alpha == 255:
            self.d.text((x, y), s, font=f, fill=fill, anchor=anchor)
        elif alpha:
            # Pillow ignores the alpha of text ink, so fade through a mask instead.
            x0, y0, x1, y1 = (math.floor(v) if n < 2 else math.ceil(v) for n, v in enumerate(self.d.textbbox((x, y), s, font=f, anchor=anchor)))
            mask = Image.new("L", (max(1, x1 - x0), max(1, y1 - y0)), 0)
            ImageDraw.Draw(mask).text((x - x0, y - y0), s, font=f, fill=alpha, anchor=anchor)
            self.img.paste(Image.new(self.img.mode, mask.size, fill[:3] + ((255,) if self.img.mode == "RGBA" else ())), (x0, y0), mask)

    def textlen(self, s, size, display=False):
        return font(round(size * self.k), display).getlength(s) / self.k

    def paste(self, im, x, y, alpha=1.0):
        if alpha < 1:
            im = im.copy()
            im.putalpha(im.getchannel("A").point(lambda v: round(v * alpha)))
        self.img.paste(im, (round(x * self.k), round(y * self.k)), im)

    def paste_center(self, im, cx, cy, scale=1.0, alpha=1.0):
        if scale <= 0.01:
            return
        if abs(scale - 1) > 0.005:
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.Resampling.BILINEAR)
        self.paste(im, cx - im.width / 2 / self.k, cy - im.height / 2 / self.k, alpha)


@lru_cache(96)
def photo(name, w, h, radius, k):
    tw, th = round(w * k), round(h * k)
    im = Image.open(PHOTO / name).convert("RGB")
    scale = max(tw / im.width, th / im.height)
    im = im.resize((math.ceil(im.width * scale), math.ceil(im.height * scale)), Image.Resampling.LANCZOS)
    dx, dy = (im.width - tw) // 2, (im.height - th) // 2
    im = im.crop((dx, dy, dx + tw, dy + th)).convert("RGBA")
    if radius:
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw, th), radius=round(radius * k), fill=255)
        im.putalpha(mask)
    return im


@lru_cache(64)
def sprite(path, w, h, k):
    im = Image.open(path).convert("RGBA")
    im.thumbnail((round(w * k), round(h * k)), Image.Resampling.LANCZOS)
    if im.width < round(w * k) and im.height < round(h * k):
        scale = min(w * k / im.width, h * k / im.height)
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
    return im


@lru_cache(16)
def polaroid(name, w, h, angle, k):
    pad = 18
    c = Pen(k)
    c.img = Image.new("RGBA", (round((w + 2 * pad) * k), round((h + 2 * pad + 44) * k)), (0, 0, 0, 0))
    c.d = ImageDraw.Draw(c.img, "RGBA")
    c.rr((0, 0, w + 2 * pad, h + 2 * pad + 44), 14, BUTTER)
    c.paste(photo(name, w, h, 8, k), pad, pad)
    return c.img.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)


# ---------------------------------------------------------------- shared pieces

def burst(p, t, t0, x, y, color=TOMATO, r=120, confetti=True):
    u = (t - t0) / 0.5
    if not 0 <= u <= 1:
        return
    if RECORDING["on"] and t - t0 < RECORDING["rate"] / FPS:
        RECORDING["bursts"].add((round(RECORDING["t"] - (t - t0) / RECORDING["rate"], 2), r, round(x)))
    e, fade = ease_out(u), 1 - u
    p.circle(x, y, r * (0.25 + 0.85 * e), outline=rgba(color, fade), w=max(2, 16 * fade))
    for i in range(8):
        a = i * math.pi / 4 + 0.39
        r0 = r * (0.6 + 0.75 * e)
        r1 = r0 + r * 0.38 * fade
        p.line([(x + r0 * math.cos(a), y + r0 * math.sin(a)), (x + r1 * math.cos(a), y + r1 * math.sin(a))], rgba(BUTTER, fade), 7)
    if confetti:
        for i, c in enumerate((PASTA, TEAL, TOMATO, PASTA, BUTTER, TEAL)):
            a = i * math.pi / 3 + 0.9
            d = r * (0.5 + 1.1 * e)
            cx, cy = x + d * math.cos(a), y + d * math.sin(a) + 40 * u * u
            size = 11 * (1 - 0.5 * u)
            if i % 2:
                p.circle(cx, cy, size, rgba(c, fade))
            else:
                p.rr((cx - size * 1.8, cy - size * 0.7, cx + size * 1.8, cy + size * 0.7), size, rgba(c, fade))


def noodle(p, t, y=1000, amp=16, color=PASTA, width=14, x0=-40, x1=W + 40, speed=2.4, wave=130):
    p.line([(x, y + amp * math.sin(x / wave + t * speed)) for x in range(int(x0), int(x1) + 1, 20)], color, width)


def vnoodle(p, t, x, y0=-40, y1=H + 40, amp=16, color=PASTA, width=14):
    p.line([(x + amp * math.sin(y / 110 + t * 3), y) for y in range(int(y0), int(y1) + 1, 20)], color, width)


def check(p, x, y, size=1.0, color=BUTTER, w=7):
    p.line([(x - 14 * size, y), (x - 4 * size, y + 11 * size), (x + 16 * size, y - 12 * size)], color, w * size)


def cross(p, x, y, size=1.0, color=BUTTER, w=7):
    p.line([(x - 11 * size, y - 11 * size), (x + 11 * size, y + 11 * size)], color, w * size)
    p.line([(x + 11 * size, y - 11 * size), (x - 11 * size, y + 11 * size)], color, w * size)


def cursor(p, x, y, pressed=False):
    s = 0.88 if pressed else 1.0
    pts = [(0, 0), (0, 46), (12, 35), (21, 54), (30, 50), (21, 32), (37, 32)]
    p.poly([(x + a * s, y + b * s) for a, b in pts], BUTTER, INK, 3)


def move(t, stops):
    """Piecewise eased path through (time, x, y) stops."""
    if t <= stops[0][0]:
        return stops[0][1:]
    for (t0, x0, y0), (t1, x1, y1) in pairwise(stops):
        if t <= t1:
            u = ease_io(seg(t, t0, t1))
            return x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
    return stops[-1][1:]


def skyline(p):
    p.rr((0, 820, W, H), 0, GROUND)
    for i, (x, w, h) in enumerate([(40, 170, 330), (230, 120, 220), (370, 210, 420), (600, 140, 280), (1180, 180, 360), (1380, 130, 250), (1530, 220, 440), (1770, 150, 300)]):
        p.rr((x, 820 - h, x + w, 820), 10, SKYLINE)
        for row in range(3, h // 60):
            for col in range(w // 55):
                if (row + col + i) % 3:
                    p.rr((x + 22 + col * 55, 820 - h + row * 60 - 150, x + 42 + col * 55, 820 - h + row * 60 - 122), 4, "#3A4E57")


def bench(p, x, y, color="#8C6A4F"):
    for yy in (y - 120, y - 80):
        p.rr((x - 170, yy, x + 170, yy + 22), 8, color)
    p.rr((x - 180, y, x + 180, y + 22), 8, color)
    for lx in (x - 140, x + 125):
        p.rr((lx, y + 18, lx + 16, y + 90), 5, "#5E4636")


def person(p, x, y, sitting=True, arm=0.0, mouth=0.0, holding="cup"):
    """Flat-vector learner. (x, y) is the hip point; arm 0 = resting, 1 = raised."""
    pants, top = "#6C8C99", TEAL
    if sitting:
        p.line([(x - 10, y - 8), (x + 80, y - 8)], pants, 44)
        p.line([(x + 80, y - 8), (x + 92, y + 82)], pants, 38)
        p.rr((x + 70, y + 76, x + 132, y + 96), 10, INK)
    else:
        for dx in (-18, 18):
            p.line([(x + dx, y - 10), (x + dx, y + 170)], pants, 36)
            p.rr((x + dx - 22, y + 162, x + dx + 34, y + 184), 10, BUTTER)
    p.rr((x - 42, y - 165, x + 42, y + 8), 36, top)
    p.circle(x - 28, y - 232, 30, HAIR)
    p.circle(x, y - 212, 46, HAIR)
    p.circle(x + 6, y - 204, 40, SKIN)
    p.rr((x - 36, y - 250, x + 40, y - 214), 18, HAIR)
    p.circle(x + 20, y - 208, 4.5, INK)
    p.circle(x + 36, y - 208, 4.5, INK)
    if mouth > 0.05:
        p.rr((x + 22, y - 190, x + 38, y - 184 + 10 * mouth), 6, "#8E3B2A")
    else:
        p.arc(x + 29, y - 196, 10, 20, 160, INK, 3)
    sx, sy = x + 14, y - 140
    hx, hy = x + 66 - 10 * arm, y - 88 - 120 * arm
    p.line([(sx, sy), ((sx + hx) / 2 + 22, (sy + hy) / 2 + 10), (hx, hy)], top, 26)
    p.circle(hx, hy, 14, SKIN)
    if holding == "cup":
        p.rr((hx - 4, hy - 30, hx + 26, hy + 8), 6, TOMATO)
    elif holding == "phone":
        p.rr((hx - 6, hy - 44, hx + 22, hy + 6), 6, INK, BUTTER, 3)


# ---------------------------------------------------------------- scenes

def s01_hook(p, t):
    p.rr((0, 0, W, H), 0, INK)
    skyline(p)
    flash = 1.45 < t < 2.4
    bench(p, 960, 760, PASTA if flash else "#8C6A4F")
    person(p, 900, 758)
    burst(p, t, 1.5, 960, 700, TOMATO, 190)
    s = pop(t, 0.35)
    if s:
        bx, by = 1130, 330
        p.poly([(bx - 40, by + 70 * s), (bx - 100, by + 150 * s), (bx + 10, by + 80 * s)], BUTTER)
        p.rr((bx - 130 * s, by - 90 * s, bx + 130 * s, by + 90 * s), 44 * s, BUTTER)
        p.text((bx, by + 4), "?", 150 * s, TOMATO, True, "mm")
    noodle(p, t, 1000, color=rgba(PASTA, seg(t, 0.2, 1.0)), x0=-40, x1=420)


def flashcard(word, gloss, k):
    c = Pen(k)
    c.img = Image.new("RGBA", (round(560 * k), round(130 * k)), (0, 0, 0, 0))
    c.d = ImageDraw.Draw(c.img, "RGBA")
    c.rr((0, 0, 560, 130), 26, "#3A474D", "#51626A", 3)
    c.text((34, 40), word, 50, MIST, True, "lm")
    c.text((34, 96), gloss, 26, "#7F8C90", False, "lm")
    return c.img


def s02_lists(p, t):
    p.rr((0, 0, W, H), 0, INK)
    skyline(p)
    bench(p, 520, 760)
    shrug = seg(t, 1.9, 2.3) - seg(t, 3.0, 3.4)
    person(p, 460, 758, arm=0.55 * shrug)
    p.text((1010, 190), "Lesson 1: vocabulary", 34, rgba(MIST, seg(t, 0.1, 0.4)), False)
    cards = [("la manzana", "the apple"), ("el niño", "the boy"), ("el coche rojo", "the red car")]
    for i, (word, gloss) in enumerate(cards):
        s = pop(t, 0.15 + i * 0.18)
        if not s:
            continue
        fall = ease_in(seg(t, 2.2 + i * 0.12, 3.1 + i * 0.12))
        im = flashcard(word, gloss, p.k).rotate((-4 + 4 * i) + 38 * fall * (1 if i % 2 else -1), expand=True, resample=Image.Resampling.BICUBIC)
        p.paste_center(im, 1300 + i * 40 + 80 * fall, 330 + i * 160 + 900 * fall, s * (1 - 0.3 * fall))
    p.text((1010, 860), "Someone else’s words.", 40, rgba(MIST, seg(t, 1.0, 1.4) - seg(t, 3.2, 3.6)), True)
    q = pop(t, 2.45)
    if q:
        p.text((560, 390), "?", 96 * q, MIST, True, "mm")
    noodle(p, t, 1000, x0=-40, x1=W * seg(t, 0, 3.6) + 40)


def headline_parts(p, size):
    a, b = "Learn the language of ", "your day."
    wa, wb = p.textlen(a, size, True), p.textlen(b, size, True)
    return a, b, wa, wb


def s03_logo(p, t):
    p.rr((0, 0, W, H), 0, INK)
    reveal = seg(t, 0.35, 1.05)
    loop = [(960 + 260 * math.cos(a) - 520 * (1 - a / (2 * math.pi)), 470 + 90 * math.sin(a))
            for a in [i / 40 * 2 * math.pi for i in range(41)]]
    drawn = loop[: max(2, int(len(loop) * seg(t, 0, 0.6)))]
    p.line([(-40, 700), (200, 620)] + drawn, rgba(PASTA, 1 - seg(t, 1.0, 1.4)), 14)
    mark = sprite(BRAND / "linguini-wordmark.png", 780, 260, p.k)
    if reveal:
        crop = mark.crop((0, 0, max(1, round(mark.width * reveal)), mark.height))
        p.paste(crop, 960 - mark.width / 2 / p.k, 300 - mark.height / 2 / p.k)
    burst(p, t, 1.05, 960, 300, TEAL, 300)
    burst(p, t, 1.15, 1290, 230, PASTA, 110)
    s = pop(t, 1.35)
    if s:
        size = 92 * s
        a, b, wa, wb = headline_parts(p, size)
        x = 960 - (wa + wb) / 2
        p.text((x, 600), a, size, BUTTER, True, "ls")
        p.text((x + wa, 600), b, size, PASTA, True, "ls")
        u = seg(t, 1.9, 2.4)
        if u:
            ux0 = x + wa
            p.line([(ux0 + i, 626 + 7 * math.sin(i / 26)) for i in range(0, int(wb * u), 8)], TOMATO, 10)
    noodle(p, t, 1010, color=rgba(PASTA, seg(t, 1.2, 1.8)))


SNAPS = [(0.55, "cafe-interior.jpg", "the café."), (2.15, "hillside-street.jpg", "the street."), (3.75, "golden-gate-bridge.jpg", "the bridge.")]
SCREEN = (1085, 150, 1535, 850)


def s04_snap(p, t):
    p.rr((0, 0, W, H), 0, DEEP)
    p.rr((1052, 96, 1568, 996), 58, "#0F2E2D")
    p.rr((1060, 90, 1560, 990), 56, BUTTER)
    x0, y0, x1, y1 = SCREEN
    sw, sh = x1 - x0, y1 - y0
    screen = Image.new("RGBA", (round(sw * p.k), round(sh * p.k)), rgba(INK))
    for i, (at, name, _) in enumerate(SNAPS):
        if t < at - 0.4 and i:
            continue
        off = 0 if i == 0 else (1 - ease_io(seg(t, at - 0.4, at - 0.05))) * sw
        screen.paste(photo(name, sw, sh, 0, p.k), (round(off * p.k), 0))
    mask = Image.new("L", screen.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *screen.size), radius=round(30 * p.k), fill=255)
    screen.putalpha(mask)
    p.paste(screen, x0, y0)
    for at, _, _ in SNAPS:
        f = 1 - seg(t, at, at + 0.14)
        if at <= t and f:
            p.rr(SCREEN, 30, rgba(BUTTER, 0.85 * f))
    press = max((1 - abs(t - at) / 0.12 for at, _, _ in SNAPS), default=0)
    r = 44 * (1 - 0.14 * clamp(press))
    p.circle(1310, 920, 54, TOMATO_PRESSED)
    p.circle(1310, 920, r + 6, BUTTER)
    p.circle(1310, 920, r, TOMATO)
    for at, _, _ in SNAPS:
        burst(p, t, at, 1310, 920, TOMATO, 120)
    p.text((170, 380), "Snap", 64, rgba(PASTA, seg(t, 0.1, 0.4)), True)
    for i, (at, _, word) in enumerate(SNAPS):
        s = pop(t, at)
        if s:
            p.text((170, 470 + i * 120), word, 104 * s, BUTTER, True)
    noodle(p, t, 1030, amp=12, x0=-40, x1=W + 40)


BRIDGE_WORDS = [("el puente", "the bridge", 60, 61), ("la torre", "the tower", 95, 30), ("el coche", "the car", 19, 70), ("el mar", "the sea", 65, 84), ("la colina", "the hill", 45, 22)]


def s05_markers(p, t):
    z = 1 + 0.06 * seg(t, 0, 4)
    zw, zh = round(W * z / 2) * 2, round(H * z / 2) * 2
    im = photo("golden-gate-bridge.jpg", zw, zh, 0, p.k)
    p.paste(im, -(zw - W) / 2, -(zh - H) / 2)
    p.rr((0, 0, W, H), 0, rgba(INK, 0.28))
    ph = W * 1047 / 1570
    for i, (word, gloss, px, py) in enumerate(BRIDGE_WORDS):
        at = 0.45 + i * 0.36
        s = pop(t, at)
        if not s:
            continue
        x = W / 2 + (px / 100 * W - W / 2) * z
        y = H / 2 + (py / 100 * ph - (ph - H) / 2 - H / 2) * z
        x, y = min(x, W - 60), min(y, 860)
        pulse = (t - at) % 1.4 / 1.4
        p.circle(x, y, 18 + 26 * pulse, outline=rgba(PASTA, 1 - pulse), w=5)
        p.circle(x, y, 20 * s, BUTTER)
        p.circle(x, y, 13 * s, PASTA)
        wl = max(p.textlen(word, 40, True), p.textlen(gloss, 24)) + 48
        right = x + 36 + wl < W - 30
        bx = x + 30 if right else x - 30 - wl
        ls = clamp(s)
        p.rr((bx, y - 56 * ls, bx + wl * ls, y + 40 * ls), 22, BUTTER)
        if s > 0.6:
            p.text((bx + 24, y - 16), word, 40, INK, True, "ls")
            p.text((bx + 24, y + 22), gloss, 24, TEAL_DARK, False, "ls")
        burst(p, t, at, x, y, PASTA, 70)
    s = pop(t, 0.2)
    if s:
        p.rr((70, 70, 70 + 420 * s, 136), 26, BUTTER)
        if s > 0.8:
            p.text((100, 104), "Across the bay · 5 words", 30, INK, False, "lm")


CHIPS = [("el", "puente", "masculine"), ("la", "torre", "feminine"), ("el", "coche", "masculine")]


def s06_choose(p, t):
    p.rr((0, 0, W, H), 0, INK)
    p.rr((132, 212, 832, 722), 32, "#1A2327")
    p.rr((120, 200, 820, 710), 32, BUTTER)
    p.paste(photo("golden-gate-bridge.jpg", 660, 400, 20, p.k), 140, 220)
    p.text((150, 670), "Across the bay", 34, INK, True, "ls")
    p.rr((912, 172, 1812, 912), 38, "#1A2327")
    p.rr((900, 160, 1800, 900), 38, BUTTER)
    p.text((960, 250), "Choose your words", 58, INK, True, "ls")
    p.text((962, 300), "Keep the useful ones. Drop the rest.", 30, MUTED, False, "ls")
    taps = [(1.05, 0), (1.6, 1), (2.3, 2)]
    for i, (article, noun, gender) in enumerate(CHIPS):
        y = 350 + i * 130
        s = pop(t, 0.15 + i * 0.12)
        dropped = seg(t, 2.35, 2.75) if i == 2 else 0
        kept = i < 2 and t >= taps[i][0]
        if not s or dropped >= 1:
            continue
        sc = s * (1 - dropped)
        cx, cy, w, h = 1340, y + 50, 780 * sc, 100 * sc
        p.rr((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), 24, SAGE if kept else "#FFFFFF", rgba(TOMATO, 1) if i == 2 and t > 2.25 else "#E4DCCB", 3)
        if sc > 0.7:
            x = cx - w / 2 + 34
            art = TOMATO if 0.3 < t < 1.0 or kept else INK
            p.text((x, cy + 16), article, 46, art, True, "ls")
            p.text((x + p.textlen(article + " ", 46, True), cy + 16), noun, 46, INK, True, "ls")
            p.text((cx + w / 2 - 120, cy + 10), gender, 26, MUTED, False, "rs")
            ix = cx + w / 2 - 58
            if kept:
                p.circle(ix, cy, 26, TEAL)
                check(p, ix, cy, 0.9)
            elif i == 2 and t > 2.25:
                p.circle(ix, cy, 26, TOMATO)
                cross(p, ix, cy, 0.8)
            else:
                p.circle(ix, cy, 26, outline="#C9C0AE", w=3)
        if kept:
            burst(p, t, taps[i][0], cx + w / 2 - 58, cy, TEAL, 80)
    burst(p, t, 2.35, 1680, 660, TOMATO, 90, confetti=False)
    s = pop(t, 0.55)
    if s:
        p.rr((950, 750, 950 + 300 * s, 830), 24, None, "#C9C0AE", 3)
        if s > 0.8:
            p.text((990, 790), "+  Add a word", 32, TEAL_DARK, False, "lm")
    if t > 0.8:
        x, y = move(t, [(0.8, 1500, 980), (1.0, 1682, 412), (1.45, 1682, 412), (1.6, 1682, 542), (2.1, 1682, 542), (2.25, 1682, 672), (2.8, 1682, 672), (3.4, 1850, 1000)])
        pressed = any(abs(t - at) < 0.08 for at, _ in taps)
        cursor(p, x, y, pressed)
    noodle(p, t, 1010, amp=12)


def word_card(k):
    c = Pen(k)
    c.rr((560, 250, 1360, 790), 44, BUTTER)
    c.text((620, 330), "From your photo", 30, TEAL_DARK, False, "ls")
    c.text((620, 470), "el puente rojo", 100, INK, True, "ls")
    c.text((624, 560), "/el ˈpwente ˈroxo/", 40, MUTED, False, "ls")
    c.text((624, 630), "the red bridge", 40, TEAL_DARK, False, "ls")
    c.rr((620, 690, 900, 746), 22, SAGE)
    c.text((646, 718), "masculine · noun", 26, TEAL_DARK, False, "lm")
    return c.img


def s07_hear(p, t):
    p.rr((0, 0, W, H), 0, DEEP)
    flip = back(seg(t, 0.05, 0.5), 1.4)
    if flip > 0.02:
        card = word_card(p.k).crop((round(560 * p.k), round(250 * p.k), round(1360 * p.k), round(790 * p.k)))
        card = card.resize((max(1, round(card.width * flip)), card.height), Image.Resampling.BILINEAR)
        p.paste(card, 960 - card.width / 2 / p.k, 250)
    burst(p, t, 0.5, 1360, 250, TEAL, 110)
    if t > 0.45:
        sx, sy = 1240, 700
        p.circle(sx, sy, 62, TEAL)
        p.poly([(sx - 26, sy - 14), (sx - 8, sy - 14), (sx + 14, sy - 34), (sx + 14, sy + 34), (sx - 8, sy + 14), (sx - 26, sy + 14)], BUTTER)
        for i in range(3):
            u = (t - 0.8 - i * 0.18) % 0.9 / 0.9 if 0.8 < t < 3.2 else 0
            if u:
                p.arc(sx, sy, 80 + 90 * u, -50, 50, rgba(PASTA, 1 - u), 8)
        burst(p, t, 0.8, sx, sy, PASTA, 90)
    noodle(p, t, 1010, amp=12)


BARS = [0.35, 0.6, 0.9, 0.55, 1, 0.7, 0.4, 0.8, 0.95, 0.5, 0.65, 0.3, 0.75, 0.45]


def s08_say(p, t):
    p.rr((0, 0, W, H), 0, INK)
    talking = 0.3 < t < 2.5
    person(p, 560, 760, sitting=False, arm=0.8, mouth=abs(math.sin(t * 14)) if talking else 0, holding="phone")
    p.rr((0, 944, W, H), 0, GROUND)
    s = pop(t, 0.1)
    if s:
        p.rr((820, 250, 820 + 900 * s, 330), 30, rgba(BUTTER, 0.1))
        p.text((860, 290), "Your turn: say it out loud", 36 * s, BUTTER, False, "lm")
    mx, my = 960, 540
    level = 1 if talking else 0.15
    ring = (t * 1.6) % 1
    if talking:
        p.circle(mx, my, 90 + 50 * ring, outline=rgba(TOMATO, 1 - ring), w=6)
    p.circle(mx, my, 86, TOMATO_PRESSED)
    p.circle(mx, my - 4, 84, TOMATO)
    p.rr((mx - 18, my - 50, mx + 18, my + 14), 18, BUTTER)
    p.arc(mx, my - 6, 34, 20, 160, BUTTER, 7)
    p.line([(mx, my + 28), (mx, my + 46)], BUTTER, 7)
    for i, a in enumerate(BARS):
        hgt = 20 + 150 * a * level * (0.6 + 0.4 * math.sin(t * 11 + i * 1.3))
        x = 1110 + i * 44
        p.rr((x, my - hgt / 2, x + 24, my + hgt / 2), 12, PASTA)
    p.text((860, 760), "el puente rojo", 88, rgba(PASTA, seg(t, 0.4, 0.8)), True, "ls")
    burst(p, t, 2.6, mx, my, TOMATO, 170)
    noodle(p, t, 1010, amp=12, color=rgba(PASTA, 0.9))


CHOICES = ["el coche", "la torre", "el mar", "la colina"]


def s09_ispy(p, t):
    p.rr((0, 0, W, H), 0, DEEP)
    shift = ease_io(seg(t, 3.0, 3.5))
    L = 440 - 360 * shift
    p.rr((L, 120, L + 850, 940), 36, BUTTER)
    p.paste(sprite(BRAND / "mascot-180.png", 120, 120, p.k), L + 700, 140)
    p.text((L + 50, 190), "LINGUINI SAYS", 28, TEAL_DARK, False, "ls")
    clue = ["Veo, veo… algo que es azul", "y está debajo del puente."]
    for i, line in enumerate(clue):
        p.text((L + 50, 290 + i * 70), line, 56, INK, True, "ls")
    p.text((L + 50, 420), "I spy… something blue under the bridge.", 28, MUTED, False, "ls")
    wrong, right = 1.55, 2.35
    for i, word in enumerate(CHOICES):
        s = pop(t, 0.3 + i * 0.1)
        if not s:
            continue
        cx = L + 50 + 190 + (i % 2) * 385
        cy = 560 + (i // 2) * 150
        if word == "el coche" and wrong < t < wrong + 0.45:
            cx += 14 * math.sin((t - wrong) * 60) * (1 - seg(t, wrong, wrong + 0.45))
        ok = word == "el mar" and t >= right
        bad = word == "el coche" and wrong < t < wrong + 0.8
        w, h = 360 * s, 120 * s
        p.rr((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), 26, TEAL if ok else CREAM, TOMATO if bad else "#E4DCCB", 4)
        if s > 0.7:
            p.text((cx - (22 if ok else 0), cy), word, 46, BUTTER if ok else INK, True, "mm")
        if ok:
            p.circle(cx + 130, cy, 24, BUTTER)
            check(p, cx + 130, cy, 0.8, TEAL)
    burst(p, t, right, L + 240, 710, TEAL, 200)
    xp = seg(t, right + 0.1, right + 1.0)
    if 0 < xp < 1:
        p.rr((L + 135, 600 - 90 * xp, L + 345, 670 - 90 * xp), 30, rgba(PASTA, 1 - xp * xp))
        p.text((L + 240, 636 - 90 * xp), "+10 XP", 36, rgba(INK, 1 - xp * xp), True, "mm")
    if t < 3.4:
        x, y = move(t, [(0.9, 900, 1000), (1.4, 400, 580), (1.9, 400, 580), (2.25, 785, 580), (3.0, 1000, 1000)])
        cursor(p, x, y, abs(t - wrong) < 0.08 or abs(t - right) < 0.08)
    if t > 2.9:
        vnoodle(p, t, 960, -40, -40 + (H + 80) * ease_io(seg(t, 2.9, 3.4)))
    if t > 3.2:
        up = 1 - ease_out(seg(t, 3.2, 3.7))
        R, top = 990, 120 + 900 * up
        p.rr((R, top, R + 850, top + 820), 36, CREAM)
        p.text((R + 50, top + 70), "YOUR TURN", 28, TEAL_DARK, False, "ls")
        p.text((R + 50, top + 160), "Describe something.", 56, INK, True, "ls")
        p.text((R + 50, top + 226), "Linguini guesses.", 56, INK, True, "ls")
        typed = "Es roja y muy alta."
        n = int(len(typed) * seg(t, 3.9, 5.0))
        p.rr((R + 50, top + 300, R + 800, top + 420), 28, BUTTER, "#E4DCCB", 3)
        p.text((R + 84, top + 362), typed[:n] + ("|" if int(t * 3) % 2 and t < 5.3 else ""), 50, INK, True, "lm")
        if t > 5.0:
            p.text((R + 54, top + 470), "It’s red and very tall.", 28, MUTED, False, "ls")
        s = pop(t, 5.45)
        if s:
            cx, cy = R + 425, top + 640
            p.rr((cx - 330 * s, cy - 80 * s, cx + 330 * s, cy + 80 * s), 32, TEAL)
            if s > 0.7:
                p.text((cx, cy - 20), "¡Bien hecho!", 54, BUTTER, True, "mm")
                p.text((cx, cy + 36), "You meant: la torre", 30, SAGE, False, "mm")
        burst(p, t, 5.45, R + 425, top + 640, PASTA, 220)


JOURNAL = "Hoy crucé el puente en coche. Desde el puente vi el mar azul y las colinas verdes. ¡La torre roja es enorme!"
HIGHLIGHT = {"puente", "coche", "mar", "colinas", "torre"}


def s10_journal(p, t):
    p.rr((0, 0, W, H), 0, INK)
    s = pop(t, 0.0, 0.45)
    if s:
        p.rr((960 - 790 * s, 540 - 410 * s, 960 + 790 * s, 540 + 410 * s), 40, CREAM)
    if s < 0.9:
        return
    vnoodle(p, t, 820, 140, 140 + 800 * ease_io(seg(t, 0.2, 0.8)), amp=8, width=10)
    for i, (name, ang, cx, cy) in enumerate([("lake-shore.jpg", -6, 470, 380), ("hillside-street.jpg", 5, 560, 600), ("golden-gate-bridge.jpg", -3, 450, 700)]):
        at = 0.35 + i * 0.3
        u = pop(t, at)
        if u:
            slide = 1 - ease_out(seg(t, at, at + 0.4))
            p.paste_center(polaroid(name, 400, 260, ang, p.k), cx - 500 * slide, cy, clamp(u, 0, 1.08))
    p.text((880, 250), "Saturday, 19 Sep", 30, rgba(MUTED, seg(t, 0.9, 1.2)), False, "ls")
    ts = pop(t, 1.1)
    if ts:
        p.text((880, 340), "El puente rojo", 80 * ts, INK, True, "ls")
    burst(p, t, 1.1, 1400, 300, PASTA, 120)
    size, lh, x0, y0, maxw = 40, 66, 880, 430, 800
    x, y, spans = x0, y0, []
    space = p.textlen(" ", size)
    for token in JOURNAL.split():
        w = p.textlen(token, size)
        if x + w > x0 + maxw:
            x, y = x0, y + lh
        spans.append((token, x, y, w))
        x += w + space
    order = 0
    for token, x, y, _ in spans:
        word = token.strip(".,¡!")
        if word.lower() in HIGHLIGHT:
            u = ease_out(seg(t, 2.0 + order * 0.45, 2.35 + order * 0.45))
            order += 1
            if u:
                x += p.textlen(token[: token.index(word)], size)
                p.rr((x - 6, y - 4, x - 6 + (p.textlen(word, size) + 12) * u, y + 50), 10, rgba(PASTA, 0.75))
    alpha = seg(t, 1.3, 1.8)
    for token, x, y, _ in spans:
        p.text((x, y), token, size, rgba(INK, alpha), False, "la")
    p.rr((880, 790, 932 + p.textlen("Your day, in Spanish", 30), 850), 24, rgba(SAGE, seg(t, 4.4, 4.8)))
    p.text((906, 820), "Your day, in Spanish", 30, rgba(TEAL_DARK, seg(t, 4.4, 4.8)), False, "lm")


PASTAS = [("farfalle", "Farfalle"), ("fusilli", "Fusilli"), ("penne", "Penne"), ("macaroni", "Macaroni")]


def s11_habit(p, t):
    p.rr((0, 0, W, H), 0, DEEP)
    s = pop(t, 0.05)
    if s:
        p.text((960, 170), "A few minutes a day.", 84 * s, BUTTER, True, "mm")
    bow = sprite(PASTA_DIR / "farfalle.png", 88, 88, p.k)
    for i, d in enumerate("MTWTFSS"):
        x = 960 + (i - 3) * 170
        at = 0.45 + i * 0.13
        p.circle(x, 380, 62, outline=rgba(BUTTER, 0.25), w=4)
        u = pop(t, at, 0.3)
        if u:
            p.circle(x, 380, 62 * clamp(u, 0, 1.1), rgba(BUTTER, 0.12))
            p.paste_center(bow, x, 380, u)
        p.text((x, 480), d, 30, MIST, False, "mm")
    burst(p, t, 0.45 + 6 * 0.13 + 0.1, 960 + 3 * 170, 380, PASTA, 120)
    s = pop(t, 1.45)
    if s:
        p.rr((960 - 150 * s, 520, 960 + 150 * s, 580), 30, PASTA)
        if s > 0.8:
            p.text((960, 550), "7-day streak", 32, INK, True, "mm")
    pick = 3.35
    for i, (key, name) in enumerate(PASTAS):
        at = 2.0 + i * 0.12
        u = pop(t, at)
        if not u:
            continue
        x = 480 + i * 320
        chosen = i == 1 and t >= pick
        grow = 1 + 0.2 * back(seg(t, pick, pick + 0.4)) if i == 1 else 1
        if chosen:
            p.circle(x, 730, 140 * clamp(pop(t, pick), 0, 1.1), rgba(PASTA, 0.22))
        p.paste_center(sprite(PASTA_DIR / f"{key}.png", 190, 190, p.k), x, 730 + 200 * (1 - clamp(u)), u * grow)
        p.text((x, 885), name, 34, PASTA if chosen else BUTTER, True, "mm")
    burst(p, t, pick, 800, 730, TOMATO, 200)


def icon(p, kind, x, y, s):
    c = TEAL_DARK
    if kind == "camera":
        p.rr((x - 52 * s, y - 34 * s, x + 52 * s, y + 40 * s), 16 * s, c)
        p.rr((x - 22 * s, y - 50 * s, x + 18 * s, y - 28 * s), 8 * s, c)
        p.circle(x, y + 3 * s, 24 * s, BUTTER)
        p.circle(x, y + 3 * s, 14 * s, c)
    elif kind == "tag":
        p.rr((x - 58 * s, y - 26 * s, x + 58 * s, y + 26 * s), 26 * s, c)
        p.circle(x - 34 * s, y, 9 * s, PASTA)
        p.text((x + 10 * s, y), "la", 40 * s, BUTTER, True, "mm")
    elif kind == "spy":
        p.circle(x - 10 * s, y - 10 * s, 34 * s, outline=c, w=13 * s)
        p.line([(x + 14 * s, y + 14 * s), (x + 44 * s, y + 44 * s)], c, 16 * s)
    else:
        p.rr((x - 54 * s, y - 40 * s, x - 3 * s, y + 42 * s), 10 * s, c)
        p.rr((x + 3 * s, y - 40 * s, x + 54 * s, y + 42 * s), 10 * s, c)
        for i in range(3):
            p.line([(x + 14 * s, y - 18 * s + i * 20 * s), (x + 42 * s, y - 18 * s + i * 20 * s)], BUTTER, 5 * s)


NODES = [("camera", "Photo"), ("tag", "Words"), ("spy", "Play"), ("book", "Journal")]


def s12_recap(p, t):
    p.rr((0, 0, W, H), 0, INK)
    reveal = W * ease_io(seg(t, 0, 3.4)) + 80
    p.line([(x, 540 + 70 * math.sin(x / 200)) for x in range(-40, int(reveal), 16)], PASTA, 16)
    for i, (kind, label) in enumerate(NODES):
        at = 0.44 + i * 0.89
        x = 360 + i * 400
        y = 540 + 70 * math.sin(x / 200)
        s = pop(t, at)
        if s:
            p.circle(x, y, 112 * s, BUTTER, PASTA, 8)
            icon(p, kind, x, y, s)
            p.text((x, y + 190), label, 64 * s, BUTTER, True, "mm")
        burst(p, t, at, x, y, (TOMATO, TEAL, PASTA, TOMATO)[i], 170)


def s13_end(p, t):
    p.rr((0, 0, W, H), 0, INK)
    mark = sprite(BRAND / "linguini-wordmark.png", 780, 260, p.k)
    s = pop(t, 0.2, 0.45)
    shrink = ease_io(seg(t, 0, 0.7))
    half = W / 2 + 40 - (W / 2 + 40 - 300) * shrink
    p.line([(x, 470 + 10 * math.sin(x / 40 + t * 4) * (1 - shrink)) for x in range(int(960 - half), int(960 + half), 12)], PASTA, 14 - 4 * shrink)
    if s:
        p.paste_center(mark, 960, 320, s)
    burst(p, t, 0.5, 960, 320, TEAL, 330)
    burst(p, t, 0.6, 1320, 220, PASTA, 120)
    s = pop(t, 0.85)
    if s:
        p.text((960, 610), "The world is your lesson.", 80 * s, BUTTER, True, "mm")
    s = pop(t, 1.2)
    if s:
        press = 6 if 2.2 < t < 2.4 else 0
        p.rr((960 - 230 * s, 700, 960 + 230 * s, 796), 26, TOMATO_PRESSED)
        p.rr((960 - 230 * s, 692 + press, 960 + 230 * s, 788 + press), 26, TOMATO)
        if s > 0.8:
            p.text((960, 740 + press), "Try a mini session", 40, "#FFFFFF", False, "mm")
    p.text((960, 870), "linguini-landing.vercel.app", 38, rgba(PASTA, seg(t, 1.5, 1.9)), False, "mm")


# (original length, final length, scene, name, voiceover cues as (seconds into scene, text)).
# Original lengths are the authoring timebase for each scene's animation; final lengths are
# whole beats at 120 BPM, so every cut lands on a beat and the drop and end card on downbeats.
SCENES = [
    (3, 2.5, s01_hook, "Hook", [(0.15, "Quick. What's bench, in Spanish?")]),
    (4, 4.0, s02_lists, "Problem", [(0.1, "Word lists taught you apple."), (1.55, "But outside? You still can't name the bench.")]),
    (4, 3.5, s03_logo, "Reveal", [(0.3, "Meet Linguini."), (1.45, "Learn the language of your day.")]),
    (6, 4.5, s04_snap, "Snap", [(0.0, "Snap the café."), (1.3, "The street."), (2.35, "The view from the bridge.")]),
    (4, 3.0, s05_markers, "Words in the photo", [(0.1, "Linguini finds the words inside your photo,")]),
    (4, 3.5, s06_choose, "Keep or drop", [(0.0, "articles attached."), (1.3, "Keep what's useful. Drop the rest.")]),
    (4, 2.0, s07_hear, "Hear it", [(0.25, "Hear it,")]),
    (4, 2.5, s08_say, "Say it", [(0.05, "then say it, out loud.")]),
    (7, 5.5, s09_ispy, "I-Spy", [(0.05, "Play I Spy."), (1.0, "Crack Linguini's clue,"), (2.6, "then describe something back.")]),
    (7, 5.0, s10_journal, "Journal", [(0.1, "Finish with a journal page."), (1.75, "Your new words, pinned to a day you actually lived.")]),
    (5, 4.0, s11_habit, "Habit", [(0.0, "A few minutes a day."), (1.2, "Keep your streak."), (2.3, "Pick your pasta.")]),
    (4, 4.5, s12_recap, "Recap", [(0.42, "Photo."), (1.42, "Words."), (2.42, "Play."), (3.42, "Journal.")]),
    (4, 5.0, s13_end, "End card", [(0.3, "Linguini."), (1.05, "The world is your lesson."), (2.4, "Try a free mini session today.")]),
]
STARTS = [sum(s[1] for s in SCENES[:i]) for i in range(len(SCENES) + 1)]
DURATION = STARTS[-1]
# How each scene enters: slide direction (dx, dy) or a push into the phone screen.
ENTRANCES = [None, (1, 0), (0, -1), (1, 0), "zoom", (0, 1), (1, 0), (1, 0), (0, -1), (1, 0), (0, 1), (1, 0), (0, -1)]
BREAKDOWN = [(22.5, 26.5)]
CAPTIONS = {"Quick. What's bench, in Spanish?": "Quick: what’s “bench” in Spanish?", "Word lists taught you apple.": "Word lists taught you “apple.”",
            "Play I Spy.": "Play I-Spy."}


def render_scene(i, t, k):
    authored, final, fn, _, _ = SCENES[i]
    rate = authored / final
    RECORDING.update(t=t, rate=rate)
    p = Pen(k, INK)
    fn(p, max(0.0, t - STARTS[i]) * rate)
    return p.img


def render(t, k=1.0):
    t = min(t, DURATION - 1e-3)
    i = next(n for n in range(len(SCENES)) if STARTS[n] <= t < STARTS[n + 1])
    base = Pen(k, INK)
    boundary = None
    if t - STARTS[i] < TRANSITION / 2 and i > 0:
        boundary, a_i, b_i = STARTS[i], i - 1, i
    elif STARTS[i + 1] - t < TRANSITION / 2 and i < len(SCENES) - 1:
        boundary, a_i, b_i = STARTS[i + 1], i, i + 1
    if boundary is None:
        return render_scene(i, t, k)
    u = ease_io((t - boundary + TRANSITION / 2) / TRANSITION)
    A, B = render_scene(a_i, t, k), render_scene(b_i, t, k)
    mode = ENTRANCES[b_i]
    if mode == "zoom":
        z = 1 + 1.6 * u
        cx, cy = 1310 * k, 500 * k
        box = (cx - cx / z, cy - cy / z, cx + (A.width - cx) / z, cy + (A.height - cy) / z)
        return Image.blend(A.resize(A.size, Image.Resampling.BILINEAR, box=box), B, clamp(u * 1.4 - 0.2))
    dx, dy = mode
    base.img.paste(A, (round(-dx * u * W * k), round(-dy * u * H * k)))
    base.img.paste(B, (round(dx * (1 - u) * W * k), round(dy * (1 - u) * H * k)))
    base.d = ImageDraw.Draw(base.img, "RGBA")
    if dx:
        vnoodle(base, t, W * (1 - u) if dx > 0 else W * u, width=18)
    else:
        noodle(base, t, H * u if dy < 0 else H * (1 - u), width=18, amp=22)
    return base.img


# (scene index, seconds into the scene's authored timebase, file name)
STYLE_FRAMES = [(2, 2.6, "explainer-frame-01-reveal.png"), (4, 2.4, "explainer-frame-02-words.png"), (9, 5.2, "explainer-frame-03-journal.png")]


def style_frames():
    for i, local, name in STYLE_FRAMES:
        t = STARTS[i] + local * SCENES[i][1] / SCENES[i][0]
        render(t, k=2).convert("RGB").resize((W, H), Image.Resampling.LANCZOS).save(OUT / name, optimize=True)
        print(f"{name}: t={t:.2f}s")


def srt_time(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def video():
    import soundtrack

    cues = [(STARTS[i] + at, text) for i, scene in enumerate(SCENES) for at, text in scene[4]]
    clips = soundtrack.voiceover(cues)
    ends = [STARTS[i + 1] for i, scene in enumerate(SCENES) for _ in scene[4]]
    for n, ((start, text, audio), scene_end) in enumerate(zip(clips, ends, strict=True)):
        end = start + len(audio) / soundtrack.SR
        limit = min(clips[n + 1][0] if n + 1 < len(clips) else DURATION, scene_end + 0.3)
        print(f"VO {start:5.2f}-{end:5.2f}s{'  OVERLAP' if end > limit else ''}  {text}")
    with tempfile.TemporaryDirectory() as d:
        silent, wav = Path(d) / "video.mp4", Path(d) / "mix.wav"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", str(silent)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        RECORDING.update(on=True, bursts=set())
        frames = round(DURATION * FPS)
        for n in range(frames):
            RECORDING["t"] = n / FPS
            proc.stdin.write(render(n / FPS).convert("RGB").tobytes())
            if n % (FPS * 10) == 0:
                print(f"frame {n}/{frames}")
        RECORDING["on"] = False
        proc.stdin.close()
        if proc.wait():
            raise SystemExit("ffmpeg failed")
        transitions = [(STARTS[i], ENTRANCES[i] == "zoom" or ENTRANCES[i][0] != 0) for i in range(1, len(SCENES))]
        soundtrack.write_wav(wav, soundtrack.mix(DURATION, clips, RECORDING["bursts"], transitions, BREAKDOWN, STARTS[-2]))
        target = OUT / "explainer.mp4"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-c:v", "copy",
                        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-shortest",
                        "-movflags", "+faststart", str(target)], check=True)
    with open(OUT / "explainer.srt", "w") as f:
        for n, (start, text, audio) in enumerate(clips, 1):
            f.write(f"{n}\n{srt_time(start)} --> {srt_time(start + len(audio) / soundtrack.SR)}\n{CAPTIONS.get(text, text)}\n\n")
    render(STARTS[-2] + 3.0).convert("RGB").save(OUT / "explainer-poster.png", optimize=True)
    print(f"{target.name}: {DURATION:.1f}s, {target.stat().st_size / 1e6:.1f} MB, {len(RECORDING['bursts'])} synced effects")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", action="store_true", help="style frames only")
    ap.add_argument("--still", type=float, help="write one review frame at this time to /tmp")
    args = ap.parse_args()
    if args.still is not None:
        path = Path(tempfile.gettempdir()) / f"linguini-explainer-{args.still:05.2f}.png"
        render(args.still).convert("RGB").save(path)
        print(path)
    else:
        style_frames()
        if not args.frames:
            video()

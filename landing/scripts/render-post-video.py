"""Render the looping cover video for the business-model blog post.

Run from any directory with: python3 landing/scripts/render-post-video.py
Requires Pillow and ffmpeg. Writes public/blog/business-model.mp4 and a poster JPEG.
Everything is drawn from the site's own photo, fonts and brand colours.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public/blog"
FONTS = ROOT / "assets/fonts"
W, H, FPS, SECONDS = 1280, 800, 24, 12

BUTTER, PAPER, CREAM, INK, MUTED = "#FBF8EF", "#FFFDF8", "#FFF2D6", "#263238", "#5D6C70"
TOMATO, TEAL, TEAL_DEEP, PASTA, SAGE, LINE = "#EF5B32", "#00968F", "#184F4E", "#F9AE22", "#DCEBDD", "#E4DCCB"

# Words and marker positions from landing/data/scenes.ts (hillside-street).
WORDS = [("el coche", 47, 62), ("la casa", 58, 33), ("la flor", 18, 66), ("la calle", 50, 86)]
# Expected cost per call (chosen models, then the cheapest alternatives), from
# marketing/business-model/model/unit-economics.json ("breakdown").
COSTS = [("Scene analysis", 0.00736, 0.00229), ("Translation", 0.00025, 0.00025), ("Learning tasks", 0.01024, 0.00454),
         ("I-Spy clues", 0.00046, 0.00022), ("I-Spy guesses", 0.00172, 0.00063)]


def font(size, display=False):
    return ImageFont.truetype(str(FONTS / ("Baloo2-ExtraBold.ttf" if display else "NunitoSans-Bold.ttf")), size)


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def spring(t):
    t = max(0.0, min(1.0, t))
    return 1 + 2.2 * (t - 1) ** 3 + 1.2 * (t - 1) ** 2 if t < 1 else 1.0


def window(t, start, length):
    return ease((t - start) / length)


def cover(path, size, radius):
    im = Image.open(path).convert("RGB")
    tw, th = size
    scale = max(tw / im.width, th / im.height)
    im = im.resize((math.ceil(im.width * scale), math.ceil(im.height * scale)), Image.Resampling.LANCZOS)
    dx, dy = (im.width - tw) // 2, (im.height - th) // 2
    im = im.crop((dx, dy, dx + tw, dy + th)).convert("RGBA")
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw, th), radius=radius, fill=255)
    im.putalpha(mask)
    return im, (scale, dx, dy, im.width, im.height)


def shadow(canvas, box, radius, alpha=40, blur=18, dy=10):
    layer = Image.new("RGBA", canvas.size)
    ImageDraw.Draw(layer).rounded_rectangle((box[0], box[1] + dy, box[2], box[3] + dy), radius, fill=(64, 52, 33, alpha))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


PHOTO_BOX = (70, 150, 760, 690)
PHOTO, _ = cover(ROOT / "public/photos/hillside-street.jpg", (PHOTO_BOX[2] - PHOTO_BOX[0], PHOTO_BOX[3] - PHOTO_BOX[1]), 26)
SRC_W, SRC_H = 1570, 1047
WORDMARK = Image.open(ROOT / "public/brand/linguini-wordmark.png").convert("RGBA")
WORDMARK.thumbnail((200, 64), Image.Resampling.LANCZOS)
MASCOT = Image.open(ROOT / "public/brand/mascot-180.png").convert("RGBA").resize((120, 120), Image.Resampling.LANCZOS)


def marker_xy(x_pct, y_pct):
    """Map a scene marker (percent of the source photo) into the cropped card."""
    bw, bh = PHOTO_BOX[2] - PHOTO_BOX[0], PHOTO_BOX[3] - PHOTO_BOX[1]
    scale = max(bw / SRC_W, bh / SRC_H)
    dx, dy = (SRC_W * scale - bw) / 2, (SRC_H * scale - bh) / 2
    return PHOTO_BOX[0] + x_pct / 100 * SRC_W * scale - dx, PHOTO_BOX[1] + y_pct / 100 * SRC_H * scale - dy


def chrome(canvas):
    d = ImageDraw.Draw(canvas)
    canvas.alpha_composite(WORDMARK, (64, 44))
    label = "THE LINGUINI BUSINESS MODEL"
    w = d.textlength(label, font=font(16))
    d.rounded_rectangle((W - 64 - w - 28, 52, W - 64, 88), 18, fill=SAGE)
    d.text((W - 64 - w - 14, 60), label, font=font(16), fill=TEAL_DEEP)


def scene_photo(t):
    c = Image.new("RGBA", (W, H), BUTTER)
    d = ImageDraw.Draw(c)
    d.ellipse((900, -260, 1500, 340), fill="#FFE8C1")
    chrome(c)
    shadow(c, PHOTO_BOX, 26)
    c.alpha_composite(PHOTO, PHOTO_BOX[:2])
    d = ImageDraw.Draw(c)
    for i, (word, x, y) in enumerate(WORDS):
        k = spring((t - 0.5 - i * 0.45) / 0.6)
        if k <= 0:
            continue
        mx, my = marker_xy(x, y)
        f = font(24)
        w = d.textlength(word, font=f) + 44
        h = 44
        s = max(0.01, k)
        box = (mx - w * s / 2, my - h * s / 2, mx + w * s / 2, my + h * s / 2)
        d.rounded_rectangle(box, radius=22 * s, fill=PAPER)
        if s > 0.85:
            d.ellipse((box[0] + 14, my - 5, box[0] + 24, my + 5), fill=TOMATO)
            d.text((box[0] + 32, my - 15), word, font=f, fill=INK)
    k = window(t, 0.3, 0.7)
    x = 820 + (1 - k) * 40
    d.text((x, 250), "1 free photo", font=font(62, True), fill=INK)
    d.text((x, 318), "lesson a day", font=font(62, True), fill=INK)
    k2 = window(t, 1.4, 0.6)
    if k2 > 0:
        d.text((x, 420), "plus one journal page,", font=font(28), fill=MUTED)
        d.text((x, 458), "every day, on the house.", font=font(28), fill=MUTED)
    return c


TIERS = [("Free", "$0", "1 photo lesson a day", SAGE, INK), ("Plus", "$49.99", "a year · or $7.99 a month", TEAL_DEEP, PAPER),
         ("Founding Plus", "$34.99", "a year · first 300", CREAM, INK)]


def scene_tiers(t):
    c = Image.new("RGBA", (W, H), BUTTER)
    d = ImageDraw.Draw(c)
    d.ellipse((-260, 480, 360, 1100), fill="#FBE9C8")
    chrome(c)
    k = window(t, 0.1, 0.5)
    d.text((80, 150 + (1 - k) * 20), "Free to start. Plus when you’re hooked.", font=font(52, True), fill=INK)
    for i, (name, price, per, fill, ink) in enumerate(TIERS):
        k = spring((t - 0.45 - i * 0.3) / 0.7)
        if k <= 0:
            continue
        x0 = 80 + i * 380
        y0 = 280 + (1 - k) * 90
        box = (x0, y0, x0 + 350, y0 + 380)
        shadow(c, box, 30, alpha=int(45 * min(1, k)))
        layer = Image.new("RGBA", (W, H))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle(box, 30, fill=fill)
        ld.text((x0 + 32, y0 + 34), name, font=font(34, True), fill=ink)
        ld.text((x0 + 32, y0 + 96), price, font=font(78, True), fill=ink)
        ld.text((x0 + 32, y0 + 196), per, font=font(22), fill=ink if ink == INK else "#C9DEDB")
        for j, line in enumerate({0: ["Curated scenes to replay", "Word games and streaks"],
                                  1: ["10 photo lessons a day", "Pronunciation feedback"],
                                  2: ["Competitive I-Spy beta", "Vote on the roadmap"]}[i]):
            ld.ellipse((x0 + 32, y0 + 262 + j * 44, x0 + 48, y0 + 278 + j * 44), fill=TOMATO if i == 1 else TEAL)
            ld.text((x0 + 60, y0 + 255 + j * 44), line, font=font(21), fill=ink)
        if i == 1:
            glow = window(t, 1.6, 0.6)
            ld.rounded_rectangle((box[0] - 6, box[1] - 6, box[2] + 6, box[3] + 6), 36,
                                 outline=(249, 174, 34, int(255 * glow)), width=5)
        layer.putalpha(layer.getchannel("A").point(lambda a, k=k: int(a * min(1, k * 1.3))))
        c.alpha_composite(layer)
    return c


def scene_costs(t):
    c = Image.new("RGBA", (W, H), BUTTER)
    d = ImageDraw.Draw(c)
    d.ellipse((920, 420, 1560, 1060), fill="#FFE8C1")
    chrome(c)
    shrink = window(t, 2.2, 1.0)
    d.text((80, 150), "AI cost of one photo lesson", font=font(52, True), fill=INK)
    x0, x1, top = 360, 1040, 280
    scale = (x1 - x0) / 0.011
    total = 0.0
    for i, (name, now, cheap, *_) in enumerate(COSTS):
        grow = window(t, 0.3 + i * 0.22, 0.6)
        value = (now + (cheap - now) * shrink) * grow
        total += value
        y = top + i * 66
        d.text((x0 - 24, y + 4), name, font=font(26), fill=INK, anchor="ra")
        d.rounded_rectangle((x0, y + 6, x1, y + 34), 8, fill="#ECE5D6")
        if value > 0:
            d.rounded_rectangle((x0, y + 6, x0 + max(10, value * scale), y + 34), 8, fill=TOMATO if shrink < 0.5 else TEAL)
        d.text((x0 + max(10, value * scale) + 16, y + 2), f"${value:.4f}", font=font(26), fill=INK)
    label = "Chosen models, via OpenRouter" if shrink < 0.5 else "Cheapest alternatives, still being tested"
    d.text((80, 640), label, font=font(28), fill=MUTED)
    d.text((80, 676), f"${total:.3f} per lesson", font=font(56, True), fill=TOMATO if shrink < 0.5 else TEAL_DEEP)
    c.alpha_composite(MASCOT, (W - 200, H - 190))
    return c


SCENES = [(scene_photo, 4.0), (scene_tiers, 4.0), (scene_costs, 4.0)]


def frame(t):
    start = 0.0
    for index, (render, length) in enumerate(SCENES):
        if t < start + length:
            local = t - start
            img = render(local)
            fade = 0.35
            if local > length - fade:
                nxt = SCENES[(index + 1) % len(SCENES)][0](0.0)
                img = Image.blend(img, nxt, (local - (length - fade)) / fade)
            return img.convert("RGB")
        start += length
    return SCENES[0][0](0).convert("RGB")


def main():
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required")
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for n in range(FPS * SECONDS):
            frame(n / FPS).save(f"{tmp}/{n:04}.png")
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{tmp}/%04d.png",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-preset", "slow", "-movflags", "+faststart",
            "-an", str(OUT / "business-model.mp4"),
        ], check=True)
    frame(3.2).save(OUT / "business-model-poster.jpg", quality=86)
    for name in ("business-model.mp4", "business-model-poster.jpg"):
        print(f"{name}: {(OUT / name).stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()

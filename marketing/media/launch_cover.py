"""Render the animated cover for the launch-week blog post: a silent, looping MP4.

Run from any directory with: python3 marketing/media/launch_cover.py
Requires Pillow and ffmpeg. Writes cover-loop.mp4 and cover-loop-poster.jpg to
landing/public/blog/launch/. Same composition as banners.blog_cover(): headline on
the left, the real launch banners landing one by one on the right, then the stack
clears and the loop starts again. Frame 0 and the last frame match.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from render import BRAND, CREAM, INK, MUTED, PAPER, ROOT, TEAL_DARK, TOMATO, font, txt

WEB = ROOT / "landing/public/blog/launch"
W, H = 1280, 800
FPS = 30
SECONDS = 9
FRAMES = FPS * SECONDS
POSTER_AT = 7.6  # seconds: every card landed and the upvote pill showing

# Card arrivals and the reset, in seconds.
FIRST, GAP, LAND = 0.25, 0.8, 0.9
EXIT, EXIT_LEN = 7.85, 0.75

# (file, width, centre x, centre y, angle), in stacking order.
CARDS = [
    ("01-your-world.jpg", 440, 860, 200, -4),
    ("ig-post-1080x1350.jpg", 210, 1135, 250, 6),
    ("02-find-your-words.jpg", 430, 1005, 420, 3),
    ("ig-story-1080x1920.jpg", 180, 725, 470, -6),
    ("03-play-and-build.jpg", 420, 1030, 590, -3),
    ("launch-card-1200x630.jpg", 400, 870, 330, 2),
    ("04-keep-the-day.jpg", 410, 1015, 245, -2),
    ("x-header-1500x500.jpg", 500, 905, 665, 3),
]


def ease_out(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def ease_in(t):
    t = min(max(t, 0.0), 1.0)
    return t ** 3


def ease_back(t, s=1.4):
    """Ease-out with a small overshoot, for the upvote pill pop."""
    t = min(max(t, 0.0), 1.0) - 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def fade(im, a):
    """Multiply an RGBA image's alpha by `a`."""
    if a >= 1:
        return im
    out = im.copy()
    out.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return out


def card(path, width, border=10):
    """A banner printed on paper with a thin white border, like blog_cover's prints."""
    im = Image.open(path).convert("RGBA")
    im = im.resize((width, round(im.height * width / im.width)), Image.Resampling.LANCZOS)
    c = Image.new("RGBA", (im.width + 2 * border, im.height + 2 * border), PAPER)
    c.alpha_composite(im, (border, border))
    return c


def posed(base, angle, scale=1.0, blur=16, dx=6, dy=16, strength=0.34):
    """Rotate and scale a card, and give it a soft drop shadow. Returns a centred sprite."""
    im = base
    if scale != 1:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
    padded = Image.new("RGBA", (im.width + 8, im.height + 8))
    padded.alpha_composite(im, (4, 4))  # transparent margin so rotated edges are antialiased
    rot = padded.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    pad = blur * 3
    out = Image.new("RGBA", (rot.width + 2 * pad, rot.height + 2 * pad))
    mask = Image.new("L", out.size)
    mask.paste(rot.getchannel("A").point(lambda v: int(v * strength)), (pad + dx, pad + dy))
    shadow = Image.new("RGBA", out.size, (50, 38, 20, 0))
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(blur)))
    out.alpha_composite(shadow)
    out.alpha_composite(rot, (pad, pad))
    return out


def place(canvas, sprite, cx, cy):
    canvas.alpha_composite(sprite, (round(cx - sprite.width / 2), round(cy - sprite.height / 2)))


def blobs(t):
    """The pasta-yellow circles from the still cover, breathing once per loop."""
    layer = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(layer)
    phase = math.sin(2 * math.pi * t / SECONDS)
    for (x0, y0, x1, y1), fill, k in (
        ((784, -288, 1472, 400), "#FFE8C1", 1),
        ((-208, 560, 336, 1104), "#FBE9C8", -1),
    ):
        grow = 10 * phase * k
        d.ellipse((x0 - grow, y0 - grow, x1 + grow, y1 + grow), fill=fill)
    return layer


def headline():
    """Static left column: wordmark and the display headline."""
    layer = Image.new("RGBA", (W, H))
    mark = Image.open(BRAND / "linguini-wordmark.png").convert("RGBA")
    mark.thumbnail((320, 72), Image.Resampling.LANCZOS)
    layer.alpha_composite(mark, (72, 72))
    txt(ImageDraw.Draw(layer), (64, 170), "Launch\nweek.", 150, INK, True, spacing=-26)
    return layer


def date_parts():
    """The launch line, split into pieces that tick in one after another."""
    icon = Image.open(WEB / "product-hunt-icon-240.png").convert("RGBA")
    icon = icon.resize((58, 58), Image.Resampling.LANCZOS)
    first = Image.new("RGBA", (420, 64))
    first.alpha_composite(icon, (0, 3))
    txt(ImageDraw.Draw(first), (74, 32), "Product Hunt", 42, INK, anchor="lm")
    parts = [(first, 72, 560)]
    x = 72
    for label in ("Sat 17 Oct", "·", "3:01pm SGT"):
        f = font(34)
        w = int(f.getlength(label)) + 4
        im = Image.new("RGBA", (w, 50))
        txt(ImageDraw.Draw(im), (0, 25), label, 34, TEAL_DARK if label != "·" else MUTED, anchor="lm")
        parts.append((im, x, 632))
        x += w + 12
    return parts


def upvote():
    f = font(34)
    w = int(f.getlength("Upvote")) + 110
    h = 68
    im = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), h // 2, fill=TOMATO)
    cx, cy = 42, h / 2
    d.polygon([(cx - 13, cy + 10), (cx + 13, cy + 10), (cx, cy - 13)], fill="#FFFFFF")
    txt(d, (68, cy), "Upvote", 34, "#FFFFFF", anchor="lm")
    return im


class Cover:
    def __init__(self):
        self.text = headline()
        self.parts = date_parts()
        self.pill = upvote()
        self.cards = [card(WEB / name, width) for name, width, *_ in CARDS]
        self.landed = [posed(c, spec[4]) for c, spec in zip(self.cards, CARDS)]

    def frame(self, t):
        c = blobs(t)
        c.alpha_composite(self.text)
        out = 1 - ease_in((t - EXIT) / EXIT_LEN)  # 1 until the reset, then fades to 0

        for i, (im, x, y) in enumerate(self.parts):
            e = ease_out((t - 0.35 - i * 0.3) / 0.45)
            if e > 0 and out > 0:
                c.alpha_composite(fade(im, e * out), (x, round(y + 14 * (1 - e))))

        p = (t - 6.85) / 0.5
        if p > 0 and out > 0:
            s = max(ease_back(p), 0.01)
            pill = self.pill.resize((max(1, round(self.pill.width * s)), max(1, round(self.pill.height * s))),
                                    Image.Resampling.LANCZOS)
            pill = fade(pill, min(p * 2.5, 1) * out)
            c.alpha_composite(pill, (round(72 + self.pill.width / 2 - pill.width / 2),
                                     round(700 + self.pill.height / 2 - pill.height / 2)))

        if out <= 0:
            return c.convert("RGB")
        stack = Image.new("RGBA", (W, H))
        for i, (base, spec) in enumerate(zip(self.cards, CARDS)):
            _, _, cx, cy, angle = spec
            e = ease_out((t - FIRST - i * GAP) / LAND)
            if e <= 0:
                continue
            if e < 1:
                sprite = posed(base, angle + 9 * (1 - e), 0.93 + 0.07 * e)
                place(stack, fade(sprite, min(e * 1.6, 1)), cx + 220 * (1 - e), cy + 120 * (1 - e))
            else:
                place(stack, self.landed[i], cx, cy)
        # The reset clears the stack as one sheet so overlapping cards never show through each other.
        c.alpha_composite(fade(stack, out), (0, round(50 * (1 - out))))
        return c.convert("RGB")


def main():
    cover = Cover()
    mp4 = WEB / "cover-loop.mp4"
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264",
         "-preset", "slow", "-crf", "28", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
        stdin=subprocess.PIPE,
    )
    for n in range(FRAMES):
        ffmpeg.stdin.write(cover.frame(n / FPS).tobytes())
    ffmpeg.stdin.close()
    if ffmpeg.wait():
        raise SystemExit("ffmpeg failed")
    cover.frame(POSTER_AT).save(WEB / "cover-loop-poster.jpg", quality=85, optimize=True, progressive=True)
    print(f"{mp4.name}: {mp4.stat().st_size / 1024:.0f} KiB, {SECONDS}s at {FPS} fps")


if __name__ == "__main__":
    main()

"""Render the launch banners: profile headers, the launch-day card and Instagram posts.

Run from any directory with: python3 marketing/media/banners.py
Requires Pillow. Writes PNGs to marketing/media/export/banners/ and web JPEGs to
landing/public/blog/launch/ for the launch campaign post.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from render import (
    BRAND, CREAM, INK, LINE, MUTED, PAPER, PHOTO, ROOT, SAGE, TEAL_DARK, TOMATO,
    cover, font, mascot, rr, shadow_card, txt, wrap,
)

OUT = Path(__file__).resolve().parent / "export" / "banners"
WEB = ROOT / "landing/public/blog/launch"
OUT.mkdir(parents=True, exist_ok=True)
WEB.mkdir(parents=True, exist_ok=True)

LAUNCH = "Sat 17 Oct · 3:01pm SGT"

# Word positions are percentages of the source photo, copied from landing/data/scenes.ts.
SCENES = {
    "hillside-street": [(47, 62, "el coche"), (58, 33, "la casa"), (18, 66, "la flor"), (50, 86, "la calle")],
    "golden-gate-bridge": [(60, 61, "el puente"), (65, 84, "el mar"), (45, 22, "la colina")],
    "cafe-interior": [(45, 60, "la mesa"), (76, 30, "la lámpara"), (32, 72, "el taburete")],
}


def chip(canvas, x, y, label, size=24):
    """A word label pinned to a photo, like the demo's markers."""
    f = font(size)
    w = int(f.getlength(label)) + size + 30
    h = size + 22
    x0, y0 = int(x - 10), int(y - h / 2)
    sh = Image.new("RGBA", canvas.size)
    ImageDraw.Draw(sh).rounded_rectangle((x0, y0 + 5, x0 + w, y0 + h + 5), h // 2, fill=(40, 30, 15, 70))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((x0, y0, x0 + w, y0 + h), h // 2, fill=PAPER)
    r = size * 0.32
    cx, cy = x0 + 12 + r, y0 + h / 2
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=TOMATO)
    txt(d, (x0 + 18 + 2 * r, y0 + h / 2), label, size, INK, anchor="lm")


def photo(canvas, scene, box, radius=24, words=None, size=24):
    """Paste a scene photo cropped to `box` and pin its words where the demo does."""
    x0, y0, x1, y1 = box
    im, mask = cover(PHOTO / f"{scene}.jpg", box, radius)
    canvas.paste(im, (int(x0), int(y0)), mask)
    src = Image.open(PHOTO / f"{scene}.jpg")
    tw, th = x1 - x0, y1 - y0
    scale = max(tw / src.width, th / src.height)
    dx, dy = (src.width * scale - tw) / 2, (src.height * scale - th) / 2
    for px, py, label in (words if words is not None else SCENES[scene]):
        x = x0 + px / 100 * src.width * scale - dx
        y = y0 + py / 100 * src.height * scale - dy
        width = font(size).getlength(label) + size + 40
        if x0 < x < x1 and y0 + 30 < y < y1 - 30:
            chip(canvas, max(x0 + 24, min(x, x1 - width - 14)), y, label, size)


def framed(canvas, scene, box, pad=16, radius=30, words=None, size=24):
    shadow_card(canvas, box, radius)
    photo(canvas, scene, (box[0] + pad, box[1] + pad, box[2] - pad, box[3] - pad), radius - 10, words, size)


def logo(canvas, x, y, height):
    im = Image.open(BRAND / "linguini-wordmark.png").convert("RGBA")
    im.thumbnail((height * 4, height), Image.Resampling.LANCZOS)
    canvas.alpha_composite(im, (int(x), int(y)))


def pill(d, x, y, label, size=22, fill=SAGE, color=TEAL_DARK):
    f = font(size)
    w = int(f.getlength(label)) + 36
    rr(d, (x, y, x + w, y + size + 22), (size + 22) // 2, fill)
    txt(d, (x + 18, y + (size + 22) / 2), label, size, color, anchor="lm")
    return w


def blob(d, box, fill="#FFE8C1"):
    d.ellipse(box, fill=fill)


def save(canvas, name):
    rgb = canvas.convert("RGB")
    rgb.save(OUT / f"{name}.png", optimize=True)
    rgb.save(WEB / f"{name}.jpg", quality=86, optimize=True, progressive=True)


def x_header():
    """X profile header. The avatar covers the bottom-left, so text sits top-left."""
    W, H = 1500, 500
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    blob(d, (-160, 300, 330, 790), "#FBE9C8")
    blob(d, (1080, -260, 1640, 300))
    logo(c, 80, 52, 64)
    txt(d, (78, 138), "Learn the language\nof your day.", 66, INK, True, spacing=-6)
    txt(d, (82, 312), "Spanish and French from everyday photos.", 26, MUTED)
    framed(c, "golden-gate-bridge", (760, 70, 1080, 330), 12, 24, [(60, 61, "el puente"), (65, 84, "el mar")], 20)
    framed(c, "hillside-street", (1040, 150, 1440, 450), 14, 26, [(47, 62, "el coche"), (58, 33, "la casa")], 21)
    d = ImageDraw.Draw(c)
    pill(d, 82, 360, "On Product Hunt " + LAUNCH, 20, INK, PAPER)
    save(c, "x-header-1500x500")


def linkedin_banner():
    """LinkedIn page cover. The logo covers the far left, so copy starts past it."""
    W, H = 1584, 396
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    blob(d, (1200, -300, 1760, 260))
    blob(d, (-200, 250, 260, 710), "#FBE9C8")
    txt(d, (330, 70), "Your photo is the lesson.", 64, INK, True)
    txt(d, (334, 158), wrap("Snap a café, a street, a view. Linguini turns it into a short Spanish or French lesson and a journal page.", 640, 25), 25, MUTED, spacing=8)
    pill(d, 334, 280, "Launching on Product Hunt " + LAUNCH, 20, TOMATO, "#FFFFFF")
    framed(c, "cafe-interior", (1060, 40, 1500, 356), 14, 26, [(45, 60, "la mesa"), (76, 30, "la lámpara")], 21)
    mascot(c, 980, 250, 110)
    save(c, "linkedin-1584x396")


def launch_card():
    """Link card for launch day: Telegram, WhatsApp, Slack and Discord previews."""
    W, H = 1200, 630
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    blob(d, (760, -280, 1400, 360))
    blob(d, (-180, 440, 300, 920), "#FBE9C8")
    logo(c, 64, 48, 60)
    pill(d, 64, 146, "LIVE ON PRODUCT HUNT TODAY", 21, TOMATO, "#FFFFFF")
    txt(d, (60, 210), "Point at your\nday. Learn\nthe words.", 72, INK, True, spacing=-8)
    txt(d, (64, 500), wrap("Try a short Spanish or French photo lesson, then tell us where you got stuck.", 500, 24), 24, MUTED, spacing=6)
    framed(c, "hillside-street", (600, 80, 1140, 560), 16, 30, size=23)
    save(c, "launch-card-1200x630")


def ig_portrait():
    """Instagram feed post, 4:5. Launch announcement."""
    W, H = 1080, 1350
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    blob(d, (560, -300, 1300, 440))
    logo(c, 80, 76, 70)
    txt(d, (76, 190), "Today’s lesson\nis on your\ncamera roll.", 92, INK, True, spacing=-10)
    framed(c, "cafe-interior", (80, 560, 1000, 1150), 18, 34, size=28)
    d = ImageDraw.Draw(c)
    pill(d, 80, 1200, "Spanish · French", 24)
    txt(d, (1000, 1222), "Product Hunt · 17 Oct", 26, TEAL_DARK, anchor="rm")
    mascot(c, 850, 440, 150)
    save(c, "ig-post-1080x1350")


def ig_story():
    """Instagram story, 9:16. Leaves the top 250 and bottom 340 px clear for the UI and link sticker."""
    W, H = 1080, 1920
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    blob(d, (520, -200, 1400, 640))
    blob(d, (-300, 1400, 420, 2120), "#FBE9C8")
    logo(c, 90, 270, 76)
    txt(d, (84, 390), "We’re live\non Product\nHunt today.", 116, INK, True, spacing=-14)
    framed(c, "golden-gate-bridge", (90, 850, 990, 1440), 18, 36, size=30)
    d = ImageDraw.Draw(c)
    txt(d, (540, 1510), "Tell us where you got stuck.", 36, MUTED, anchor="mm")
    rr(d, (300, 1560, 780, 1640), 40, PAPER, LINE, 3)
    txt(d, (540, 1600), "Link sticker here", 28, MUTED, anchor="mm")
    save(c, "ig-story-1080x1920")


def countdown():
    """Square teaser for the week before launch."""
    W = H = 1080
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    blob(d, (-240, -240, 520, 520), "#FFE8C1")
    txt(d, (90, 110), "3", 330, TOMATO, True)
    txt(d, (320, 230), "days to\nlaunch", 92, INK, True, spacing=-10)
    framed(c, "hillside-street", (90, 500, 990, 910), 16, 32, [(47, 62, "el coche"), (58, 33, "la casa"), (18, 66, "la flor")], 27)
    d = ImageDraw.Draw(c)
    txt(d, (90, 970), "Linguini on Product Hunt · " + LAUNCH, 30, INK)
    txt(d, (90, 1016), "Turn on notifications for launch day", 24, MUTED)
    save(c, "countdown-1080x1080")


def countdown_story():
    """Story version of the countdown, 9:16, same safe areas as ig_story."""
    W, H = 1080, 1920
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    blob(d, (-360, 40, 560, 960), "#FFE8C1")
    blob(d, (700, 1500, 1400, 2200), "#FBE9C8")
    logo(c, 90, 270, 76)
    txt(d, (80, 360), "3", 420, TOMATO, True)
    txt(d, (390, 520), "days to\nlaunch", 120, INK, True, spacing=-14)
    framed(c, "hillside-street", (90, 900, 990, 1420), 18, 36, [(47, 62, "el coche"), (58, 33, "la casa"), (18, 66, "la flor")], 30)
    d = ImageDraw.Draw(c)
    txt(d, (90, 1480), "Linguini on Product Hunt", 40, INK)
    txt(d, (90, 1536), LAUNCH, 34, MUTED)
    save(c, "ig-story-countdown-1080x1920")


def blog_cover():
    """16:10 cover for the launch campaign blog post: the kit laid out on the table."""
    W, H = 1600, 1000
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    blob(d, (980, -360, 1840, 500))
    blob(d, (-260, 640, 420, 1320), "#FBE9C8")

    def print_(path, width, xy, angle):
        im = Image.open(path).convert("RGBA")
        im = im.resize((width, round(im.height * width / im.width)), Image.Resampling.LANCZOS)
        card = Image.new("RGBA", (im.width + 24, im.height + 24), PAPER)
        card.alpha_composite(im, (12, 12))
        card = card.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        sh = Image.new("RGBA", c.size)
        sh.paste((50, 38, 20, 80), (xy[0] + 8, xy[1] + 22), card.getchannel("A"))
        c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(20)))
        c.alpha_composite(card, xy)

    print_(OUT.parent / "01-your-world.png", 640, (840, 70), -4)
    print_(OUT / "ig-post-1080x1350.png", 330, (1180, 440), 5)
    print_(OUT / "x-header-1500x500.png", 700, (700, 640), 3)
    d = ImageDraw.Draw(c)
    logo(c, 90, 100, 80)
    txt(d, (84, 250), "Launch\nweek.", 170, INK, True, spacing=-24)
    txt(d, (92, 640), wrap("Our Product Hunt plan, the posts, the banners and the checklist.", 520, 34), 34, MUTED, spacing=8)
    save(c, "blog-cover-1600x1000")


if __name__ == "__main__":
    for render in (x_header, linkedin_banner, launch_card, ig_portrait, ig_story, countdown, countdown_story, blog_cover):
        render()
    print(f"Wrote banners to {OUT} and {WEB}")

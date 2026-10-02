"""Render editable Linguini launch graphics from assets already in the repo.

Run from any directory with: python3 marketing/media/render.py
Requires Pillow. Outputs remain in marketing/media/export/.
"""

from __future__ import annotations

from pathlib import Path
import math
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "export"
OUT.mkdir(exist_ok=True)
PHOTO = ROOT / "landing/public/photos"
BRAND = ROOT / "landing/public/brand"
FONTS = ROOT / "landing/assets/fonts"

W, H = 1270, 760
CREAM = "#FBF8EF"
PAPER = "#FFFDF8"
INK = "#263238"
MUTED = "#5D6C70"
TOMATO = "#EF5B32"
TEAL = "#2E9C99"
TEAL_DARK = "#21716F"
PASTA = "#F9AE22"
SAGE = "#DCEBDD"
LINE = "#E4DCCB"


def font(size: int, display=False):
    name = "Baloo2-ExtraBold.ttf" if display else "NunitoSans-Bold.ttf"
    return ImageFont.truetype(FONTS / name, size)


def txt(draw, xy, s, size, fill=INK, display=False, anchor=None, spacing=8):
    draw.multiline_text(xy, s, font=font(size, display), fill=fill, anchor=anchor, spacing=spacing)


def wrap(s: str, max_width: int, size: int, display=False):
    f = font(size, display)
    lines, line = [], ""
    for word in s.split():
        trial = f"{line} {word}".strip()
        if f.getlength(trial) > max_width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return "\n".join(lines)


def rr(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def cover(path, box, radius=0):
    x0, y0, x1, y1 = box
    tw, th = int(x1 - x0), int(y1 - y0)
    im = Image.open(path).convert("RGB")
    scale = max(tw / im.width, th / im.height)
    im = im.resize((math.ceil(im.width * scale), math.ceil(im.height * scale)), Image.Resampling.LANCZOS)
    dx, dy = (im.width - tw) // 2, (im.height - th) // 2
    im = im.crop((dx, dy, dx + tw, dy + th)).convert("RGBA")
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw, th), radius=radius, fill=255)
    return im, mask


def paste_cover(canvas, path, box, radius=0):
    im, mask = cover(path, box, radius)
    canvas.paste(im, (int(box[0]), int(box[1])), mask)


def shadow_card(canvas, box, radius=30, fill=PAPER, blur=22, dy=10):
    sh = Image.new("RGBA", canvas.size)
    d = ImageDraw.Draw(sh)
    d.rounded_rectangle((box[0], box[1] + dy, box[2], box[3] + dy), radius=radius, fill=(64, 52, 33, 44))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(canvas).rounded_rectangle(box, radius=radius, fill=fill)


def wordmark(canvas, x=65, y=35, height=56):
    im = Image.open(BRAND / "linguini-wordmark.png").convert("RGBA")
    im.thumbnail((320, height), Image.Resampling.LANCZOS)
    canvas.alpha_composite(im, (x, y))


def mascot(canvas, x, y, size):
    im = Image.open(BRAND / "mascot-180.png").convert("RGBA")
    im = im.resize((size, size), Image.Resampling.LANCZOS)
    canvas.alpha_composite(im, (x, y))


def eyebrow(draw, x, y, label, color=TEAL_DARK):
    rr(draw, (x, y, x + 198, y + 38), 18, SAGE)
    txt(draw, (x + 16, y + 7), label, 19, color)


def foot(draw, n):
    draw.line((65, 715, 1205, 715), fill=LINE, width=2)
    txt(draw, (66, 722), "LINGUINI · LEARN THE LANGUAGE OF YOUR DAY", 15, MUTED)
    txt(draw, (1204, 722), f"0{n} / 04", 15, MUTED, anchor="ra")


def preview_label(draw, right=1205):
    left = right - 216
    rr(draw, (left, 37, right, 70), 12, INK)
    txt(draw, (left + 13, 43), "ILLUSTRATIVE PREVIEW", 15, PAPER)


def save(canvas, name):
    canvas.convert("RGB").save(OUT / name, quality=94, subsampling=0)


def slide1():
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    # Warm orange ribbon and subtle paper dots.
    d.ellipse((855, -290, 1500, 355), fill="#FFE8C1")
    d.ellipse((-190, 490, 380, 1060), fill="#FBE9C8")
    wordmark(c)
    eyebrow(d, 66, 142, "PHOTO-LED LEARNING")
    txt(d, (62, 205), "See a scene.\nLearn its language.", 68, INK, True, spacing=-4)
    txt(d, (66, 422), wrap("Explore Spanish or French through everyday photo scenes.", 480, 28), 28, MUTED, spacing=8)
    rr(d, (66, 577, 390, 637), 19, TOMATO)
    txt(d, (91, 589), "Try the demo", 26, "#FFFFFF")
    # Two real sample photos as paper prints.
    shadow_card(c, (730, 95, 1203, 605), 26)
    paste_cover(c, PHOTO / "hillside-street.jpg", (751, 117, 1182, 495), 14)
    d = ImageDraw.Draw(c)
    txt(d, (913, 512), "Hillside drive", 29, INK, True)
    txt(d, (915, 553), "5 words · Spanish", 18, MUTED)
    shadow_card(c, (620, 356, 895, 647), 24)
    paste_cover(c, PHOTO / "golden-gate-bridge.jpg", (635, 371, 880, 570), 12)
    d = ImageDraw.Draw(c)
    txt(d, (650, 581), "Across the bay", 22, INK, True)
    mascot(c, 1060, 543, 125)
    d = ImageDraw.Draw(c)
    preview_label(d)
    foot(d, 1)
    save(c, "01-your-world.png")


def label(d, x, y, text, dot=TOMATO):
    w = int(font(21).getlength(text)) + 38
    rr(d, (x, y, x + w, y + 42), 16, PAPER)
    d.ellipse((x + 12, y + 16, x + 21, y + 25), fill=dot)
    txt(d, (x + 28, y + 6), text, 21, INK)


def slide2():
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    wordmark(c)
    txt(d, (65, 119), "Find words in everyday scenes.", 53, INK, True)
    txt(d, (67, 188), "Pick a demo photo, then choose the Spanish or French words to learn.", 23, MUTED)
    shadow_card(c, (65, 265, 825, 668), 26)
    paste_cover(c, PHOTO / "hillside-street.jpg", (79, 279, 811, 654), 16)
    d = ImageDraw.Draw(c)
    label(d, 288, 473, "el coche")
    label(d, 503, 354, "la casa", TEAL)
    label(d, 110, 496, "la flor", PASTA)
    shadow_card(c, (856, 265, 1205, 668), 28)
    d = ImageDraw.Draw(c)
    txt(d, (885, 292), "From this scene", 19, TEAL_DARK)
    txt(d, (885, 334), "el coche", 43, INK, True)
    txt(d, (887, 391), "the car", 20, MUTED)
    d.line((885, 438, 1176, 438), fill=LINE, width=2)
    txt(d, (885, 463), "Also found", 20, TEAL_DARK)
    for y, item in [(509, "la casa  ·  house"), (550, "la flor  ·  flower"), (591, "la calle  ·  street")]:
        d.ellipse((888, y + 9, 900, y + 21), fill=TEAL)
        txt(d, (910, y), item, 21, INK)
    preview_label(d)
    foot(d, 2)
    save(c, "02-find-your-words.png")


def slide3():
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    wordmark(c)
    txt(d, (65, 119), "A small session. A story to tell.", 54, INK, True)
    txt(d, (67, 189), "See the words, play I-Spy, then build a sentence from the scene.", 23, MUTED)
    shadow_card(c, (65, 261, 674, 668), 27)
    paste_cover(c, PHOTO / "golden-gate-bridge.jpg", (80, 276, 659, 653), 17)
    d = ImageDraw.Draw(c)
    rr(d, (101, 296, 291, 334), 18, PAPER)
    txt(d, (117, 303), "A scene from your day", 17, INK)
    shadow_card(c, (707, 261, 1205, 668), 28)
    d = ImageDraw.Draw(c)
    txt(d, (739, 288), "LINGUINI SAYS", 19, TEAL_DARK)
    txt(d, (739, 333), wrap("Veo, veo… algo que es azul y está debajo del puente.", 420, 31, True), 31, INK, True)
    txt(d, (739, 450), "I spy something blue under the bridge.", 19, MUTED)
    rr(d, (739, 504, 1172, 565), 17, SAGE)
    txt(d, (761, 516), "Correct: el mar", 27, TEAL_DARK)
    txt(d, (741, 596), "Word cards / I-Spy / Sentence", 18, MUTED)
    preview_label(d)
    foot(d, 3)
    save(c, "03-play-and-build.png")


def slide4():
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    wordmark(c)
    txt(d, (65, 119), "Finish with a journal page.", 59, INK, True)
    txt(d, (67, 195), "Use words from the scene to write a short story in Spanish or French.", 23, MUTED)
    shadow_card(c, (72, 275, 914, 662), 29)
    paste_cover(c, PHOTO / "hillside-street.jpg", (91, 294, 433, 642), 20)
    d = ImageDraw.Draw(c)
    txt(d, (466, 303), "Saturday, 19 Sep", 18, MUTED)
    txt(d, (466, 347), "Una calle con flores", 38, INK, True)
    body = "Hoy subí una calle muy bonita. Había flores por todas partes y un coche rojo bajaba despacio. ¡Quiero vivir en una de esas casas!"
    txt(d, (466, 414), wrap(body, 407, 21), 21, INK, spacing=11)
    rr(d, (466, 575, 830, 622), 16, SAGE)
    txt(d, (487, 584), "Sample journal entry from the demo", 20, TEAL_DARK)
    shadow_card(c, (947, 343, 1199, 633), 28, fill="#FFF2D6")
    mascot(c, 973, 357, 195)
    d = ImageDraw.Draw(c)
    txt(d, (1073, 558), "Come back", 22, INK, True, anchor="mt")
    txt(d, (1073, 588), "tomorrow.", 22, INK, True, anchor="mt")
    preview_label(d)
    foot(d, 4)
    save(c, "04-keep-the-day.png")


def social():
    c = Image.new("RGBA", (1080, 1080), CREAM)
    d = ImageDraw.Draw(c)
    d.ellipse((628, -140, 1330, 562), fill="#FFE8C1")
    wordmark(c, 76, 65, 83)
    txt(d, (76, 188), "A photo scene.\nA fresh lesson.", 83, INK, True, spacing=3)
    txt(d, (80, 419), "Explore Spanish or French in interactive photo scenes.", 28, MUTED)
    shadow_card(c, (109, 536, 683, 991), 28)
    paste_cover(c, PHOTO / "hillside-street.jpg", (126, 553, 666, 916), 17)
    d = ImageDraw.Draw(c)
    txt(d, (145, 930), "Hillside drive  ·  el coche", 24, INK, True)
    shadow_card(c, (650, 637, 994, 940), 26)
    paste_cover(c, PHOTO / "golden-gate-bridge.jpg", (665, 652, 979, 871), 15)
    d = ImageDraw.Draw(c)
    txt(d, (681, 882), "Across the bay", 21, INK, True)
    mascot(c, 808, 420, 176)
    txt(d, (79, 1027), "Try the interactive demo", 21, TEAL_DARK)
    preview_label(d, 1000)
    save(c, "social-square.png")


def product_hunt_icon():
    source = Image.open(BRAND / "linguini-logo.png").convert("RGBA")
    for size in (240, 512):
        c = Image.new("RGBA", (size, size), PAPER)
        img = source.resize((int(size * .9), int(size * .9)), Image.Resampling.LANCZOS)
        c.alpha_composite(img, ((size - img.width) // 2, (size - img.height) // 2))
        c.save(OUT / f"product-hunt-icon-{size}.png")


def teaser_frames():
    frame_dir = OUT / "teaser-frames"
    frame_dir.mkdir(exist_ok=True)
    for index, name in enumerate(("01-your-world.png", "02-find-your-words.png", "03-play-and-build.png", "04-keep-the-day.png"), 1):
        im = Image.open(OUT / name).convert("RGB").crop((0, 0, W, 714))
        im = im.resize((1280, 720), Image.Resampling.LANCZOS)
        d = ImageDraw.Draw(im)
        rr(d, (927, 18, 1250, 53), 13, INK)
        txt(d, (942, 25), "ILLUSTRATED PRODUCT TEASER", 16, PAPER)
        im.save(frame_dir / f"{index:02}.png", quality=95)
    c = Image.new("RGBA", (1280, 720), CREAM)
    d = ImageDraw.Draw(c)
    d.ellipse((810, -170, 1450, 470), fill="#FFE8C1")
    wordmark(c, 100, 78, 98)
    txt(d, (100, 241), "Make today\na lesson.", 88, INK, True)
    txt(d, (104, 491), "Try the interactive demo", 30, MUTED)
    rr(d, (101, 559, 929, 625), 18, TOMATO)
    txt(d, (126, 569), "linguini-landing.vercel.app", 30, PAPER)
    mascot(c, 999, 406, 185)
    rr(d, (927, 18, 1250, 53), 13, INK)
    txt(d, (942, 25), "ILLUSTRATED PRODUCT TEASER", 16, PAPER)
    c.convert("RGB").save(frame_dir / "05.png", quality=95)


if __name__ == "__main__":
    slide1(); slide2(); slide3(); slide4(); social(); product_hunt_icon(); teaser_frames()
    for path in sorted(OUT.glob("*.png")):
        print(f"{path.name}: {path.stat().st_size / 1024:.0f} KiB")

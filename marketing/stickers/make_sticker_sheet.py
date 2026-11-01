"""Build the Linguini sticker sheet PDF (A4 landscape, 300 DPI).

The page is two identical A5-portrait halves side by side (cut the page in
half vertically for two standalone sheets). Every sticker is exactly 3 cm.

Both halves carry the same curated 4x3 grid: all five mascot moods plus
seven badges, with a "catch us at STEPS" promo line in the header.

Outputs:
  linguini-sticker-sheet.png  (preview)
  linguini-sticker-sheet.pdf  (print, 300 DPI)

Run from the repo root:  python marketing/stickers/make_sticker_sheet.py
"""

import qrcode
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUB = ROOT / "frontend" / "public"
FONTS = ROOT / "marketing" / "STePs" / "gif-studio" / "assets"
OUT = Path(__file__).parent

TEAL = (33, 113, 111)      # #21716F
MUTED = (138, 125, 95)

DPI = 300
PAGE_W, PAGE_H = 3508, 2480          # A4 landscape @300dpi
HALF_W = PAGE_W // 2                 # A5 portrait = 148.5 x 210 mm
CM = 300 / 2.54                      # px per cm
TOMATO = (232, 93, 50)     # #E85D32

STICKER = int(3 * CM)                # 3 cm sticker box = 354 px
COLS, ROWS = 4, 3                    # curated 12 per half

# Same set on both halves — the mascots + most iconic badges
STICKERS = [
    "ratings/rating-4.png",          # smiley
    "linguini-logo-cool.png",        # sunglasses
    "ratings/rating-5.png",          # heart-eyes
    "badges/daily-dish.webp",        # noodle bowl
    "badges/ask-away.webp",          # speech bubble blob
    "badges/pick-flavour.webp",      # flag blob
    "badges/spot-and-say.webp",      # magnifier tube
    "badges/count-me-in.webp",       # three tubes
    "ratings/rating-3.png",          # neutral
    "ratings/rating-1.png",          # angry
    "badges/seek-and-find.webp",
    "badges/price-tag.webp",
]


def load(path):
    im = Image.open(PUB / path).convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    return im.crop(bbox) if bbox else im


def fit(im, box):
    # thumbnail() only shrinks — resize so smaller art also scales up to `box`
    w, h = im.size
    r = box / max(w, h)
    return im.resize((round(w * r), round(h * r)), Image.LANCZOS)


def draw_half(page, x0):
    """One A5 portrait half: header (wordmark + URL + QR) and a 3x3 grid of 4cm stickers."""
    draw = ImageDraw.Draw(page, "RGBA")
    nunito = lambda s: ImageFont.truetype(str(FONTS / "NunitoSans-Bold.ttf"), s)
    baloo = lambda s: ImageFont.truetype(str(FONTS / "Baloo2-ExtraBold.ttf"), s)
    cx = x0 + HALF_W // 2

    # Header — big wordmark + website centred, QR top-right
    wm = fit(load("linguini-wordmark.png"), 440)
    page.paste(wm, (cx - wm.width // 2, 60), wm)
    draw.text((cx, 245), "learnwithlinguini.com",
              font=nunito(64), fill=TEAL, anchor="mm")
    draw.text((cx, 345), "catch us at STePS · 11 Nov · CS3216-03",
              font=baloo(56), fill=TOMATO, anchor="mm")
    draw.text((cx, 415), "NUS COM3-MPH · 2pm-8pm",
              font=nunito(42), fill=MUTED, anchor="mm")

    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data("https://www.learnwithlinguini.com")
    qr_img = qr.make_image(fill_color=(38, 50, 56), back_color="white").convert("RGBA")
    qr_img = qr_img.resize((190, 190), Image.NEAREST)
    qx = x0 + HALF_W - 60 - qr_img.width
    page.paste(qr_img, (qx, 50), qr_img)
    draw.text((qx + qr_img.width // 2, 265), "scan · try it out",
              font=nunito(30), fill=MUTED, anchor="mm")

    # Grid — 4 cols x 3 rows of 3 cm stickers, spread across the half
    header_h = 470
    grid_w = HALF_W - 2 * 60
    cell_w = grid_w // COLS
    grid_h = PAGE_H - header_h - 50
    row_pitch = grid_h // ROWS

    for i, path in enumerate(STICKERS):
        col, row = i % COLS, i // COLS
        scx = x0 + 60 + col * cell_w + cell_w // 2
        cy = header_h + row * row_pitch + row_pitch // 2

        art = fit(load(path), STICKER)
        page.paste(art, (scx - art.width // 2, cy - art.height // 2), art)


def main():
    page = Image.new("RGBA", (PAGE_W, PAGE_H), (255, 255, 255, 255))
    draw_half(page, 0)
    draw_half(page, HALF_W)

    # dashed cut line at the A5 boundary (vertical)
    draw = ImageDraw.Draw(page)
    y = 60
    while y < PAGE_H - 60:
        draw.line((HALF_W, y, HALF_W, y + 18), fill=(200, 196, 180), width=3)
        y += 36

    page.convert("RGB").save(OUT / "linguini-sticker-sheet.png")
    page.convert("RGB").save(OUT / "linguini-sticker-sheet.pdf",
                             "PDF", resolution=DPI)
    print("wrote", OUT / "linguini-sticker-sheet.png")
    print("wrote", OUT / "linguini-sticker-sheet.pdf")


if __name__ == "__main__":
    main()

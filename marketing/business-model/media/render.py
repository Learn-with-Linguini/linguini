"""Render Linguini business-model charts and pricing promotion graphics.

Run from any directory with: python3 marketing/business-model/media/render.py
Requires Pillow. Reads marketing/business-model/model/unit-economics.json (run
cost_model.py first) and reuses the drawing helpers in marketing/media/render.py.
Outputs go to marketing/business-model/media/export/.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "export"
OUT.mkdir(exist_ok=True)
MODEL = json.loads((ROOT / "marketing/business-model/model/unit-economics.json").read_text())

sys.dont_write_bytecode = True  # keep marketing/media free of __pycache__
_spec = importlib.util.spec_from_file_location("launch_render", ROOT / "marketing/media/render.py")
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)
font, txt, wrap, rr, shadow_card, wordmark, mascot, paste_cover = (
    L.font, L.txt, L.wrap, L.rr, L.shadow_card, L.wordmark, L.mascot, L.paste_cover
)
CREAM, PAPER, INK, MUTED, TOMATO, TEAL_DARK, PASTA, SAGE, LINE = (
    L.CREAM, L.PAPER, L.INK, L.MUTED, L.TOMATO, L.TEAL_DARK, L.PASTA, L.SAGE, L.LINE
)
# Chart marks: tomato + a more saturated teal that passes the categorical palette
# checks on PAPER (lightness band, chroma, CVD and normal-vision separation).
MARK_A, MARK_B, MARK_NEUTRAL, GRID = TOMATO, "#00968F", "#C9C1B2", "#ECE5D6"
PHOTO, PASTA_IMG = ROOT / "landing/public/photos", ROOT / "landing/public/pasta"
W, H = 1270, 760


def save(canvas, name):
    canvas.convert("RGB").save(OUT / name, quality=94, subsampling=0)


def tag(d, right, y, label, fill=INK, ink=PAPER):
    w = int(font(15).getlength(label)) + 26
    rr(d, (right - w, y, right, y + 33), 12, fill)
    txt(d, (right - w + 13, y + 6), label, 15, ink)


def pasta(canvas, name, xy, width):
    im = Image.open(PASTA_IMG / f"{name}.png").convert("RGBA")
    im.thumbnail((width, width), Image.Resampling.LANCZOS)
    canvas.alpha_composite(im, xy)


def check(d, x, y, color=MARK_B):
    d.ellipse((x, y, x + 20, y + 20), fill=color)
    d.line((x + 5, y + 10, x + 9, y + 14, x + 15, y + 6), fill=PAPER, width=3, joint="curve")


def bullet_list(d, x, y, items, width, size=19, gap=12, color=MARK_B):
    for item in items:
        text = wrap(item, width - 32, size)
        check(d, x, y + 3, color)
        txt(d, (x + 32, y), text, size, INK, spacing=5)
        y += (text.count("\n") + 1) * (size + 6) + gap
    return y


# --- Promotion -------------------------------------------------------------------


def pricing_tiers():
    c = Image.new("RGBA", (W, H), CREAM)
    d = ImageDraw.Draw(c)
    d.ellipse((930, -260, 1480, 250), fill="#FFE8C1")
    wordmark(c)
    tag(d, 1205, 37, "PROPOSED PRICING · NOT YET LIVE")
    txt(d, (65, 118), "Free to start. Plus when you’re hooked.", 50, INK, True)
    txt(d, (67, 184), "Every day can become a lesson. Upgrade when one a day stops being enough.", 22, MUTED)

    cards = [
        ("Free", "$0", "forever", SAGE, [
            "1 photo lesson a day",
            "1 journal page a day",
            "Curated scenes to replay",
            "Word cards, I-Spy, sentences",
            "Streaks and XP",
        ], MARK_B),
        ("Plus", "$4.17", "/mo billed $49.99 yearly · or $7.99 monthly", "#FFF2D6", [
            "Up to 10 photo lessons a day",
            "Pronunciation feedback",
            "Review words that haven’t stuck",
            "10 photos per journal page",
            "Journal PDF keepsake",
        ], TOMATO),
        ("Founding Plus", "$34.99", "/yr, locked while you stay · first 300", PAPER, [
            "Everything in Plus",
            "Beta of competitive I-Spy",
            "Vote on what we build next",
            "Monthly call with the makers",
        ], PASTA),
    ]
    x = 65
    for i, (name, price, per, fill, items, dot) in enumerate(cards):
        box = (x, 240, x + 364, 690)
        shadow_card(c, box, 26, fill=fill)
        d = ImageDraw.Draw(c)
        if i == 1:
            rr(d, (x + 26, 223, x + 170, 257), 14, INK)
            txt(d, (x + 40, 230), "MOST POPULAR", 15, PAPER)
            pasta(c, "farfalle", (x + 282, 262), 64)
            d = ImageDraw.Draw(c)
        if i == 2:
            rr(d, (x + 26, 223, x + 148, 257), 14, TOMATO)
            txt(d, (x + 40, 230), "BETA CLUB", 15, PAPER)
        txt(d, (x + 26, 262), name, 30, INK, True)
        txt(d, (x + 26, 305), price, 50, INK, True)
        txt(d, (x + 26, 372), wrap(per, 310, 16), 16, MUTED, spacing=4)
        d.line((x + 26, 420, x + 338, 420), fill=LINE, width=2)
        bullet_list(d, x + 26, 440, items, 320, 19, 11, dot)
        x += 388
    L.foot(d, 1)
    d.rectangle((1100, 718, 1210, 745), fill=CREAM)
    txt(d, (1204, 722), "PRICING", 15, MUTED, anchor="ra")
    save(c, "pricing-tiers.png")


def founding_square():
    c = Image.new("RGBA", (1080, 1080), CREAM)
    d = ImageDraw.Draw(c)
    d.ellipse((600, -180, 1320, 540), fill="#FFE8C1")
    wordmark(c, 76, 65, 83)
    rr(d, (78, 190, 380, 232), 18, SAGE)
    txt(d, (98, 197), "FOUNDING PLUS · 300 SPOTS", 21, TEAL_DARK)
    txt(d, (74, 258), "Help build the\nlanguage game\nof your day.", 80, INK, True, spacing=0)
    txt(d, (80, 560), wrap("$34.99 a year, locked for as long as you stay. Play competitive I-Spy first and vote on what ships next.", 520, 27), 27, MUTED, spacing=9)
    shadow_card(c, (632, 470, 1004, 862), 28)
    paste_cover(c, PHOTO / "cafe-interior.jpg", (648, 486, 988, 752), 16)
    d = ImageDraw.Draw(c)
    txt(d, (664, 768), "Veo, veo… un sofá", 24, INK, True)
    txt(d, (664, 802), "de cuero marrón.", 24, INK, True)
    mascot(c, 880, 900, 120)
    d = ImageDraw.Draw(c)
    rr(d, (78, 770, 470, 836), 20, TOMATO)
    txt(d, (104, 783), "Become a founding member", 27, PAPER)
    txt(d, (80, 880), wrap("Proposed offer for launch. Opens only when Plus checkout works end to end.", 520, 19), 19, MUTED, spacing=6)
    txt(d, (79, 1022), "linguini-landing.vercel.app", 21, TEAL_DARK)
    save(c, "founding-plus-square.png")


def founding_story():
    c = Image.new("RGBA", (1080, 1920), CREAM)
    d = ImageDraw.Draw(c)
    d.ellipse((520, -260, 1400, 620), fill="#FFE8C1")
    d.ellipse((-300, 1500, 500, 2300), fill="#FBE9C8")
    wordmark(c, 80, 120, 90)
    rr(d, (82, 270, 470, 322), 22, SAGE)
    txt(d, (106, 280), "FOUNDING PLUS · 300 SPOTS", 25, TEAL_DARK)
    txt(d, (76, 360), "Your photos.\nYour words.\nYour vote.", 104, INK, True, spacing=0)
    shadow_card(c, (80, 780, 1000, 1330), 34)
    paste_cover(c, PHOTO / "paris-rooftops.jpg", (100, 800, 980, 1200), 20)
    d = ImageDraw.Draw(c)
    for x, y, label in ((130, 1110, "la gargouille"), (660, 872, "la tour Eiffel"), (770, 1070, "le pont")):
        w = int(font(26).getlength(label)) + 46
        rr(d, (x, y, x + w, y + 52), 20, PAPER)
        d.ellipse((x + 15, y + 20, x + 27, y + 32), fill=TOMATO)
        txt(d, (x + 35, y + 9), label, 26, INK)
    txt(d, (110, 1230), "Paris rooftops · 3 words · French", 30, INK, True)
    y = 1400
    for line in ("$34.99/yr, locked while you stay", "First into competitive I-Spy", "Vote on what we build next"):
        check(d, 92, y + 8, MARK_B)
        txt(d, (130, y), line, 36, INK)
        y += 70
    rr(d, (80, 1640, 1000, 1740), 30, TOMATO)
    txt(d, (540, 1666), "Become a founding member", 40, PAPER, anchor="ma")
    txt(d, (540, 1790), "Proposed offer · opens with Plus checkout", 24, MUTED, anchor="ma")
    mascot(c, 860, 1470, 130)
    save(c, "founding-plus-story.png")


# --- Charts ------------------------------------------------------------------------


def chart_frame(title, subtitle, source):
    c = Image.new("RGBA", (W, H), PAPER)
    d = ImageDraw.Draw(c)
    txt(d, (60, 44), title, 34, INK, True)
    txt(d, (62, 96), subtitle, 20, MUTED)
    txt(d, (62, 712), source, 14, MUTED)
    return c, d


def hbar(d, x0, y, length, thickness, color):
    """Horizontal bar: square at the baseline, 4px rounded data end."""
    if length <= 0:
        return
    r = min(4, length / 2)
    d.rounded_rectangle((x0, y, x0 + length, y + thickness), radius=r, fill=color)
    d.rectangle((x0, y, x0 + min(r, length), y + thickness), fill=color)


def chart_competitors():
    rows = [
        ("CapWords Premium (photo vocab)", 19.99, 29.99, False),
        ("Linguini Founding Plus (proposed)", 34.99, None, True),
        ("Linguini Plus (proposed)", 49.99, None, True),
        ("Linguini Plus (current landing)", 59.88, None, True),
        ("Speak Premium", 83.99, None, False),
        ("Super Duolingo", 83.99, 95.99, False),
        ("Babbel (12 months)", 107.64, None, False),
        ("Speak Premium Plus", 164.99, None, False),
        ("Duolingo Max", 168.00, None, False),
    ]
    c, d = chart_frame(
        "Annual price, US list",
        "Linguini sits above photo-flashcard apps and below curriculum and AI-tutor apps",
        "Sources: App Store (CapWords), dealnews (Duolingo, Babbel, May–Jul 2026), speakshark (Speak, Sep 2026). "
        "Median: RevenueCat SOSA 2026.",
    )
    x0, x1, top, band = 430, 1150, 178, 55
    scale = (x1 - x0) / 180
    for v in (0, 50, 100, 150):
        x = x0 + v * scale
        d.line((x, top - 8, x, top + band * len(rows)), fill=GRID, width=1)
        txt(d, (x, top + band * len(rows) + 8), f"${v}", 15, MUTED, anchor="ma")
    median = x0 + 44.99 * scale
    for y in range(top - 14, top + band * len(rows), 10):
        d.line((median, y, median, y + 5), fill=INK, width=1)
    txt(d, (median + 6, top - 30), "Education median $44.99", 15, INK)
    for i, (name, low, high, ours) in enumerate(rows):
        y = top + i * band + 12
        color = MARK_A if ours else MARK_NEUTRAL
        txt(d, (x0 - 16, y + 1), name, 18, INK if ours else MUTED, anchor="ra")
        hbar(d, x0, y, (high or low) * scale, 24, color)
        if high:
            d.rectangle((x0 + low * scale, y, x0 + low * scale + 2, y + 24), fill=PAPER)
        label = f"${low:.2f}–{high:.2f}" if high else f"${low:.2f}"
        txt(d, (x0 + (high or low) * scale + 10, y + 1), label, 17, INK)
    save(c, "chart-competitor-prices.png")


def chart_session_cost():
    b = MODEL["breakdown"]
    rows = [
        ("Chosen models", "chosen"),
        ("First alternatives", "fallback"),
        ("Cheapest alternatives (lower quality)", "budget"),
    ]
    c, d = chart_frame(
        "AI cost of one own-photo lesson",
        "Scene analysis and learning tasks are almost all of the cost",
        "Model: marketing/business-model/model/cost_model.py · measured tokens, 10% retry allowance · "
        "OpenRouter catalogue prices (MODEL_COMPARISON.md)",
    )
    x0, x1, top, band = 470, 1130, 190, 130
    maxv = 0.025
    scale = (x1 - x0) / maxv
    scene_key, tasks_key = "Scene analysis (vision)", "Learning tasks"
    series = (("Scene analysis (vision)", MARK_A), ("Learning tasks", MARK_B), ("Translation and I-Spy", MARK_NEUTRAL))
    lx = 470
    for label, color in series:
        rr(d, (lx, 142, lx + 16, 158), 4, color)
        txt(d, (lx + 24, 137), label, 17, INK)
        lx += 24 + int(font(17).getlength(label)) + 40
    for v in (0, 0.005, 0.01, 0.015, 0.02, 0.025):
        x = x0 + v * scale
        d.line((x, top - 10, x, top + band * len(rows) - 30), fill=GRID, width=1)
        txt(d, (x, top + band * len(rows) - 22), f"${v:.3f}", 15, MUTED, anchor="ma")
    for i, (name, key) in enumerate(rows):
        y = top + i * band + 20
        scene = b[key][scene_key]
        tasks = b[key][tasks_key]
        rest = sum(v for k, v in b[key].items() if k not in (scene_key, tasks_key))
        txt(d, (x0 - 18, y + 2), wrap(name, 380, 19), 19, INK, anchor="ra" if "\n" not in wrap(name, 380, 19) else None)
        x = x0
        for j, (value, color) in enumerate(((scene, MARK_A), (tasks, MARK_B), (rest, MARK_NEUTRAL))):
            start = x + (2 if j else 0)
            hbar(d, start, y, value * scale - (2 if j else 0), 24, color)
            if j:  # square the join so only the data end is rounded
                d.rectangle((start, y, start + 4, y + 24), fill=color)
            x += value * scale
            if j < 2:
                d.rectangle((x, y, x + 2, y + 24), fill=PAPER)
        total = scene + tasks + rest
        txt(d, (x0 + total * scale + 12, y + 1), f"${total:.4f}", 19, INK, True)
        txt(d, (x0, y + 34), f"scene analysis {scene / total:.0%}, learning tasks {tasks / total:.0%} of the lesson", 15, MUTED)
    save(c, "chart-session-cost.png")


def chart_breakeven():
    be = MODEL["breakeven_conversion"]
    key = "B · Recommended ($7.99 / $49.99)"
    rows = [
        ("Chosen models", be["chosen"][key]),
        ("First alternatives", be["fallback"][key]),
        ("Cheapest alternatives (lower quality)", be["budget"][key]),
    ]
    c, d = chart_frame(
        "Paid share of monthly users needed to cover AI cost",
        "With 1 free photo lesson a day, the chosen models need above-median conversion",
        "Model: cost_model.py (free-user mix 50/35/15% light/casual/at cap). Benchmarks: RevenueCat SOSA 2026 "
        "education; Duolingo Q2 2026 letter.",
    )
    x0, x1, top, band = 470, 1150, 200, 120
    scale = (x1 - x0) / 0.10
    for v in (0, 0.02, 0.04, 0.06, 0.08, 0.10):
        x = x0 + v * scale
        d.line((x, top - 30, x, top + band * len(rows) - 20), fill=GRID, width=1)
        txt(d, (x, top + band * len(rows) - 12), f"{v:.0%}", 15, MUTED, anchor="ma")
    for value, label, dy in ((0.023, "Education median, download to paid: 2.3%", -62), (0.09, "Duolingo paid share of MAU ≈9%", -62)):
        x = x0 + value * scale
        for y in range(top - 40, top + band * len(rows) - 20, 10):
            d.line((x, y, x, y + 5), fill=INK, width=1)
        txt(d, (x, top + dy), label, 15, INK, anchor="ma" if value > 0.05 else "la")
    for i, (name, value) in enumerate(rows):
        y = top + i * band + 10
        txt(d, (x0 - 18, y + 1), name, 19, INK, anchor="ra")
        hbar(d, x0, y, value * scale, 24, MARK_A if value > 0.0235 else MARK_B)
        txt(d, (x0 + value * scale + 12, y), f"{value:.1%}", 20, INK, True)
    note = "Tomato: needs better-than-median conversion.  Teal: at or below the median."
    txt(d, (x0, top + band * len(rows) + 22), note, 16, MUTED)
    save(c, "chart-breakeven-conversion.png")


if __name__ == "__main__":
    pricing_tiers(); founding_square(); founding_story()
    chart_competitors(); chart_session_cost(); chart_breakeven()
    for path in sorted(OUT.glob("*.png")):
        print(f"{path.name}: {path.stat().st_size / 1024:.0f} KiB")

"""Render the feature posters, the animated showcase and the click-through tour.

Run from any directory with: python3 marketing/feature-posters/build.py [--inline PATH]
Requires Pillow and FFmpeg. Reads phone captures from docs/screenshots/features/ and the
feature list from features.json, and writes everything to marketing/feature-posters/export/.
`--inline PATH` additionally writes a single self-contained tour (images embedded) to PATH.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "media"))

from render import (  # noqa: E402
    CREAM, FONTS, INK, LINE, MUTED, PAPER, ROOT, SAGE, TEAL_DARK, TOMATO,
    font, mascot, rr, shadow_card, txt, wordmark, wrap,
)

SHOTS = ROOT / "docs/screenshots/features"
OUT = HERE / "export"
POSTERS = OUT / "posters"
PW, PH = 1080, 1350
SECONDS_PER_POSTER = 2.6
FADE_SECONDS = 0.4
FPS = 25


def load_features():
    data = json.loads((HERE / "features.json").read_text())
    for feature in data:
        for shot in feature["shots"]:
            if not (SHOTS / shot["file"]).exists():
                raise SystemExit(f"missing screenshot: docs/screenshots/features/{shot['file']}")
    return data


def phone(canvas, path, x, y, width):
    """Paste a capture inside a rounded phone card with a soft shadow."""
    im = Image.open(path).convert("RGBA")
    height = round(im.height * width / im.width)
    im = im.resize((width, height), Image.Resampling.LANCZOS)
    pad, radius = max(8, width // 40), max(22, width // 13)
    shadow_card(canvas, (x - pad, y - pad, x + width + pad, y + height + pad), radius + pad, fill=INK, blur=26, dy=14)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width, height), radius=radius, fill=255)
    canvas.paste(im, (x, y), mask)
    return height


def poster(feature, index, total):
    c = Image.new("RGBA", (PW, PH), CREAM)
    d = ImageDraw.Draw(c)
    d.ellipse((760, -260, 1380, 360), fill="#FFE8C1")
    d.ellipse((-260, 980, 300, 1540), fill="#FBE9C8")
    wordmark(c, 64, 52, 58)
    label = feature["eyebrow"].upper()
    w = int(font(19).getlength(label)) + 34
    rr(d, (PW - 64 - w, 58, PW - 64, 98), 20, SAGE)
    txt(d, (PW - 64 - w / 2, 78), label, 19, TEAL_DARK, anchor="mm")
    title = wrap(feature["title"], PW - 128, 64, True)
    txt(d, (64, 140), title, 64, INK, True, spacing=0)
    title_h = d.multiline_textbbox((64, 140), title, font=font(64, True), spacing=0)[3]
    caption = wrap(feature["caption"], PW - 128, 28)
    txt(d, (64, title_h + 18), caption, 28, MUTED, spacing=10)
    top = d.multiline_textbbox((64, title_h + 18), caption, font=font(28), spacing=10)[3] + 46

    picks = feature.get("poster")
    shots = [s for s in feature["shots"] if s["file"] in picks] if picks else feature["shots"][:3]
    n = len(shots)
    avail_h = PH - 110 - top
    gap = 44
    width = min(int((PW - 128 - gap * (n - 1)) / n), int(avail_h * 440 / 900), 470)
    total_w = width * n + gap * (n - 1)
    top += max(0, (avail_h - round(width * 900 / 440)) // 2 - 10)
    x = (PW - total_w) // 2
    for i, shot in enumerate(shots):
        h = phone(c, SHOTS / shot["file"], x + i * (width + gap), top, width)
        if n > 1 and shot.get("label"):
            lab = shot["label"]
            lw = int(font(20).getlength(lab)) + 30
            cx = x + i * (width + gap) + width // 2
            ly = top + h - 26
            rr(d, (cx - lw // 2, ly, cx + lw // 2, ly + 40), 20, TOMATO)
            txt(d, (cx, ly + 20), lab, 20, "#FFFFFF", anchor="mm")
    d.line((64, PH - 70, PW - 64, PH - 70), fill=LINE, width=2)
    txt(d, (64, PH - 56), "LINGUINI · LEARN THE LANGUAGE OF YOUR DAY", 17, MUTED)
    txt(d, (PW - 64, PH - 56), f"{index:02d} / {total:02d}", 17, MUTED, anchor="ra")
    return c.convert("RGB")


def cover(features):
    c = Image.new("RGBA", (PW, PH), CREAM)
    d = ImageDraw.Draw(c)
    d.ellipse((620, -300, 1400, 480), fill="#FFE8C1")
    wordmark(c, 64, 60, 76)
    txt(d, (64, 170), "Every feature,\none photo at a time.", 76, INK, True, spacing=0)
    txt(d, (66, 360), wrap(f"A tour of {len(features)} features captured from the running app: "
                           "snap a scene, learn its words, play I-Spy and keep a journal.", 900, 30), 30, MUTED, spacing=10)
    mascot(c, PW - 64 - 170, 170, 170)
    cols, cell_w, gap = 4, 220, 26
    thumbs = [f["shots"][0]["file"] for f in features][:12]
    y0 = 520
    for i, name in enumerate(thumbs):
        row, col = divmod(i, cols)
        x = 64 + col * (cell_w + gap) + (PW - 128 - cols * cell_w - (cols - 1) * gap) // 2
        im = Image.open(SHOTS / name).convert("RGBA")
        im = im.resize((cell_w, round(im.height * cell_w / im.width)), Image.Resampling.LANCZOS)
        crop_h = 236
        im = im.crop((0, 0, cell_w, crop_h))
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, cell_w, crop_h), radius=20, fill=255)
        y = y0 + row * (crop_h + gap)
        shadow_card(c, (x, y, x + cell_w, y + crop_h), 20, fill=PAPER, blur=14, dy=8)
        c.paste(im, (x, y), mask)
    d.line((64, PH - 70, PW - 64, PH - 70), fill=LINE, width=2)
    txt(d, (64, PH - 56), "LINGUINI · LEARN THE LANGUAGE OF YOUR DAY", 17, MUTED)
    txt(d, (PW - 64, PH - 56), "learnwithlinguini.com", 17, TOMATO, anchor="ra")
    return c.convert("RGB")


def overview(features):
    """One tall contact sheet with every capture, grouped by feature."""
    cols, cell, gap, pad = 6, 260, 28, 64
    blocks = []
    for f in features:
        rows = -(-len(f["shots"]) // cols)
        blocks.append((f, rows))
    cell_h = round(cell * 900 / 440)
    height = 260 + sum(90 + rows * (cell_h + gap + 34) for _, rows in blocks) + 40
    width = pad * 2 + cols * cell + (cols - 1) * gap
    c = Image.new("RGBA", (width, height), CREAM)
    d = ImageDraw.Draw(c)
    wordmark(c, pad, 60, 70)
    txt(d, (pad, 150), "Linguini feature map", 54, INK, True)
    y = 260
    for f, rows in blocks:
        txt(d, (pad, y + 20), f"{f['title']}", 36, INK, True)
        txt(d, (width - pad, y + 34), f["route"], 22, MUTED, anchor="ra")
        y += 90
        for i, shot in enumerate(f["shots"]):
            row, col = divmod(i, cols)
            x = pad + col * (cell + gap)
            yy = y + row * (cell_h + gap + 34)
            phone(c, SHOTS / shot["file"], x, yy, cell)
            txt(d, (x + cell // 2, yy + cell_h + 22), shot.get("label", ""), 18, MUTED, anchor="mm")
        y += rows * (cell_h + gap + 34)
    return c.convert("RGB")


def showcase(frames):
    """Cross-fade the posters into an MP4 and a half-size animated WebP."""
    hold = round(SECONDS_PER_POSTER * FPS)
    fade = round(FADE_SECONDS * FPS)
    with tempfile.TemporaryDirectory() as tmp:
        n = 0
        for i, frame in enumerate(frames):
            nxt = frames[(i + 1) % len(frames)]
            for _ in range(hold):
                frame.save(f"{tmp}/{n:05d}.png")
                n += 1
            for k in range(1, fade + 1):
                Image.blend(frame, nxt, k / (fade + 1)).save(f"{tmp}/{n:05d}.png")
                n += 1
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{tmp}/%05d.png",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart",
            str(OUT / "feature-showcase.mp4"),
        ], check=True)
    small = [f.resize((540, 675), Image.Resampling.LANCZOS) for f in frames]
    small[0].save(OUT / "feature-showcase.webp", save_all=True, append_images=small[1:],
                  duration=int(SECONDS_PER_POSTER * 1000), loop=0, quality=82, method=4)


def tour_html(features, src):
    """Click/scroll/keyboard tour. `src(path)` maps a file to its <img> URL."""
    nav, slides = [], []
    for i, f in enumerate(features):
        fid = html.escape(f["id"])
        nav.append(f'<a href="#{fid}" data-i="{i}">{html.escape(f["title"])}</a>')
        figs = "".join(
            f'<figure><img loading="lazy" src="{src(SHOTS / s["file"])}" alt="{html.escape(f["title"] + " — " + s.get("label", ""))}" width="440" height="900">'
            f'<figcaption>{html.escape(s.get("label", ""))}</figcaption></figure>'
            for s in f["shots"]
        )
        slides.append(
            f'<section id="{fid}" class="slide"><header><p class="eyebrow">{html.escape(f["eyebrow"])}'
            f' · <code>{html.escape(f["route"])}</code></p><h2>{html.escape(f["title"])}</h2>'
            f'<p>{html.escape(f["caption"])}</p></header><div class="shots">{figs}</div></section>'
        )
    return TEMPLATE.replace("{{NAV}}", "".join(nav)).replace("{{SLIDES}}", "".join(slides)).replace(
        "{{COUNT}}", str(len(features))).replace("{{SHOWCASE}}", src(OUT / "feature-showcase.webp")).replace(
        "{{FONT_DISPLAY}}", src(FONTS / "Baloo2-ExtraBold.ttf")).replace("{{FONT_BODY}}", src(FONTS / "NunitoSans-Bold.ttf"))


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Linguini · feature tour</title>
<style>
@font-face{font-family:"Baloo 2";font-weight:800;src:url("{{FONT_DISPLAY}}") format("truetype")}
@font-face{font-family:"Nunito Sans";font-weight:400 800;src:url("{{FONT_BODY}}") format("truetype")}
:root{--cream:#FBF8EF;--paper:#FFFDF8;--ink:#263238;--muted:#5D6C70;--tomato:#EF5B32;--teal:#21716F;--sage:#DCEBDD;--line:#E4DCCB}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--cream);color:var(--ink);font:16px/1.5 "Nunito Sans",system-ui,sans-serif;display:grid;grid-template-columns:260px 1fr;min-height:100vh}
nav{position:sticky;top:0;height:100vh;overflow:auto;padding:28px 18px;border-right:1px solid var(--line);background:var(--paper)}
nav h1{font:800 26px/1.1 "Baloo 2",system-ui;margin:0 0 6px;color:var(--tomato)}nav p{margin:0 0 18px;color:var(--muted);font-size:14px}
nav a{display:block;padding:7px 10px;border-radius:10px;color:var(--ink);text-decoration:none;font-size:14px}
nav a:hover{background:var(--sage)}nav a.on{background:var(--tomato);color:#fff}
main{padding:0 36px;min-width:0}.hero>div{min-width:0}
.slide{min-height:100vh;padding:48px 0;scroll-margin-top:0;border-bottom:1px solid var(--line)}
.eyebrow{display:inline-block;background:var(--sage);color:var(--teal);border-radius:999px;padding:3px 12px;font-size:13px;font-weight:700;margin:0}
.eyebrow code{font-size:12px}
h2{font:800 40px/1.1 "Baloo 2",system-ui;margin:12px 0 6px}.slide header p:last-child{color:var(--muted);max-width:720px;margin:0 0 24px}
.shots{display:flex;gap:24px;overflow-x:auto;padding:8px 4px 20px;scroll-snap-type:x mandatory}
figure{margin:0;flex:0 0 auto;scroll-snap-align:start;text-align:center}
figure img{width:300px;height:auto;border-radius:26px;border:6px solid var(--ink);box-shadow:0 14px 30px rgba(64,52,33,.18);cursor:zoom-in;display:block;background:#fff}
figcaption{font-size:13px;color:var(--muted);margin-top:8px;max-width:300px}
.controls{position:fixed;right:24px;bottom:24px;display:flex;gap:8px}
.controls button{border:0;border-radius:999px;background:var(--tomato);color:#fff;font:700 15px system-ui;padding:12px 18px;cursor:pointer;box-shadow:0 6px 14px rgba(239,91,50,.3)}
.hero{display:flex;gap:32px;align-items:center;padding:40px 0;border-bottom:1px solid var(--line)}
.hero img{width:270px;border-radius:18px;box-shadow:0 10px 24px rgba(64,52,33,.18)}
#zoom{position:fixed;inset:0;background:rgba(38,50,56,.85);display:none;align-items:center;justify-content:center;z-index:9;cursor:zoom-out}
#zoom img{max-height:94vh;max-width:94vw;border-radius:24px}
@media (max-width:800px){body{grid-template-columns:1fr}nav{position:static;height:auto}main{padding:0 16px}figure img{width:240px}.hero{flex-direction:column}}
</style></head><body>
<nav><h1>Linguini</h1><p>{{COUNT}} features, captured from the running app. Use ← → or the buttons; click a screen to zoom.</p>{{NAV}}</nav>
<main><div class="hero"><img src="{{SHOWCASE}}" alt="Animated feature showcase"><div><h2>Every feature, one photo at a time.</h2>
<p>Snap a scene, learn its words, practise real missions, play I-Spy with friends and keep a journal. Scroll down or jump to a feature.</p></div></div>
{{SLIDES}}</main>
<div class="controls"><button id="prev" aria-label="Previous feature">← Prev</button><button id="next" aria-label="Next feature">Next →</button></div>
<div id="zoom" role="dialog" aria-label="Zoomed screenshot"><img alt=""></div>
<script>
const slides=[...document.querySelectorAll('.slide')],links=[...document.querySelectorAll('nav a')];let cur=0;
const go=i=>{cur=Math.max(0,Math.min(slides.length-1,i));slides[cur].scrollIntoView({behavior:'smooth'})};
document.getElementById('prev').onclick=()=>go(cur-1);document.getElementById('next').onclick=()=>go(cur+1);
addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowDown'||e.key==='PageDown'){e.preventDefault();go(cur+1)}
if(e.key==='ArrowLeft'||e.key==='ArrowUp'||e.key==='PageUp'){e.preventDefault();go(cur-1)}if(e.key==='Escape')zoom.style.display='none'});
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){cur=slides.indexOf(e.target);links.forEach((l,j)=>l.classList.toggle('on',j===cur))}}),{threshold:.35});slides.forEach(s=>io.observe(s));
const zoom=document.getElementById('zoom');document.querySelectorAll('figure img').forEach(im=>im.onclick=()=>{zoom.querySelector('img').src=im.src;zoom.style.display='flex'});zoom.onclick=()=>zoom.style.display='none';
</script></body></html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inline", type=Path, help="also write a self-contained tour to this path")
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required")
    features = load_features()
    POSTERS.mkdir(parents=True, exist_ok=True)
    for old in POSTERS.glob("*.png"):
        old.unlink()
    frames = [cover(features)]
    frames[0].save(POSTERS / "00-cover.png", optimize=True)
    for i, f in enumerate(features, 1):
        im = poster(f, i, len(features))
        im.save(POSTERS / f"{i:02d}-{f['id']}.png", optimize=True)
        frames.append(im)
    overview(features).save(OUT / "feature-map.png", optimize=True)
    showcase(frames)
    rel = lambda p: Path(p).resolve().relative_to(ROOT).as_posix()  # noqa: E731
    up = "../" * len(OUT.relative_to(ROOT).parts)
    (OUT / "index.html").write_text(tour_html(features, lambda p: up + rel(p)))
    if args.inline:
        mime = {".png": "image/png", ".webp": "image/webp", ".ttf": "font/ttf"}
        def embed(p):
            return f"data:{mime[Path(p).suffix]};base64," + base64.b64encode(Path(p).read_bytes()).decode()
        args.inline.write_text(tour_html(features, embed))
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            print(f"{path.relative_to(OUT)}: {path.stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()

"""Generate standalone vector Linguini assets for Canva.

All output uses transparent backgrounds and scalable SVG geometry. The mascot
silhouette follows frontend/public/linguini-logo.svg; the six pasta characters
are redrawn from the STePS handout reference supplied by the team.
"""

from __future__ import annotations

import base64
from pathlib import Path


HERE = Path(__file__).resolve().parent
FONT = HERE.parents[1] / "videos" / "launch-film" / "assets" / "Baloo2-ExtraBold.ttf"


PALETTE = {
    "red": "#E84B16",
    "orange": "#F26A32",
    "amber": "#FFAE16",
    "yellow": "#FFD84A",
    "cream": "#FFF5D6",
    "mint": "#85BEA4",
    "mint_dark": "#559B83",
    "brown": "#B9533D",
    "ink": "#2D3336",
}


DEFS = f"""
<defs>
  <linearGradient id="gold" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#FFE36A"/>
    <stop offset="0.52" stop-color="{PALETTE['yellow']}"/>
    <stop offset="1" stop-color="{PALETTE['amber']}"/>
  </linearGradient>
  <linearGradient id="goldDeep" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#FFD458"/>
    <stop offset="1" stop-color="#F58B2D"/>
  </linearGradient>
  <linearGradient id="mint" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#A9D7B6"/>
    <stop offset="1" stop-color="{PALETTE['mint']}"/>
  </linearGradient>
  <linearGradient id="lens" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#4C4649"/>
    <stop offset="0.55" stop-color="#17181B"/>
    <stop offset="1" stop-color="#302A2E"/>
  </linearGradient>
  <filter id="softShadow" x="-30%" y="-30%" width="160%" height="170%">
    <feDropShadow dx="0" dy="12" stdDeviation="10" flood-color="#9B3E1E" flood-opacity="0.2"/>
  </filter>
</defs>
"""


def svg(body: str, *, viewbox: str = "0 0 640 640", title: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" role="img" aria-label="{title}">
  <title>{title}</title>
  {DEFS}
  {body}
</svg>
'''


def write(name: str, content: str) -> None:
    (HERE / name).write_text(content, encoding="utf-8", newline="\n")


def mascot_base(face: str, extras: str = "") -> str:
    return f'''
<g transform="translate(64 64)" filter="url(#softShadow)">
  <g stroke="{PALETTE['red']}" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="260" cy="243" r="156" fill="url(#gold)" stroke-width="16"/>
    <circle cx="260" cy="243" r="140" fill="none" stroke="{PALETTE['cream']}" stroke-width="13"/>
    <path d="M125 260c-27-108 51-201 159-189 104 11 170 109 135 207-28 78-111 125-190 101-42-13-75-44-92-82" fill="none" stroke-width="20"/>
    <path d="M124 259c-42-28-88 8-74 53 12 39 65 43 84 12 17-28-7-60-38-49" fill="none" stroke-width="16"/>
    <path d="M229 365c-41 27-77 62-101 105" fill="none" stroke-width="20"/>
    <path d="M128 470c-14 23 10 40 30 25l41-35" fill="none" stroke-width="20"/>
  </g>
  <path d="M145 150c28-48 78-75 132-73" fill="none" stroke="#FFF6D8" stroke-width="13" stroke-linecap="round" opacity=".8"/>
  {face}
  {extras}
</g>'''


HAPPY_FACE = f'''
<g fill="{PALETTE['red']}">
  <circle cx="210" cy="232" r="18"/>
  <circle cx="310" cy="232" r="18"/>
  <path d="M209 282c18 48 76 48 94 0v20c-23 39-71 39-94 0z"/>
</g>'''


LOVE_FACE = f'''
<g fill="{PALETTE['red']}" stroke="{PALETTE['red']}" stroke-linejoin="round">
  <path d="M183 222c0-20 27-26 34-6 8-20 35-14 35 6 0 21-35 42-35 42s-34-21-34-42z" stroke-width="4"/>
  <path d="M276 222c0-20 27-26 34-6 8-20 35-14 35 6 0 21-35 42-35 42s-34-21-34-42z" stroke-width="4"/>
  <path d="M211 292c19 38 69 38 89 0" fill="none" stroke-width="13" stroke-linecap="round"/>
</g>'''


LOVE_EXTRA = f'''
<g fill="{PALETTE['red']}" stroke="{PALETTE['red']}" stroke-width="4">
  <path d="M425 105c0-17 23-22 29-5 7-17 30-12 30 5 0 18-30 36-30 36s-29-18-29-36z"/>
  <path d="M470 154c0-10 14-14 18-3 4-11 19-7 19 3 0 12-19 23-19 23s-18-11-18-23z"/>
</g>'''


COOL_FACE = f'''
<g>
  <path d="M163 202c49-8 74-4 101 6 29-11 62-13 105-3l-8 55c-7 40-70 43-84 4l-9-25-9 25c-13 39-76 36-84-4z" fill="url(#lens)" stroke="{PALETTE['ink']}" stroke-width="13" stroke-linejoin="round"/>
  <path d="M162 202l-22-6M369 205l25-8" stroke="{PALETTE['ink']}" stroke-width="13" stroke-linecap="round"/>
  <path d="M189 214l39 2-37 30" fill="none" stroke="#F7A23B" stroke-width="10" stroke-linecap="round" opacity=".75"/>
  <path d="M296 214l40 3-37 30" fill="none" stroke="#F7A23B" stroke-width="10" stroke-linecap="round" opacity=".75"/>
  <path d="M214 295c18 35 66 35 87 0" fill="none" stroke="{PALETTE['red']}" stroke-width="13" stroke-linecap="round"/>
</g>'''


def make_wordmark() -> str:
    font_data = base64.b64encode(FONT.read_bytes()).decode("ascii")
    body = f'''
<defs>
  <style>
    @font-face {{ font-family: LinguiniBaloo; src: url(data:font/ttf;base64,{font_data}) format("truetype"); font-weight: 800; }}
  </style>
</defs>
<g fill="#FFAA00">
  <text x="28" y="172" font-family="LinguiniBaloo, sans-serif" font-size="166" font-weight="800" letter-spacing="-5">Linguini</text>
  <path d="M287 194c37 30 68 31 99 1 27-26 56-27 86-2 27 23 60 23 93-5" fill="none" stroke="#FFAA00" stroke-width="18" stroke-linecap="round"/>
</g>'''
    return svg(body, viewbox="0 0 620 230", title="Linguini wordmark")


def make_farfalle() -> str:
    body = f'''
<g filter="url(#softShadow)">
  <ellipse cx="320" cy="394" rx="232" ry="181" fill="url(#mint)" stroke="{PALETTE['mint_dark']}" stroke-width="15"/>
  <path d="M105 402c78 73 273 108 425 3" fill="none" stroke="#C7E3CC" stroke-width="14" stroke-linecap="round" opacity=".5"/>
  <g stroke="{PALETTE['orange']}" stroke-width="15" stroke-linejoin="round">
    <path d="M174 176c35 18 60 44 86 84l60-5c-3-54-24-100-65-137-14-12-29 6-39 0-11-7-14-29-31-20-12 7-7 28-18 33-12 6-28-9-37 5-9 14 25 23 44 40z" fill="url(#gold)"/>
    <path d="M466 176c-35 18-60 44-86 84l-60-5c3-54 24-100 65-137 14-12 29 6 39 0 11-7 14-29 31-20 12 7 7 28 18 33 12 6 28-9 37 5 9 14-25 23-44 40z" fill="url(#gold)"/>
    <path d="M260 260c-19 45-21 92-8 142 30-14 52-36 68-66 17 31 40 53 69 66 13-50 10-97-9-142-37-18-78-18-120 0z" fill="url(#goldDeep)"/>
  </g>
  <path d="M244 165l42 169M397 165l-43 169" stroke="#F6A43A" stroke-width="12" stroke-linecap="round" opacity=".65"/>
  <g fill="{PALETTE['brown']}"><circle cx="299" cy="291" r="10"/><circle cx="347" cy="291" r="10"/></g>
  <path d="M304 319c13 15 27 15 39 0" fill="none" stroke="{PALETTE['brown']}" stroke-width="10" stroke-linecap="round"/>
  <path d="M254 346c-20 4-37 18-48 41M388 346c18 6 33 19 43 39" fill="none" stroke="{PALETTE['orange']}" stroke-width="13" stroke-linecap="round"/>
  <circle cx="205" cy="391" r="20" fill="url(#gold)" stroke="{PALETTE['orange']}" stroke-width="11"/>
  <circle cx="433" cy="390" r="20" fill="url(#gold)" stroke="{PALETTE['orange']}" stroke-width="11"/>
</g>'''
    return svg(body, title="Farfalle pasta character")


def make_macaroni() -> str:
    body = f'''
<g filter="url(#softShadow)">
  <path d="M191 130c78-59 200-35 260 48 69 97 58 225-21 305-77 78-210 78-286-1-54-56-70-141-43-214 18-50 48-95 90-138z" fill="url(#goldDeep)" stroke="{PALETTE['orange']}" stroke-width="17"/>
  <path d="M209 133c55-37 117-42 174-14-50 15-91 51-117 103-29-20-57-49-57-89z" fill="#FFFDF2" stroke="{PALETTE['orange']}" stroke-width="15"/>
  <path d="M224 113c25-40 67-54 107-39 34 13 56 48 55 85-1 43-33 78-73 85-38 6-77-15-94-51" fill="url(#gold)" stroke="{PALETTE['orange']}" stroke-width="16"/>
  <path d="M252 102c29-19 68-7 78 25 9 30-11 60-41 65-27 4-51-15-55-39" fill="#FFFDF2" stroke="{PALETTE['orange']}" stroke-width="13"/>
  <path d="M144 313c-8 70 22 134 79 170" fill="none" stroke="#FFCB4A" stroke-width="14" stroke-linecap="round" opacity=".55"/>
  <circle cx="352" cy="290" r="11" fill="{PALETTE['brown']}"/><circle cx="401" cy="303" r="11" fill="{PALETTE['brown']}"/>
  <path d="M359 331c12 15 28 18 43 7" fill="none" stroke="{PALETTE['brown']}" stroke-width="10" stroke-linecap="round"/>
</g>'''
    return svg(body, title="Curved macaroni character")


def make_noodle_ball() -> str:
    loops = "".join(
        f'<path d="{d}" fill="none" stroke="#F7942D" stroke-width="17" stroke-linecap="round"/>'
        for d in [
            "M172 277c-42-58 32-121 88-82 33-64 132-41 130 33 70-20 108 64 61 111",
            "M153 343c-53-21-49-100 10-115 2-68 100-89 132-30 48-52 137-6 119 65",
            "M177 403c-66-17-64-110 2-127 1-69 100-93 137-36 46-45 125-1 107 61",
            "M210 449c-58-32-35-122 31-119 21-61 116-58 133 7 58-16 92 58 55 100",
            "M251 166c34-71 142-51 149 29 62 5 76 91 20 118",
            "M238 238c33-42 100-23 105 30 48 2 66 62 35 94",
        ]
    )
    body = f'''
<g filter="url(#softShadow)">
  <circle cx="320" cy="326" r="220" fill="url(#gold)" stroke="{PALETTE['orange']}" stroke-width="17"/>
  {loops}
  <circle cx="287" cy="345" r="11" fill="{PALETTE['brown']}"/><circle cx="354" cy="345" r="11" fill="{PALETTE['brown']}"/>
  <path d="M299 376c15 18 31 18 47 0" fill="none" stroke="{PALETTE['brown']}" stroke-width="11" stroke-linecap="round"/>
</g>'''
    return svg(body, title="Noodle ball character")


def make_rigatoni_family() -> str:
    tubes = []
    for x, y, w, h in [(112, 238, 122, 248), (245, 159, 150, 335), (409, 245, 119, 240)]:
        cx = x + w / 2
        tubes.append(f'''
<g>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="45" fill="url(#gold)" stroke="{PALETTE['orange']}" stroke-width="15"/>
  <ellipse cx="{cx}" cy="{y + 9}" rx="{w * .38}" ry="{w * .16}" fill="#FFB334" stroke="{PALETTE['orange']}" stroke-width="12"/>
  <ellipse cx="{cx}" cy="{y + 8}" rx="{w * .25}" ry="{w * .09}" fill="#FFE277"/>
  <path d="M{int(x+w*.25)} {int(y+58)}v{int(h-98)}M{int(x+w*.75)} {int(y+58)}v{int(h-98)}" stroke="#F5A035" stroke-width="9" stroke-linecap="round" opacity=".55"/>
  <circle cx="{cx-19}" cy="{y+h*.51}" r="9" fill="{PALETTE['brown']}"/><circle cx="{cx+19}" cy="{y+h*.51}" r="9" fill="{PALETTE['brown']}"/>
  <path d="M{cx-13} {y+h*.60}c9 12 19 12 28 0" fill="none" stroke="{PALETTE['brown']}" stroke-width="8" stroke-linecap="round"/>
</g>''')
    body = f'''
<g filter="url(#softShadow)">{''.join(tubes)}
  <path d="M112 381c-28 4-45 24-51 51M528 386c27 2 44 19 50 44" fill="none" stroke="{PALETTE['orange']}" stroke-width="13" stroke-linecap="round"/>
  <path d="M235 383c15 14 29 18 45 9M396 385c15 10 28 9 43-4" fill="none" stroke="{PALETTE['orange']}" stroke-width="12" stroke-linecap="round"/>
</g>'''
    return svg(body, title="Rigatoni pasta family")


def make_ravioli_flag() -> str:
    body = f'''
<g filter="url(#softShadow)">
  <path d="M143 330c0-118 78-209 180-209 103 0 185 88 185 209 0 100-69 181-185 181-114 0-180-79-180-181z" fill="url(#gold)" stroke="{PALETTE['orange']}" stroke-width="17"/>
  <path d="M165 278c35-60 89-95 158-104 72 5 125 37 159 96" fill="none" stroke="#FFE574" stroke-width="14" stroke-linecap="round" opacity=".7"/>
  <path d="M151 372c-42 3-76-30-75-72 1-38 26-68 63-74" fill="none" stroke="{PALETTE['orange']}" stroke-width="14" stroke-linecap="round"/>
  <path d="M82 223V86" stroke="{PALETTE['orange']}" stroke-width="15" stroke-linecap="round"/>
  <path d="M89 91c51-13 88 15 127 2v78c-44 13-78-15-127-2z" fill="#F35A37" stroke="{PALETTE['orange']}" stroke-width="10" stroke-linejoin="round"/>
  <circle cx="289" cy="319" r="11" fill="{PALETTE['brown']}"/><circle cx="358" cy="319" r="11" fill="{PALETTE['brown']}"/>
  <path d="M301 352c14 17 31 17 45 0" fill="none" stroke="{PALETTE['brown']}" stroke-width="11" stroke-linecap="round"/>
  <path d="M461 376c30 4 48 25 53 56" fill="none" stroke="{PALETTE['orange']}" stroke-width="13" stroke-linecap="round"/>
</g>'''
    return svg(body, title="Ravioli character holding a flag")


def make_rigatoni_magnifier() -> str:
    body = f'''
<g filter="url(#softShadow)">
  <rect x="254" y="122" width="205" height="386" rx="67" fill="url(#gold)" stroke="{PALETTE['orange']}" stroke-width="17"/>
  <ellipse cx="356" cy="129" rx="77" ry="28" fill="#FFB334" stroke="{PALETTE['orange']}" stroke-width="14"/>
  <ellipse cx="356" cy="128" rx="53" ry="16" fill="#FFE277"/>
  <path d="M303 196v236M356 184v265M408 196v236" stroke="#F5A035" stroke-width="11" stroke-linecap="round" opacity=".55"/>
  <circle cx="333" cy="310" r="11" fill="{PALETTE['brown']}"/><circle cx="388" cy="310" r="11" fill="{PALETTE['brown']}"/>
  <path d="M344 344c13 16 28 16 42 0" fill="none" stroke="{PALETTE['brown']}" stroke-width="10" stroke-linecap="round"/>
  <path d="M447 367c32 5 51 27 55 59" fill="none" stroke="{PALETTE['orange']}" stroke-width="13" stroke-linecap="round"/>
  <circle cx="173" cy="235" r="80" fill="#FFF7DE" stroke="{PALETTE['orange']}" stroke-width="18"/>
  <circle cx="173" cy="235" r="56" fill="none" stroke="#FFE6A7" stroke-width="10"/>
  <path d="M221 295l76 104" stroke="{PALETTE['orange']}" stroke-width="28" stroke-linecap="round"/>
  <path d="M222 296l75 102" stroke="#F77B43" stroke-width="13" stroke-linecap="round"/>
</g>'''
    return svg(body, title="Rigatoni detective with magnifying glass")


def main() -> None:
    write("linguini-wordmark.svg", make_wordmark())
    write("01-linguini-happy.svg", svg(mascot_base(HAPPY_FACE), title="Happy Linguini mascot"))
    write("02-linguini-love.svg", svg(mascot_base(LOVE_FACE, LOVE_EXTRA), title="Linguini mascot with heart eyes"))
    write("03-linguini-cool.svg", svg(mascot_base(COOL_FACE), title="Linguini mascot wearing sunglasses"))
    write("04-farfalle-friend.svg", make_farfalle())
    write("05-macaroni-friend.svg", make_macaroni())
    write("06-noodle-ball-friend.svg", make_noodle_ball())
    write("07-rigatoni-family.svg", make_rigatoni_family())
    write("08-ravioli-flag.svg", make_ravioli_flag())
    write("09-rigatoni-magnifier.svg", make_rigatoni_magnifier())


if __name__ == "__main__":
    main()

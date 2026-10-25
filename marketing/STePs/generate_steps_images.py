"""Generate landscape promo images for the Linguini STePS project page.

Model: gpt-image-1.5 at high quality, 1536x1024 (3:2 landscape — suits the
STePS/uvents project page better than the 4:5 Instagram posters).

Reads OPENAI_API_KEY from the environment. Writes raw API output to raw/
and finished images to promo/. Prints file names only.
"""

import base64
import io
import sys
from pathlib import Path

from openai import OpenAI
from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
RAW = ROOT / "raw"
OUT = ROOT / "promo"

BRAND = REPO / "frontend" / "public" / "brand"
PHOTOS = REPO / "frontend" / "public" / "photos"
SHOTS = REPO / "docs" / "screenshots"

REFS = {
    "wordmark": BRAND / "linguini-wordmark.png",
    "mascot": BRAND / "mascot-180.png",
    "cafe": PHOTOS / "cafe-interior.jpg",
    "vocabulary": SHOTS / "vocabulary.png",
}

STYLE = """Palette: tomato #E85D32, pasta #F9B233, butter #FFF9ED, cream #FFF1D2, sage #DCEBDD, teal-dark #21716F, ink #263238.
Rounded, human typography inspired by Baloo 2 for the headline and Nunito Sans for labels.
Sunny, tactile, smart, playful but not childish. Premium student-built product campaign.
Crisp margins and type; no mock phone, no gradients, no neon, no green-led palette, no owl or feathers, no watermark, no competitor styling.
Do not add any words other than the exact text specified above and the supplied wordmark."""

IMAGES = [
    (
        "steps-poster",
        ["wordmark", "mascot", "cafe"],
        f"""Create a polished wide landscape promotional poster for the language-learning app Linguini, for a university project-showcase page (NUS STePS).

USE THE REFERENCES:
- Preserve the supplied Linguini wordmark faithfully as the brand mark near the top left.
- The supplied mascot may appear once, small and playful, peeking from behind a croissant on the table.
- Use the supplied cafe-interior photograph only as loose mood reference; compose an original scene.

SCENE: a wide morning cafe-table flatlay seen from above — a croissant on a small plate, a latte with heart foam, an open pocket notebook, a small film camera, scattered blank instant-photo frames, soft morning sunlight with long shadows.

LAYOUT (landscape, generous side margins):
- Warm butter paper background (#FFF9ED) with one large rounded photo window on the right holding the morning scene, restrained cream paper layers.
- On the left, stacked: a small tomato status pill "IN BETA", then a large, extremely legible headline "Your first lesson is already on the table."
- Small bottom label under the headline: "photo-led language lessons — CS3216, NUS"
- One looping pasta-yellow noodle path with tomato outline as a tasteful accent, never crossing text.

{STYLE}""",
    ),
    (
        "promo-photo-to-words",
        ["wordmark", "cafe"],
        f"""Create a second wide landscape promotional image for Linguini, visually cohesive with the same warm editorial campaign.

USE THE REFERENCES:
- Preserve the supplied Linguini wordmark faithfully as a small brand mark near the top left.
- Use the supplied cafe-interior photograph as loose mood reference; compose an original cafe-tabletop photo as the hero.

SCENE INSIDE THE PHOTO CARD: a bright cafe tabletop photographed at a slight angle, clearly showing a cup of coffee, a croissant on a plate, and a wooden table edge.

LAYOUT (landscape):
- Butter paper background (#FFF9ED), restrained cream paper layers.
- CRITICAL: keep every element fully inside the canvas with a wide empty margin on all four sides — nothing may touch, cross or leave the canvas edge.
- Left side: large, extremely legible headline "One photo." with a supporting line directly beneath it: "Linguini finds the words in it."
- Right side: the tabletop photo inside a white rounded photo card. On the photo, add exactly four clean white rounded vocabulary chips, each with a small tomato dot and dark ink text, placed near the matching object:
  "el café" near the coffee
  "la taza" near the cup
  "el croissant" near the croissant
  "la mesa" near the table edge
- One pasta-yellow noodle path guides the eye from the headline to the photo card.

{STYLE}""",
    ),
    (
        "promo-words-stay",
        ["wordmark", "mascot", "vocabulary"],
        f"""Create a third wide landscape promotional image for Linguini, visually cohesive with the same warm editorial campaign.

USE THE REFERENCES:
- Preserve the supplied Linguini wordmark faithfully as a small brand mark near the top left.
- The supplied mascot may appear once as a small supportive sticker near the card edge.
- Use the supplied app screenshot ONLY as a layout reference for the vocabulary card: a rounded white card with a photo on top, a card title with a word count on the right, then word rows each showing a Spanish word with a small grey English gloss beneath it. Do not copy the screenshot's photo, header bar, or navigation — draw the card clean.

HERO ELEMENT: the vocabulary card, showing a warm morning cafe-table photo on top, header "Morning café" with a small teal "4 words" label on the right, then four word rows. Each row shows the Spanish word with its small grey English gloss directly beneath it on the left, and a small grey speaker icon on the right — never repeat the gloss on the right side:
  "el croissant" / "the croissant"
  "la cámara" / "the camera"
  "el café" / "the coffee"
  "el cuaderno" / "the notebook"
A second, similar vocabulary card peeks from behind and below, photo visible but words illegible — suggesting more saved photo lessons.

LAYOUT (landscape):
- Butter paper background (#FFF9ED), restrained cream and sage paper layers, generous margins.
- Left side: large, extremely legible headline "Every photo keeps its words." with a supporting line beneath it: "Revisit any photo. Keep every word."
- Right side: the stacked vocabulary cards.
- One small farfalle pasta shape as a quiet accent near the supporting line.

{STYLE}""",
    ),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    client = OpenAI()
    RAW.mkdir(parents=True, exist_ok=True)

    only = None
    for arg in sys.argv:
        if arg.startswith("--only="):
            only = arg.split("=", 1)[1]

    failures = []
    for name, ref_keys, prompt in IMAGES:
        if only and not name.startswith(only):
            continue
        try:
            handles = [open(REFS[k], "rb") for k in ref_keys]
            try:
                result = client.images.edit(
                    model="gpt-image-1.5",
                    image=handles,
                    prompt=prompt,
                    size="1536x1024",
                    quality="high",
                )
            finally:
                for h in handles:
                    h.close()

            raw = Image.open(io.BytesIO(base64.b64decode(result.data[0].b64_json)))
            raw_path = RAW / f"{name}.png"
            raw.save(raw_path)

            out_path = OUT / f"{name}.png"
            raw.convert("RGB").save(out_path)
            print(f"wrote {out_path.relative_to(REPO)}", flush=True)
        except Exception as exc:
            failures.append((name, str(exc)[:300]))
            print(f"FAILED {name}: {str(exc)[:300]}", flush=True)

    if failures:
        print(f"{len(failures)} image(s) failed")
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())

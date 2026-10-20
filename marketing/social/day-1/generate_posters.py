"""Generate the Day-One Instagram poster set with the OpenAI Images API.

Model: gpt-image-1 at high quality, 1024x1536, then centre-cropped and
resized to 1080x1350 (Instagram 4:5 feed format) — the same post-processing
used for marketing/social/instagram.

Reads OPENAI_API_KEY from the environment. Writes raw API output to raw/
and finished posters to instagram/. Prints file names only.
"""

import base64
import io
import sys
from pathlib import Path

from openai import OpenAI
from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
RAW = ROOT / "raw"
OUT = ROOT / "instagram"

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

POSTERS = [
    (
        "01-day-one-morning",
        ["wordmark", "mascot", "cafe"],
        f"""Create a polished Instagram feed poster for the language-learning app Linguini, part of a "Day One" campaign following a learner's first day with the app.

USE THE REFERENCES:
- Preserve the supplied Linguini wordmark faithfully as the brand mark near the top.
- The supplied mascot may appear once, small and playful, peeking from behind a croissant on the table.
- Use the supplied cafe-interior photograph only as loose mood reference; compose an original scene.

SCENE: a warm morning cafe-table flatlay seen from above — a croissant on a small plate, a latte with heart foam, an open pocket notebook, a small film camera, scattered blank instant-photo frames, soft morning sunlight with long shadows.

LAYOUT:
- Warm butter paper background (#FFF9ED) with one large rounded photo window holding the morning scene, restrained cream paper layers.
- Small tomato status pill near the top: "DAY ONE"
- Large, extremely legible headline: "Your first lesson is already on the table."
- Small bottom label: "Spanish from everyday photos"
- One looping pasta-yellow noodle path with tomato outline as a tasteful accent, never crossing text.

{STYLE}""",
    ),
    (
        "02-one-photo",
        ["wordmark", "cafe"],
        f"""Create a second polished Instagram feed poster for Linguini, visually cohesive with the same warm editorial "Day One" campaign.

USE THE REFERENCES:
- Preserve the supplied Linguini wordmark faithfully as a small brand mark near the top.
- Use the supplied cafe-interior photograph as loose mood reference; compose an original cafe-tabletop photo as the hero.

SCENE INSIDE THE PHOTO CARD: a bright cafe tabletop photographed at a slight angle, clearly showing a cup of coffee, a croissant on a plate, and a wooden table edge.

LAYOUT:
- Butter paper background (#FFF9ED), restrained cream paper layers, generous margins.
- Large, extremely legible headline: "One photo."
- Supporting line directly beneath it: "Linguini finds the words in it."
- The tabletop photo sits inside a white rounded photo card. On the photo, add exactly four clean white rounded vocabulary chips, each with a small tomato dot and dark ink text, placed near the matching object:
  "el café" near the coffee
  "la taza" near the cup
  "el croissant" near the croissant
  "la mesa" near the table edge
- Small bottom label: "Your camera roll is the textbook"
- One pasta-yellow noodle path guides the eye from the headline to the photo card.

{STYLE}""",
    ),
    (
        "03-you-decide",
        ["wordmark", "mascot"],
        f"""Create a third polished Instagram feed poster for Linguini, visually cohesive with the same warm editorial "Day One" campaign.

USE THE REFERENCES:
- Preserve the supplied Linguini wordmark faithfully as a small brand mark near the top.
- The supplied mascot may appear once as a small supportive sticker holding a pencil, not as the main subject.

HERO ELEMENT: a cream paper review sheet with a soft shadow, titled by the headline. It lists six suggested objects as rows, each with a small circle checkbox on the left:
- Four rows carry a clean tomato check mark: "el café", "la taza", "el croissant", "la mesa"
- Two rows carry a muted grey cross: "el menú", "la silla"

LAYOUT:
- Butter paper background (#FFF9ED), restrained cream and sage paper layers, generous margins.
- Large, extremely legible headline above the sheet: "AI suggests. You decide."
- Small supporting line beneath the sheet: "Review what enters your lesson."
- One pasta-yellow noodle path loops beside the sheet as a tasteful accent, never crossing text.

{STYLE}""",
    ),
    (
        "04-i-spy",
        ["wordmark", "cafe"],
        f"""Create a fourth polished Instagram feed poster for Linguini, visually cohesive with the same warm editorial "Day One" campaign.

USE THE REFERENCES:
- Preserve the supplied Linguini wordmark faithfully as a small brand mark near the top.
- Use the supplied cafe-interior photograph as loose mood reference; compose an original cafe-tabletop photo similar in spirit to the second poster's scene.

LAYOUT:
- Butter paper background (#FFF9ED), restrained cream paper layers, generous margins.
- Large, extremely legible headline: "Play I-Spy with your world."
- Small supporting line: "Find the word. Then give the clue."
- Hero: the cafe-tabletop photo inside a white rounded photo card, with a small clean white clue card overlapping its lower edge. The clue card must read exactly: "Veo algo que empieza con C." — Spanish first person "Veo" (I see), never "Vea".
- Two small restrained speech-card accents floating near the photo card:
  "Linguini gives clues"
  "Then it's your turn"
- One pasta-yellow noodle path guides the eye between the two speech cards.

{STYLE}""",
    ),
    (
        "05-words-stay",
        ["wordmark", "mascot", "vocabulary"],
        f"""Create a fifth polished Instagram feed poster for Linguini, visually cohesive with the same warm editorial "Day One" campaign.

USE THE REFERENCES:
- Preserve the supplied Linguini wordmark faithfully as a small brand mark near the top.
- The supplied mascot may appear once as a small supportive sticker near the bottom card edge.
- Use the supplied app screenshot ONLY as a layout reference for the vocabulary card: a rounded white card with a photo on top, a card title with a word count on the right, then word rows each showing a Spanish word with a small grey English gloss beneath it. Do not copy the screenshot's photo, header bar, or navigation — draw the card clean.

HERO ELEMENT: the vocabulary card, showing a warm morning cafe-table photo on top, header "Morning café" with a small teal "5 words" label on the right, then five word rows:
  "el café" / "the coffee"
  "la taza" / "the cup"
  "el croissant" / "the croissant"
  "la mesa" / "the table"
  "la cuenta" / "the bill"
A second, similar vocabulary card peeks from behind and below, photo visible but words illegible — suggesting more saved photo lessons.

LAYOUT:
- Butter paper background (#FFF9ED), restrained cream and sage paper layers, generous margins.
- Large, extremely legible headline: "Every photo keeps its words."
- Small supporting line beneath the cards: "Revisit any photo. Keep every word."
- One small farfalle pasta shape as a quiet accent near the supporting line.

{STYLE}""",
    ),
]


def crop_to_feed(img: Image.Image) -> Image.Image:
    """Fit the whole poster inside 1080x1350 (4:5), padding with the
    poster's own background colour so no headline or label is clipped."""
    img = img.convert("RGB")
    bg = img.getpixel((6, 6))
    scale = min(1080 / img.width, 1350 / img.height)
    size = (round(img.width * scale), round(img.height * scale))
    img = img.resize(size, Image.LANCZOS)
    canvas = Image.new("RGB", (1080, 1350), bg)
    canvas.paste(img, ((1080 - size[0]) // 2, (1350 - size[1]) // 2))
    return canvas


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    if "--reprocess" in sys.argv:
        for raw_path in sorted(RAW.glob("*.png")):
            crop_to_feed(Image.open(raw_path)).save(OUT / raw_path.name)
            print(f"reprocessed {raw_path.name}", flush=True)
        return 0

    client = OpenAI()
    RAW.mkdir(parents=True, exist_ok=True)

    only = None
    for arg in sys.argv:
        if arg.startswith("--only="):
            only = arg.split("=", 1)[1]

    failures = []
    for name, ref_keys, prompt in POSTERS:
        if only and not name.startswith(only):
            continue
        try:
            handles = [open(REFS[k], "rb") for k in ref_keys]
            try:
                result = client.images.edit(
                    model="gpt-image-1",
                    image=handles,
                    prompt=prompt,
                    size="1024x1536",
                    quality="high",
                )
            finally:
                for h in handles:
                    h.close()

            raw = Image.open(io.BytesIO(base64.b64decode(result.data[0].b64_json)))
            raw_path = RAW / f"{name}.png"
            raw.save(raw_path)

            feed = crop_to_feed(raw)
            out_path = OUT / f"{name}.png"
            feed.save(out_path)
            print(f"wrote {out_path.relative_to(REPO)}", flush=True)
        except Exception as exc:
            failures.append((name, str(exc)[:300]))
            print(f"FAILED {name}: {str(exc)[:300]}", flush=True)

    if failures:
        print(f"{len(failures)} poster(s) failed")
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())

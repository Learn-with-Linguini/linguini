# STePS assets

Media for the Linguini project page at
https://uvents.nus.edu.sg/event/29th-steps/module/CS3216/project/3 (CS3216-03).

## GIFs (original motion graphics — NOT video clips; 960px, 15fps, ~6s loop)

Designed, animated promo posters in the style other STEPS projects use
(e.g. `reference/runsquad.gif`, `reference/artisan.gif` from the 23rd STEPS).

| File | Concept | Source composition |
| --- | --- | --- |
| `gif-1.gif` | "Your camera roll is the textbook." — café photo card + four vocab chips pop on | `gif-studio/index.html` |
| `gif-2.gif` | "AI suggests. You decide." — suggestions list, two rejected, "4 kept" verdict | `gif-studio/compositions/gif-2-you-decide.html` |
| `gif-3.gif` | "Veo, veo…" — mascot speech bubble types the clue, correct choice highlights | `gif-studio/compositions/gif-3-i-spy.html` |
| `gif-4.gif` | Artisan-style 3-act recreating the real `/demo` flow: "Try a photo lesson" picker → cursor picks "Study day" (desk photo) → "Finding objects…" scan → 5 numbered markers + Objects list (real scene words) → wordmark/tagline/IN BETA URL bar | `gif-studio/compositions/gif-4-artisan-style.html` (11s) |
| `gif-5.gif` | Same 3-act shape on the real `/practice` UI: "Capture a scene" dashed upload zone (Click / Upload buttons) → cursor uploads the desk photo → "Starting analysis…" → Scene analysis with 5 markers + "Check what this lesson will use" list → CTA | `gif-studio/compositions/gif-5-practice-upload.html` (11s) |
| `gif-6.gif` | gif-5 zoomed to 70% inside the 16:9 frame (butter padding) — survives the uvents card's `background-size: cover` center-crop in both directions | derived from `renders/gif-5.mp4` via ffmpeg `scale + pad` (no composition) |
| `gif-7.gif` | Full `/practice` page incl. the pasta-yellow wordmark header + enlarged text: cursor clicks Upload, desk photo lands in the dropzone → "Starting analysis…" → Scene analysis (5 markers + "Check what this lesson will use") → a practice task ("Choose the right word", `la libreta` correct, marker 1 rings) → CTA | `gif-studio/compositions/gif-7-practice-full.html` (13s) |
| `gif-8.gif` | gif-7 zoomed to 70% inside the 16:9 frame — crop-safe variant | derived from `renders/gif-7.mp4` via ffmpeg `scale + pad` (no composition) |

Re-render after editing a composition:

```sh
cd gif-studio
npx --yes hyperframes@0.8.181 render -o renders/gif-1.mp4                       # index.html
npx --yes hyperframes@0.8.181 render -c compositions/gif-2-you-decide.html -o renders/gif-2.mp4
# then MP4 → GIF:
ffmpeg -y -i renders/gif-1.mp4 -vf "fps=15,scale=960:-1:flags=lanczos,palettegen=max_colors=128" pal.png
ffmpeg -y -i renders/gif-1.mp4 -i pal.png -lavfi "fps=15,scale=960:-1:flags=lanczos [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4" ../gif-1.gif

# gif-6 (zoomed-out variant of gif-5):
ffmpeg -y -i renders/gif-5.mp4 -vf "scale=896:504:flags=lanczos,pad=1280:720:(1280-896)/2:(720-504)/2:color=0xFFF9ED" -c:a copy renders/gif-6.mp4
# then MP4 → GIF as above
```

Note: `gif-1.gif` is ~4 MB (full-photo content); imgur allows 20 MB, but a 640px
re-encode halves it if the page feels heavy.

## Promo images (`promo/`, 1536x1024)

- `steps-poster.png` — main poster candidate for the page's "Poster image" slot: IN BETA pill, "Your first lesson is already on the table."
- `promo-photo-to-words.png` — one photo → four vocab chips ("One photo. Linguini finds the words in it.")
- `promo-words-stay.png` — Revisit card with the four saved café words ("Every photo keeps its words.")

Generated with the OpenAI Images API (`gpt-image-1.5`, high) by
`generate_steps_images.py` — reads `OPENAI_API_KEY` from the environment,
raws in `raw/`, re-run one image with `--only=<name>`.

## Still needed

- A video: embed `videos/day-one/renders/Linguini-Beta-Promo.mp4` (30s, 1920x1080) or link the hosted version if the uploader prefers.

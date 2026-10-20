# Day One image generation

Pipeline: OpenAI Images API, `gpt-image-1`, `quality="high"`, `size="1024x1536"`.
Each call uses the Images **edit** endpoint with repository reference images
(wordmark, mascot, café photo, app screenshot) — the same pattern documented
in `../instagram/prompts.md`. Raw 2:3 output is saved to `raw/`, then fitted
inside a 1080 × 1350 (4:5) canvas padded with the poster's own corner
background colour.

The exact prompt strings are the `POSTERS` entries in
[`generate_posters.py`](generate_posters.py) — kept as a single source of
truth rather than duplicated here. Reference sets per poster:

| Poster | References sent |
| --- | --- |
| `01-day-one-morning` | wordmark, mascot, café interior (mood) |
| `02-one-photo` | wordmark, café interior (mood) |
| `03-you-decide` | wordmark, mascot |
| `04-i-spy` | wordmark, café interior (mood) |
| `05-words-stay` | wordmark, mascot, `docs/screenshots/vocabulary.png` (layout only) |

The LinkedIn video's textless hero art
(`marketing/videos/day-one/assets/day-one-key-art.png`) is a `generate` call
with no references: 1536 × 1024, high — morning café flatlay, explicitly
"no text, no letters, no logos".

## Lessons learnt

- **Fit, don't crop.** A centre-crop of the 1024 × 1536 output to 4:5 clipped
  the wordmark and bottom labels, because the model fills the canvas edge to
  edge. Padding the raw into 4:5 with the poster's own background colour is
  near-seamless and loses nothing.
- **Proofread every rendered word.** The first `04-i-spy` pass wrote "Vea"
  instead of "Veo" on the clue card. The fix was an explicit negative
  instruction in the prompt: 'first person "Veo" (I see), never "Vea"'.
- **Small deviations tolerated:** `02` shows the `la taza` chip floating
  clear of the cup and `la mesa` lacks its tomato dot; `03` kept five rows
  instead of six. Both read fine at feed size — regenerate only for real
  errors (language, meaning, brand), not pixel-perfect placements.

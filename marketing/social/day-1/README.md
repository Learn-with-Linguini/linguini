# Day One social pack

A five-poster "first day with Linguini" story, generated end-to-end with the
OpenAI Images API (`gpt-image-1`, high quality) — unlike `../instagram/` and
`../week-1/`, which were made with an earlier built-in generation tool.
Nothing in the older folders was modified; this pack sits alongside them.

## Posters

| File | Story beat | Headline |
| --- | --- | --- |
| `instagram/01-day-one-morning.png` | Morning hook | "Your first lesson is already on the table." |
| `instagram/02-one-photo.png` | Photo → vocabulary | "One photo." |
| `instagram/03-you-decide.png` | Learner review | "AI suggests. You decide." |
| `instagram/04-i-spy.png` | Practice | "Play I-Spy with your world." |
| `instagram/05-words-stay.png` | Saved vocabulary | "Every photo keeps its words." |

All five are 1080 × 1350 (Instagram 4:5 feed format). Uncropped 2:3 originals
are kept in `raw/` — reuse them for LinkedIn feed images or stories.

The matching 30-second LinkedIn video is the editable HyperFrames project in
[`../../videos/day-one/`](../../videos/day-one).

## Regenerating

```sh
# needs OPENAI_API_KEY in the environment
python3 marketing/social/day-1/generate_posters.py             # all five
python3 marketing/social/day-1/generate_posters.py --only=04   # one poster
python3 marketing/social/day-1/generate_posters.py --reprocess # refit raws to 4:5, no API calls
```

Generation settings and lessons learnt are in [`prompts.md`](prompts.md);
the exact prompts sent to the API are the `POSTERS` list in
[`generate_posters.py`](generate_posters.py).

## Posting notes

- Post the five as an Instagram carousel in order — they read as one
  continuous day.
- `03-you-decide` also works standalone for the "AI suggests, you decide"
  week-two theme; `05-words-stay` pairs with any vocabulary/journal post.
- Check `compare.html` (serve the repo root and open it in a browser) for a
  side-by-side of the previous campaign art and this set.

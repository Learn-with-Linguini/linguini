# Launch film

`out/linguini-launch.mp4` · 1920×1080 · 30 fps · 30.6 s · H.264 + AAC · mixed to −14 LUFS. `out/linguini-launch-720p.mp4` is a lighter copy for chat apps. `./render.sh` also writes `out/linguini-launch-master.mp4` (about 145 MB, not committed); upload that one to YouTube.

**The idea:** everything in your day has a word. Real footage, a camera focus frame that finds the object in each shot, and its word in Spanish, then in French. The cuts speed up with a solo piano, as the Claude Opus 5.5 film does with its horizon shots, until the piano stops dead on a plate of pasta. Then silence, and the wordmark.

It is 100 BPM; every cut lands on a note because the score and the edit share one beat grid (`edit.py`).

| Time | Section | Shot length | On screen |
| --- | --- | --- | --- |
| 0:00 | Black. The viewfinder blinks twice on two high notes | — | — |
| 0:01 | Five shots, piano alone: el café, la lluvia, el perro, la bicicleta, el pan | 3 beats (1.8 s) | the word under each object |
| 0:10 | Four shots, the left hand comes in: la lima, el gato, el libro, el sol | 2 beats | "Your day" |
| 0:15 | Six shots, a rising line: el vino, la luna, el reloj, la vela, el pájaro, la guitarra | 1 beat | "is the" |
| 0:18.6 | Eight shots in French, both hands driving: le café, l'orange, les fleurs, le métro, la tartine, la rue, le téléphone, le cœur | half a beat | "lesson." |
| 0:21 | A fork lifting pasta; full chord and riser | 3 beats | la pasta |
| 0:22.8 | Hard cut to silence | — | — |
| 0:23.4 | One quiet chord; the wordmark's strand draws itself | — | Linguini |
| 0:25.2 | | — | "Learn the language of your day." |
| 0:27 | | — | "Coming soon to Product Hunt" |

## How it's made

| File | Job |
| --- | --- |
| `edit.py` | The shot list: Mixkit clip, in-point, word, and the object's box. Writes `timeline.json` |
| `fetch.py` | Downloads the clips and the piano samples into `cache/` (neither is committed) |
| `plate.py` | Cuts, crops and grades the footage, with a slow push-in on every shot. Tracks each object with OpenCV CSRT and writes `boxes.json` |
| `overlay.html`, `overlay.js` | Focus frame, words, headline and end card, drawn as a pure function of time. Open `overlay.html?t=12` through a local server to scrub |
| `overlay.mjs` | Renders the overlay to transparent PNG frames with Playwright |
| `score.py` | Composes the score from single piano notes on the edit's beat grid, adds reverb and the riser, and cuts to silence on the last shot |
| `composite.sh` | Overlay on footage, film grain, loudness to −14 LUFS with a −1.5 dBFS limiter, mux |
| `render.sh` | All of the above, in order |

```sh
cd marketing/videos/promo-film
pip install -r requirements.txt
npm install            # Playwright; its Chromium must be available
./render.sh            # about 10 minutes; needs ffmpeg
```

If Playwright can't find a browser, run `npx playwright install chromium`, or point it at an existing Chrome with `CHROMIUM=/path/to/chrome ./render.sh`.

To change a word or swap a shot, edit `SHOTS` in `edit.py` and run `./render.sh`. Check the tracking before anything else: the boxes in `boxes.json` must sit on the object. Any replacement clip must show the **Free** licence badge on its Mixkit page, not Restricted (see `CREDITS.md`).

## YouTube

**Title:** Linguini: learn the language of your day

**Description:**

```
Everything in your day has a word. Photograph a moment and Linguini finds the words inside it, then turns them into a five-minute Spanish or French session and keeps the day in your journal.

Try it on a real photo, no sign-up: https://linguini-landing.vercel.app
Open the app: https://linguini-navy.vercel.app

Footage: Mixkit (mixkit.co). Piano: University of Iowa Musical Instrument Samples.
```

No chapters: at 30 seconds they get in the way. Upload `out/linguini-launch-master.mp4` as **Unlisted** until launch day (Product Hunt needs a full `youtube.com/watch?v=` link), then switch it to Public. Use `out/poster.jpg` as the custom thumbnail.

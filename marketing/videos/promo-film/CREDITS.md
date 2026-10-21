# Launch film: credits and licences

Every licence below was checked on 2026-09-24. Nothing in the film needs an on-screen or description credit. The courtesy line under **For the video description** is optional, but we should use it.

## Footage: Mixkit, Stock Video Free License

All 24 shots are from [Mixkit](https://mixkit.co) under the **Stock Video Free License**. It allows commercial projects, online marketing ads, social media posts and YouTube videos; attribution is not required ([licence](https://mixkit.co/license/); modal text fetched from `https://mixkit.co/license/modal/videoFree/`).

Mixkit also has a **Stock Video Restricted License** for personal projects only. It rules out commercial projects, advertising, company social media posts and YouTube, so **never use a Restricted clip here**. The badge is on each clip's page; `edit.py` notes the rule next to the shot list. Seven clips in the first draft of this edit were Restricted and were replaced.

The clips are not committed, because the licence does not let us redistribute them on their own. `fetch.py` downloads them into `cache/`.

| Time | Word | Clip | Mixkit ID |
| --- | --- | --- | --- |
| 0:01.20 | el café | [Cup of coffee on top of coffee beans](https://mixkit.co/free-stock-video/cup-of-coffee-on-top-of-coffee-beans-4992/) | 4992 |
| 0:03.00 | la lluvia | [Window on a rainy day](https://mixkit.co/free-stock-video/window-on-a-rainy-day-2846/) | 2846 |
| 0:04.80 | el perro | [Smiling dog](https://mixkit.co/free-stock-video/smiling-dog-1552/) | 1552 |
| 0:06.60 | la bicicleta | [A calm street in Paris](https://mixkit.co/free-stock-video/a-calm-street-in-paris-4348/) | 4348 |
| 0:08.40 | el pan | [People buying bagels at a market](https://mixkit.co/free-stock-video/people-buying-bagels-at-a-market-995/) | 995 |
| 0:10.20 | la lima | [Bunch of lemons slowly rotating](https://mixkit.co/free-stock-video/bunch-of-lemons-slowly-rotating-42945/) | 42945 |
| 0:11.40 | el gato | [White cat lying among the grasses seen up close](https://mixkit.co/free-stock-video/white-cat-lying-among-the-grasses-seen-up-close-22732/) | 22732 |
| 0:12.60 | el libro | [A person reading a book, close up](https://mixkit.co/free-stock-video/a-person-reading-a-book-close-up-1724/) | 1724 |
| 0:13.80 | el sol | [View of the horizon in the sea while a sailboat sails](https://mixkit.co/free-stock-video/view-of-the-horizon-in-the-sea-while-a-sailboat-sails-4477/) | 4477 |
| 0:15.00 | el vino | [A mesmerizing stream of red wine falling into a elegant wineglass over a black backdrop](https://mixkit.co/free-stock-video/a-mesmerizing-stream-of-red-wine-falling-into-a-elegant-wineglass-over-a-black-backdrop-52407/) | 52407 |
| 0:15.60 | la luna | [Full moon](https://mixkit.co/free-stock-video/full-moon-4305/) | 4305 |
| 0:16.20 | el reloj | [Slowly approaching a clock on a black background](https://mixkit.co/free-stock-video/slowly-approaching-a-clock-on-a-black-background-28897/) | 28897 |
| 0:16.80 | la vela | [Lighting candles in the dark](https://mixkit.co/free-stock-video/lighting-candles-in-the-dark-3461/) | 3461 |
| 0:17.40 | el pájaro | [Bird singing in a tree](https://mixkit.co/free-stock-video/bird-singing-in-a-tree-2560/) | 2560 |
| 0:18.00 | la guitarra | [Close view of a musician playing a Spanish guitar](https://mixkit.co/free-stock-video/close-view-of-a-musician-playing-a-spanish-guitar-44161/) | 44161 |
| 0:18.60 | le café | [Serving a sparkling cappuccino in a cup](https://mixkit.co/free-stock-video/serving-a-sparkling-cappuccino-in-a-cup-41859/) | 41859 |
| 0:18.90 | l’orange | [Hand of a person squeezing an orange on a light background](https://mixkit.co/free-stock-video/hand-of-a-person-squeezing-an-orange-on-a-light-background-10435/) | 10435 |
| 0:19.20 | les fleurs | [View to the sideboard of a flower shop](https://mixkit.co/free-stock-video/view-to-the-sideboard-of-a-flower-shop-4742/) | 4742 |
| 0:19.50 | le métro | [Subway cars departing from an underground station](https://mixkit.co/free-stock-video/subway-cars-departing-from-an-underground-station-40672/) | 40672 |
| 0:19.80 | la tartine | [Preparing a slice of bread with avocado and vegetables](https://mixkit.co/free-stock-video/preparing-a-slice-of-bread-with-avocado-and-vegetables-43922/) | 43922 |
| 0:20.10 | la rue | [Narrow and old alley in Venice](https://mixkit.co/free-stock-video/narrow-and-old-alley-in-venice-4600/) | 4600 |
| 0:20.40 | le téléphone | [A person texting on a smartphone](https://mixkit.co/free-stock-video/a-person-texting-on-a-smartphone-1711/) | 1711 |
| 0:20.70 | le cœur | [Drawing a heart on a foggy window on a rainy day](https://mixkit.co/free-stock-video/drawing-a-heart-on-a-foggy-window-on-a-rainy-day-18308/) | 18308 |
| 0:21.00 | la pasta | [Eating fettuccine](https://mixkit.co/free-stock-video/eating-fettuccine-2434/) | 2434 |

## Music: original score

`audio/score.flac` is an original piece written in code by `score.py` for this film. It plays one piano, note by note, on the same beat grid as the edit.

- **Piano samples:** University of Iowa Electronic Music Studios, *Musical Instrument Samples*, Steinway model B (https://theremin.music.uiowa.edu/MISpiano.html). The collection has been free to download and use since 1997 without restriction. `audio/piano-notes.json` lists the 68 notes used; `fetch.py` downloads them, and they are not committed.
- **Riser** `audio/sfx-riser2.wav`: "riser-tension", AtomCut, *Motion Essentials* (DSP-synthesized), CC0 1.0, from `novincode/atomcut-library` @ `391f87ff50bd` : `packs/motion-essentials/audio/riser-tension.wav`. It was converted to 48 kHz stereo WAV, silence-trimmed and peak-normalized.
- The reverb is synthetic, generated in `score.py`.

## Type

- **Instrument Serif** (the words, headline and tagline): SIL Open Font License 1.1, `assets/fonts/OFL-InstrumentSerif.txt`. From `google/fonts`: `ofl/instrumentserif`.
- **Baloo 2 ExtraBold** (the wordmark, redrawn as live text with its linguini strand) and **Nunito Sans** (the small English glosses): SIL Open Font License 1.1, as used in the app.

## For the video description (optional courtesy line)

```
Footage: Mixkit (mixkit.co). Piano: University of Iowa Musical Instrument Samples.
```

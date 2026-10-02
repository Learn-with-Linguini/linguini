# Linguini launch video

A 30-second, 1920 × 1080, 30 fps narrated ad for the **curated Linguini landing demo**. The story follows one ready-made hillside-street photo through Spanish/French words, I-Spy, sentence building and a **sample** journal page. The last frame points to [the live mini session](https://linguini-landing.vercel.app/). This is an illustrative marketing film, not a claim that personal-photo analysis, speech grading or account journal persistence works in this demo.

## Watch and review

From the **repository root**:

```sh
python3 -m http.server 8018 --bind 127.0.0.1
```

Open **http://localhost:8018/marketing/videos/launch-film/review.html**. The browser page has a controlled, non-autoplaying video, MP4/poster/SRT download links, the full narration transcript and the four Product Hunt gallery images. It opens through a local web server so fonts, images and video load consistently. The video includes visible phrase captions; the transcript is also readable below the player. The current reviewer artifact names are `renders/linguini-launch-v2.mp4`, `renders/poster.jpg` and `voice/narration.srt`.

## Build the composition

Requires Node 22+, npm, FFmpeg/ffprobe and a Chromium-compatible browser for Hyperframes rendering. From `marketing/videos/launch-film/`:

```sh
npm ci
bash mix-audio.sh
node build.mjs
npx hyperframes lint .
npx hyperframes check .
npx hyperframes render . --quality high --fps 30 --output renders/linguini-launch-v2.mp4
```

These commands use the locked `hyperframes@0.8.71` and `gsap@3.15.0` dependencies. `build.mjs` assembles the nine scenes into `index.html` with its local assets, voice envelope and timed captions. The render command and flags were checked against the installed Hyperframes CLI help. The source audio files must be present before building: `audio/final-mix.wav`, `voice/envelope.json` and `voice/narration.srt`. To make a poster from the finished MP4, run:

```sh
ffmpeg -y -ss 28.5 -i renders/linguini-launch-v2.mp4 -frames:v 1 renders/poster.jpg
```

The landing site plays this film, muted with a "Sound on" button, in the blog post "Why we teach with your photos". Refresh its web copies after a re-render, from the repository root:

```sh
ffmpeg -y -i marketing/videos/launch-film/renders/linguini-launch-v2.mp4 -c:v libx264 -crf 26 -preset slow -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart landing/public/blog/photos/narrated-film-1080p.mp4
ffmpeg -y -i marketing/videos/launch-film/renders/linguini-launch-v2.mp4 -vf scale=1280:-2 -c:v libx264 -crf 27 -preset slow -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart landing/public/blog/photos/narrated-film-720p.mp4
ffmpeg -y -ss 7.6 -i marketing/videos/launch-film/renders/linguini-launch-v2.mp4 -frames:v 1 -vf scale=1280:-2 -q:v 3 landing/public/blog/photos/narrated-film-poster.jpg
```

`landing/public/blog/photos/narrated-film.vtt` copies the cue timings from `voice/narration.srt`. The film already burns its captions into the picture, so the blog doesn't show the track by default.

The optional raw voice regeneration steps are documented in `voice/generate.py` and use `voice/requirements.txt`. The score and effects can be regenerated with `python3 audio/build_audio.py`. `voice/build.py` assembles the locally synthesized narration clips into `voice.wav`, timed SRT captions and the 30 fps amplitude envelope; it expects the `raw-*.wav` and bilingual phrase clips already present in `voice/`. The final stereo mix in `audio/final-mix.wav` combines that voice with the score and effects. Run `bash mix-audio.sh` to rebuild the stereo mix from the retained voice and music/SFX stems. The raw synthetic voice clips are included so a clean checkout can reproduce the timing without calling a paid service.

## Creative and source notes

- **Picture:** one real hillside-street photograph from the landing demo. The `assets/demo-review.png` shot is an actual captured demo review screen; other practice cards, cursor actions, markers, sentence and journal shots are HTML motion reconstructions using the demo's curated content, not screen recordings of a personal-photo session.
- **Voice:** locally generated Kokoro `af_heart` narration. The small SVG Linguini mascot is a drawn brand character, **not a human likeness or talking-head deepfake**. Its mouth movement follows the voice WAV's measured amplitude, rather than inferred phonemes.
- **Music:** original 120 BPM instrumental and sound effects synthesized by `audio/build_audio.py`; no stock track or third-party sample is used. Cut points at 0, 2, 5, 8, 12, 16, 19, 23 and 27 seconds have musical accents, with a clean stop at 30 seconds.
- **Brand:** local Linguini wordmark/logo, Baloo 2 and Nunito Sans fonts, cream/tomato/teal palette, and product wording from the repository landing site. The photo credit for `hillside-street.jpg` is **Viktor Hanáček / picjumbo**; provenance and the licence note are in [landing photo credits](../../../landing/public/photos/credits.json). Verify source-image rights before public upload. The separate Product Hunt gallery and its photo-rights notes are in the [media kit](../../media/README.md).

Final device playback and subjective audio balance are for team review before publishing. No Product Hunt video has been posted from this directory.

## Export verification

The final MP4 was decoded through all 900 frames and inspected via extracted contact sheets. It is exactly 30.000 seconds, H.264 at 1920 × 1080 / 30 fps with stereo AAC at 48 kHz. FFmpeg found no black gaps; measured program loudness is -16.13 LUFS integrated with a -1.50 dBTP peak. Hyperframes runtime, layout and contrast checks report zero errors. The one layout warning is the intentional 125 ms overlap as the “flores” token lands on the blank; 25 lint warnings concern repeated assets and single-file composition organization. The browser review page and final poster were also inspected. These checks do not replace the team listening to the voice and music before publication.

# Linguini marketing

Everything for launching and selling Linguini outside the app: the Product Hunt kit, launch videos, the media kit and the business model. The public marketing site itself lives in [`frontend/src/marketing/`](../frontend/src/marketing), and deploys with the learner app from the same Vite build.

| Path | What it is |
| --- | --- |
| [`product-hunt/`](product-hunt/README.md) | Product Hunt launch kit: status and team decisions ([README](product-hunt/README.md)), launch dashboard and checklists ([plan.md](product-hunt/plan.md)), listing copy ([listing.md](product-hunt/listing.md)), channel posts and reply bank ([social-posts.md](product-hunt/social-posts.md)), and the six gallery images with their HTML sources |
| [`videos/launch-film/`](videos/launch-film/README.md) | 30-second narrated launch film built with Hyperframes, synthesized score and a team [review page](videos/launch-film/review.html). Render: `renders/linguini-launch-v2.mp4` |
| [`videos/promo-film/`](videos/promo-film/VIDEO.md) | 30-second launch film from real footage with a focus frame naming objects in Spanish and French, and an original piano score. Render: `out/linguini-launch.mp4` (+ 720p) |
| [`videos/campaign/`](videos/campaign/scripts.md) | Human-voice campaign scripts (30, 20, 15 and 6 seconds), a [recording guide](videos/campaign/recording-guide.md) and music/SFX beds. Not filmed yet |
| [`media/`](media/README.md) | Media kit: illustrated gallery, Product Hunt icon, social square, banners, the 50-second animated explainer (`export/explainer.mp4`, script in [explainer-script.md](media/explainer-script.md)) and the 18-second illustrated teaser |
| [`landing-page/`](landing-page/milestone-landing-page.html) | Landing page milestone write-up: hero, features and pricing, SEO, Open Graph previews, GEO, team decisions and next steps. Open in a browser and paste into the Google Doc, like `business-model/milestone-business-model.html` |
| [`analytics/`](analytics/milestone-analytics.html) | Analytics milestone write-up: Contentsquare set-up and checks, the Home redesign before and after, journeys from Home, mobile against desktop, data caveats and next metrics. Replace the yellow screenshot boxes before pasting into the Google Doc |
| [`feature-posters/`](feature-posters/build.py) | Feature tour from real app captures (`docs/screenshots/features/`): 16 captioned posters, a click/scroll/keyboard HTML tour (`export/index.html`), a cross-fading MP4 and animated WebP showcase, and a contact sheet of every capture (`export/feature-map.png`). Captions live in `features.json` |
| [`business-model/`](business-model/README.md) | Pricing proposal (Free, Plus, Founding Plus), reproducible AI cost model and charts. The model prices the five AI calls on the models chosen in the root [`MODEL_COMPARISON.md`](../MODEL_COMPARISON.md), all through OpenRouter, using the token counts measured there |

Dated launch plans and milestone write-ups are retained as project evidence. Their dates, proposed prices and readiness notes are historical; the [project documentation](../docs/README.md) describes the current application.

## Finished videos

| Video | File | Length |
| --- | --- | --- |
| Narrated launch film | `videos/launch-film/renders/linguini-launch-v2.mp4` | 30 s |
| Promo film (real footage) | `videos/promo-film/out/linguini-launch.mp4` | 30.6 s |
| Animated explainer | `media/export/explainer.mp4` | 49.5 s |
| Illustrated teaser | `media/export/teaser-illustrated.mp4` | 18 s |

Which one becomes the Product Hunt listing video is an open decision in the [launch kit](product-hunt/README.md#team-decision-checklist).

Where each one plays on the landing site: the promo film is the home-page film (`frontend/public/film/`), the narrated launch film is in the blog post "Why we teach with your photos" (`frontend/public/blog/photos/`), and the explainer is in the launch post (`frontend/public/blog/launch/`). All three start muted with a "Sound on" button. The launch post's card cover is a silent loop rendered by `media/launch_cover.py`.

## Rebuilding

Each folder documents its own pipeline. In short:

```sh
# Narrated launch film (full steps in videos/launch-film/README.md)
cd marketing/videos/launch-film && npm ci && bash mix-audio.sh && node build.mjs \
  && npx hyperframes render . --quality high --fps 30 --output renders/linguini-launch-v2.mp4

# Promo film
cd marketing/videos/promo-film && pip install -r requirements.txt && npm install && ./render.sh

# Media kit: gallery images and teaser, banners (Pillow)
bash marketing/media/build_video.sh && python3 marketing/media/banners.py

# Animated explainer (needs the one-time venv and voice model in media/explainer.py)
marketing/media/.venv/bin/python marketing/media/explainer.py

# Feature posters, showcase video and HTML tour (Pillow + FFmpeg). Edit captions or the
# shot list in feature-posters/features.json; captures come from docs/screenshots/features/.
# --inline additionally writes a single self-contained tour you can send as one file.
python3 marketing/feature-posters/build.py --inline /tmp/linguini-feature-tour.html

# Business model numbers and charts
python3 marketing/business-model/model/cost_model.py && python3 marketing/business-model/media/render.py
```

Several scripts read photos, fonts and brand art from `frontend/public` and `frontend/src/marketing/assets`, and some write web-sized copies back into `frontend/public/blog`. Keep the two in step when you change an asset.

# Linguini landing page

The public marketing site for Linguini. It is a Next.js 16 App Router project that lives apart from the learner app (`frontend/`) and the API (`backend/`), so it builds and deploys on its own.

## Run it

```sh
npm ci
npm run dev      # http://localhost:3000
npm run lint     # oxlint + TypeScript
npm run build    # production build, also pre-renders the OG images
```

Copy `.env.example` to `.env.local` to point the site at real URLs:

| Variable | Used for |
| --- | --- |
| `NEXT_PUBLIC_SITE_URL` | Canonical URL, sitemap and absolute OG image links. On Vercel it falls back to the production domain. |
| `NEXT_PUBLIC_APP_URL` | Where “Start learning” and “Log in” go. Production builds (including Vercel) default to the live app, https://linguini-navy.vercel.app; development uses `http://localhost:5173`. |
| `REDIRECT_FROM_HOSTS` | Optional. After moving to a custom domain, old hosts (e.g. `linguini-landing.vercel.app`) that should 301 to `NEXT_PUBLIC_SITE_URL`. |
| `GOOGLE_SITE_VERIFICATION`, `BING_SITE_VERIFICATION` | Optional. Search Console and Bing Webmaster Tools ownership meta tags (the `content` value only). |
| `INDEXNOW_KEY` | Optional. Served at `/indexnow-key.txt`; `node scripts/indexnow.mjs <site-url>` then asks Bing and partners to re-crawl the sitemap. |
| `NEXT_PUBLIC_PRODUCT_HUNT_URL`, `NEXT_PUBLIC_PRODUCT_HUNT_POST_ID` | Optional. Shows Product Hunt's badge in the hero and adds the listing to Organization `sameAs`. Hidden until both are set. |

Check every page's search and share tags against a running build with `node scripts/check-seo.mjs http://localhost:3000` (or the production URL). It crawls the sitemap and fails on a missing title, description, canonical, single `h1`, OG/X tag, broken OG image or invalid JSON-LD.

Live at https://linguini-landing.vercel.app (Vercel project `linguini-landing`, **Root Directory** `landing`).

## What’s inside

- **Interactive demo** (`components/try/`): pick a real photo, watch it get “analysed”, then play through word cards, I-Spy, a fill-in-the-blank and a sentence builder before the day is saved as a journal entry. Lesson content for each photo, in Spanish and French, is in `data/scenes.ts`.
- **SEO**: semantic sections with one `h1`, per-page metadata, `robots.txt`, `sitemap.xml`, a web manifest and JSON-LD (Organization, WebSite, SoftwareApplication with Free/Plus offers, FAQPage, BlogPosting). Build subpage metadata with `pageMetadata()` from `lib/seo.ts`. Next merges `openGraph`/`twitter` shallowly, so a page that sets only a title would keep the homepage's share card text.
- **Search-intent pages** (`app/learn/[language]/`): `/learn/spanish` and `/learn/french` list every word in the demo scenes with its article, gender and IPA, walk through a whole session, and carry their own FAQ, BreadcrumbList and DefinedTermSet JSON-LD. Copy is in `data/languages.ts`; the vocabulary comes from `data/scenes.ts`. The comparison post (`linguini-vs-duolingo`) reads the team-checked prices in `data/competitors.ts`, which the business model post's chart also uses. It is dated before the launch posts so they stay first on the blog.
- **AI answer engines (GEO)**: `/llms.txt` (`app/llms.txt/route.ts`) is a Markdown summary built from `data/pricing.ts`, `data/steps.ts`, `data/faq.ts` and `data/posts.ts`, the same data the page renders, so the two always agree.
- **Social previews**: Open Graph and X cards made with `next/og` (`app/opengraph-image.tsx`). Each blog post has its own generated card (`app/blog/[slug]/opengraph-image.tsx`). `app/og/route.tsx` renders a dynamic journal-page card, and `/share?photo=…&lang=…&words=…` uses it so a finished demo session can be shared with its own preview.
- **Blog** (`app/blog/`, `components/blog/`): the three newest posts sit below the final call to action. Post metadata is in `data/posts.ts` and each body is a component in `components/blog/posts/`. Interactive charts and the animated lesson walkthrough live in `components/blog/interactive/`; their numbers come from `marketing/business-model/model/cost_model.py`, which prices the five AI calls on the models chosen in the root `MODEL_COMPARISON.md` (all routed through OpenRouter) with the token counts measured there. Rerun it and update `components/blog/interactive/data.ts` when a model changes. The main post's looping cover video is rendered with `python3 scripts/render-post-video.py` (Pillow and ffmpeg). The launch post's looping cover (`public/blog/launch/cover-loop.mp4` and its poster) is rendered by `python3 marketing/media/launch_cover.py` from the launch banners. There are four posts: the business model, the launch plan (`LaunchCampaign.tsx`, with its diagrams in `components/blog/launch/Plan.tsx`, brand marks in `Logos.tsx` and post copy in `content.ts`) and "Why we teach with your photos" (`PhotoLessons.tsx`), which absorbed the old "Inside a Linguini lesson" post, plus the older comparison post (`CompareApps.tsx`), which only appears in the blog's "All posts" list. Old slugs listed in `movedPosts` (`data/posts.ts`) redirect permanently through `next.config.ts`. A post with a `pdf` path offers a download; regenerate it after editing with `NEXT_PUBLIC_SITE_URL=https://linguini-landing.vercel.app npm run build && npm start`, then `node scripts/export-post-pdf.mjs` in another terminal (needs Google Chrome).
- **Launch film** (`components/Film.tsx`): the 30-second real-footage film, shown right under the demo. It loops muted while on screen (browsers block autoplay with sound), and "Sound on" restarts it with the score. Reduced-motion visitors see the poster. Desktop gets the 1080p file and phones get the 720p one. The files in `public/film/` are copies of `marketing/videos/promo-film/out/`, so copy them again after a re-render. The poster is the frame at 12.4 s: `ffmpeg -ss 12.4 -i linguini-launch.mp4 -frames:v 1 -q:v 3 public/film/poster.jpg`.
- **Videos with sound** (`components/SoundVideo.tsx`): the player behind the launch film, reused in the blog. It takes `sources` (with optional `media` queries), a `poster`, a `label` and optional WebVTT `captions`. The launch post uses it for the 50-second explainer (`public/blog/launch/explainer-720p.mp4`, with captions). "Why we teach with your photos" uses it for the narrated launch film: `public/blog/photos/narrated-film-{1080p,720p}.mp4` are web encodes of `marketing/videos/launch-film/renders/linguini-launch-v2.mp4` (see that folder's README).
- **Share widgets**: `components/ShareBar.tsx` builds share links for X, WhatsApp, Telegram, LinkedIn and Facebook, plus the native share sheet and copy link. It loads no third-party scripts.

## Assets

- Brand wordmark, mascot and pasta avatars are copied from `frontend/public/`. Edit the originals there, then re-export them here.
- Every photo in `public/photos/` is a real photograph, not AI-generated. Each one's source repository, commit date and licence notes are in `public/photos/credits.json`, which the `/credits` page displays.

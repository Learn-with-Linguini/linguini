# Linguini Product Hunt launch kit

**Status: prepared for team review; no Product Hunt post has been published and no message has been sent.** The public [landing page](https://linguini-landing.vercel.app/) offers a curated-photo mini session. The recommended next step is a supervised learner beta, followed by a Product Hunt launch once the checks in the [launch dashboard](plan.md) pass. The planning slot is **Saturday 17 October 2026 at 00:01 PDT / 15:01 SGT** (moved from Tuesday 13 October: Saturdays have about a third as many launches, and Product Hunt reports 15% more visit clicks on weekends). Move it if readiness slips.

> **Open decision: launch date.** This kit merges two drafts. The newer one plans **Sat 17 October, 15:01 SGT**. The older readiness review proposed **Wed 14 October, 15:01 SGT** (a mid-week day with normal traffic, two weeks after 30 September to clear the must-fix list), with Tue 13 October or the following week as fallbacks if it clashes with midterms or CS3216 deadlines. Pick one, then check it against everyone's timetable. Don't launch on a day when two of the four of us have exams.

## What's in this folder

| File | Use |
| --- | --- |
| [plan.md](plan.md) | Launch dashboard: useful links, readiness audit and must-fix list, goals and definitions, owner board and launch-day roles, tasks by week, go/no-go, hour-by-hour run, distribution lists (communities, creators, newsletters), assets, retention, and what we verified about Product Hunt's rules. |
| [listing.md](listing.md) | Everything pasted into Product Hunt: name, taglines, description, launch tags, pricing, links, thumbnail, gallery order and captions, video, first maker comment, the full-release draft and the demo video storyboard. |
| [social-posts.md](social-posts.md) | Every channel post (X, LinkedIn, Instagram, TikTok, Telegram/WhatsApp, email, Reddit, Show HN), one-to-one and creator outreach, and the reply bank for Product Hunt comments. |
| [milestone-launch-campaign.html](milestone-launch-campaign.html) | The launch-campaign milestone write-up. Open it in a browser, copy all and paste into the Google Doc, like `business-model/milestone-business-model.html`. |
| [gallery/](gallery/) | Six 1270 × 760 gallery images (`01-hero` to `06-habit`, each with an `@2x`), the 240 × 240 thumbnail (PNG and GIF) and the 1200 × 630 social card. |
| [gallery-src/](gallery-src/) | HTML compositions for the gallery, built from 4× captures of the running landing page. The captures aren't committed; `capture.mjs` regenerates them from `landing/` on port 3200, then `render.mjs` and `thumb.mjs` export the PNGs and GIF. |

## Elsewhere in the repo

| Material | Use |
| --- | --- |
| [Narrated launch film and team review page](../videos/launch-film/review.html) | 30-second narrated film for team review; includes the MP4, poster, transcript and gallery in one place. Serve the worktree locally as described in the [video guide](../videos/launch-film/README.md). |
| [Promo film](../videos/promo-film/) | 30-second launch film from real Mixkit footage with a piano score. YouTube title and description are in [VIDEO.md](../videos/promo-film/VIDEO.md); every clip and licence is in [CREDITS.md](../videos/promo-film/CREDITS.md). |
| [Campaign scripts](../videos/campaign/scripts.md) | Human-voice campaign scripts, with a [recording guide](../videos/campaign/recording-guide.md) and audio mixes. |
| [Media kit](../media/README.md) | Four illustrative Product Hunt gallery images, icon, social square, banners, the animated explainer (`export/explainer.mp4` + `.srt`) and editable sources. |
| [Explainer video script](../media/explainer-script.md) | Script and production notes for the 50-second animated explainer: visual system, second-by-second voiceover, visuals and motion notes, audio, and claims to verify. The rendered video, captions and style frames are in the media kit. |
| [Business model](../business-model/README.md) | Pricing proposal (Free, Plus, Founding Plus), cost model and the metrics to watch. |
| [Launch campaign blog post](../../landing/components/blog/posts/LaunchCampaign.tsx) | Public write-up at `/blog/launch-week`, organised around the milestone questions: launch time (and why a Singapore team launches on Product Hunt's Pacific clock), open demo versus invite list, the listing and explainer, a sideways-scrolling rail of every channel draft, banners, who we tell (circles, communities, creators, where we're not posting), the three launch-day shifts and on-call roles, the week-one return target and the next launch. The checklist shows the first task of each week and expands to all of them ([`Checklist.tsx`](../../landing/components/blog/launch/Checklist.tsx), diagrams in [`Plan.tsx`](../../landing/components/blog/launch/Plan.tsx), post text in [`content.ts`](../../landing/components/blog/launch/content.ts)). Keep it in step with [plan.md](plan.md) and [social-posts.md](social-posts.md). |

## Team decision checklist

- [ ] Agree on the launch promise: curated interactive preview now, or a full learner-app release after production verification.
- [ ] Pick the launch date (17 or 14 October, see above) and write it in the team calendar in both time zones.
- [ ] Redeploy the landing-site CTA fix and confirm that signup, login and every plan link opens the intended production route. One audit found the deployed page pointing those links to `localhost`; another found them correct on the same day (see the [readiness audit](plan.md#current-readiness-audit-24-september-2026)).
- [ ] Reconcile landing claims about automatic photo analysis, speech feedback, pricing and Plus trials with working production behavior. Photo analysis now runs on Claude Haiku 4.5 through OpenRouter (`AI_SCENE_ANALYSIS_*` in `backend/.env.example`; model choices in `MODEL_COMPARISON.md`), but `backend/README.md` still describes placeholder analysis and speech grading is not built. Confirm on production before any copy says the app finds objects in your photo.
- [ ] Decide Product Hunt pricing: **Free** until someone can actually buy Plus. The landing page shows US$6.99/mo or $59.88/yr; the [business model](../business-model/README.md) proposes $7.99/mo or $49.99/yr plus Founding Plus.
- [ ] Publish a privacy policy and terms, add a support email, and name a human owner for support, incidents and launch replies (must-fix items 2 and 3 in [plan.md](plan.md#must-fix-before-launch-day-ranked)).
- [ ] Confirm photo rights and inspect every media export. Anything in the gallery, thumbnail or video must be our own or have a confirmed licence.
- [ ] Choose the listing video: the 50-second animated explainer, the 30-second narrated launch film or the 30-second promo film (see [listing.md](listing.md#video)). Review it with sound and captions on desktop and phone. The narrated film depicts the **curated landing demo** through animation and one captured demo screen; it does not show a personal-photo workflow. Record a genuine product walkthrough before any listing that claims that flow is live.
- [ ] Choose the gallery set: four illustrative images from the media kit, or six compositions in `gallery/` (see [listing.md](listing.md#gallery)).
- [ ] Have the team review the Product Hunt listing, tagline, gallery order, first comment and outreach text.
- [ ] Run the beta and go/no-go checklist in [plan.md](plan.md#go--no-go-at-t1), then schedule the listing. Replace `[PH_POST_URL]` after Product Hunt creates the post.

The source fix in `landing/lib/site.ts` makes production builds use the deployed learner-app URL when `NEXT_PUBLIC_APP_URL` is unset, including in browser-rendered components. Development keeps the local app URL. Setting that environment variable explicitly remains the preferred deployment configuration.

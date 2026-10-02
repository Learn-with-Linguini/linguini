# Linguini launch dashboard

**Recommendation:** use a small, supervised learner beta now; schedule a public Product Hunt launch only after the gates below pass. The tentative public slot is **Saturday, 17 October 2026, 00:01 Pacific Daylight Time (15:01 Singapore time)**. A Databox analysis of 2026 launches found Saturdays have about a third as many launches as Tuesdays, and Product Hunt reports 15% more visit clicks on weekend launches; for a small network, that trade favours Saturday. [Databox](https://www.producthunt.com/p/databox/i-ve-analyzed-all-2026-ph-launches-to-find-the-best-day-to-launch) · [Preparing for launch](https://www.producthunt.com/launch/preparing-for-launch) This is a planning target, not a booked launch or a claim that the learner app is ready. Product Hunt runs on Pacific 24-hour launch days and recommends 12:01 a.m. Pacific when the team can cover the day. [Product Hunt posting guide](https://help.producthunt.com/en/articles/479557-how-to-post-a-product) · [Product Hunt launch guide](https://www.producthunt.com/launch)

> **Open decision: launch date.** The earlier readiness review proposed **Wednesday 14 October 2026, 15:01 SGT** (07:01 UTC), ending 14:59 SGT on Thursday 15 October. Its reasons: two weeks to clear the must-fix list, within Product Hunt's 30-day scheduling window, and a mid-week day with normal traffic. Fallbacks were Tuesday 13 October or the following week. Whichever date wins, check it against everyone's timetables, midterms and CS3216 deadlines, and don't launch on a day when two of the four of us have exams. If the date has to slip, move it rather than launching with must-fix items 1 to 4 open; pick the new date from the Pre-Launch Dashboard.

**Time zones.** Product Hunt launches go live at 12:01 am Pacific. On 17 October (and 14 October) the Pacific coast is on daylight time (PDT, UTC−7), so launch is at **15:01 SGT** and the Product Hunt day ends at 23:59 PDT, which is **14:59 SGT the next day**. Plan for 24 hours of launch, Saturday afternoon to Sunday afternoon in Singapore. US daylight time ends on Sunday 1 November 2026. From then on, Pacific is PST (UTC−8) and 12:01 am PT becomes **16:01 SGT**. Singapore has no daylight saving. If the date moves past 1 November, change every SGT time in this plan by +1 hour.

The primary goal is **learners who complete a lesson and return**, not a leaderboard position. A public interactive demo can collect useful feedback immediately, but a public promise that people can upload any photo and get a fully generated lesson would outrun the current backend: uploaded photos currently receive explicitly labeled sample object suggestions; real image analysis, AI generation and speech evaluation remain unimplemented. The app has Supabase login and image upload paths in the current code and backend README, but these need production end-to-end verification. The older `frontend/README.md` describes an earlier implementation, so use `backend/README.md` and a live smoke test when approving claims.

> **Open decision: what the app does today.** Every AI call now goes through OpenRouter, with photos read by Anthropic's Claude Haiku 4.5 (`AI_SCENE_ANALYSIS_PROVIDER=openrouter` in `backend/.env.example`; choices justified in `MODEL_COMPARISON.md`). `backend/README.md` still describes fixed suggestions and no pixel inspection. Settle this with a live smoke test before any listing, post or reply says Linguini finds the objects in your photo.

This dashboard is modelled on [Yangshun Tay's Docusaurus 2.0 launch dashboard](https://gist.github.com/yangshun/1e84ae8461975e7fa9a7d153621c3756): links, a minute-level timeline, tasks, assets, outreach and after-launch tasks in one place. The blog copy at `/blog/launch-week` has the same checklist with tickable boxes; keep the two in step ([`landing/components/blog/launch/Checklist.tsx`](../../landing/components/blog/launch/Checklist.tsx)).

## Useful links

- Landing page (Product Hunt primary URL): https://linguini-landing.vercel.app/
- Learner app: https://linguini-navy.vercel.app/
- Launch blog post: https://linguini-landing.vercel.app/blog/launch-week
- Product Hunt post: `[PH_POST_URL]` (fill in once the draft exists) · Edit: `[PH_EDIT_URL]`
- Product Hunt listing copy: [listing.md](listing.md)
- Channel posts, outreach and reply bank: [social-posts.md](social-posts.md)
- Media kit: [../media/README.md](../media/README.md)
- Analytics dashboard: `[DASHBOARD_URL]`
- Error logs and rollback: `[LOGS_URL]` · `[DEPLOYS_URL]`
- Support inbox owner: `[NAME]`

## Current readiness audit (24 September 2026)

Two audits were made on 24 September, one from the live sites and one from the repository. Both are kept here.

| Item | Evidence | Decision |
| --- | --- | --- |
| Landing page | `https://linguini-landing.vercel.app/` returns HTTP 200; it has an interactive, curated-photo demo, Spanish/French content, branded OG cards and share pages. | Usable as the primary Product Hunt destination after copy/links are reconciled. |
| App destination | `https://linguini-navy.vercel.app/login?mode=signup` returns HTTP 200. Production landing HTML currently renders signup/login/Plus links to `http://localhost:5173/login...` because `NEXT_PUBLIC_APP_URL` is unset in that deployment. A source-level fallback fix is being prepared; production deployment remains pending. | **Hard no-go:** deploy the fix or set the production app URL, then click every CTA on mobile and desktop. HTTP 200 alone does not prove signup works. |
| Landing claims | Current page describes automatic photo analysis, pronunciation feedback, daily free plan, Plus trial and prices. Backend documents placeholder analysis and no speech grading. | **Hard no-go:** verify or revise each claim before directing a broad audience here; never charge or advertise a trial that cannot be fulfilled. |
| Funnel measurement | Landing source has no first-party analytics events for demo completion, CTA click or signup handoff; app HTML loads Contentsquare, but that does not establish a measured funnel. | Instrument privacy-aware events and verify them in the live dashboard before launch. |
| Support and privacy | Photo uploads involve personal images; landing has photo credits, but the public support route, user-photo explanation and response owner need review. | Assign an inbox owner and verify privacy/support links, retention/deletion wording and escalation path. |

> **Open decision: CTA links.** The repository audit found the opposite of row 2: on 24 September the landing page's "Start free" and "Log in" buttons pointed at `https://linguini-navy.vercel.app/login?mode=signup` and `/login`, and both sites returned 200. Tap every button on the production site to settle it, and check again after every deploy.

**Verdict from the repository audit:** not today; launch as a free product after must-fix items 1 to 5 below. The product itself is ready for Product Hunt. The concept is distinctive, and the demo lets anyone try it in under a minute without signing up. What's missing is the trust layer around it. The landing page offers a paid plan nobody can buy, there is no privacy policy for an app that uploads personal photos, there's no way to contact us, and the licences for most landing-page photos are unconfirmed. All of that can be fixed in two weeks, and each gap would come up in the first hour of comments. Launch day is hard to redo, so it's worth waiting for.

### What's strong

- **A demo that needs no sign-up.** The landing page runs a real session on real photos. Product Hunt visitors can try the idea straight away, which the featuring guidelines reward ("immediate access").
- **A concept that's clear in one line.** "Your camera roll is the textbook" is novel and easy to repeat, and it isn't one more AI chatbot tutor. It fits Product Hunt's "Novel" and "Creative" criteria.
- **The learner stays in charge.** The AI suggests words, and you untick or add before every session. That's a good answer to "is the AI accurate?" and it's already built.
- **A polished landing page.** Open Graph images, share cards, FAQ, how-it-works, a journal wall, a photo-credits page, and a consistent pasta brand from mascot to streak to avatars.
- **Works in the browser, nothing to install.** Phone, tablet or laptop. Nobody gets turned away for being on the wrong platform.

### Blockers and risks

| # | Issue | Evidence | Severity |
|---|---|---|---|
| 1 | **The pricing page offers a Plus plan you can't buy.** The page shows US$6.99/mo or $59.88/yr and a "Try Plus free for 7 days" button, but billing doesn't exist. The button goes to `…/login?mode=signup&plan=plus-yearly`, and the app ignores the `plan` parameter. The FAQ says Plus "adds unlimited sessions, pronunciation feedback and review mode", but pronunciation feedback and export aren't built. Structured data (`JsonLd.tsx`) also advertises a US$6.99 offer to search engines. | `landing/components/Pricing.tsx:81–91`, `landing/data/faq.ts`, `landing/components/JsonLd.tsx:54–70`, `frontend/src/pages/Login.tsx` (no plan handling) | **Blocker.** Product Hunt users will click it, and that breaks trust on day one |
| 2 | **No privacy policy or terms.** `/privacy` returns 404. The app stores email addresses and personal photos and sends photos to a third-party AI vision model (Claude Haiku 4.5, via OpenRouter). We found no account-deletion flow; journal entries can be deleted. | `curl https://linguini-landing.vercel.app/privacy` returned 404; `backend/.env.example` `AI_SCENE_ANALYSIS_PROVIDER`; `backend/app/api/routes/journals.py` (delete route only) | **Blocker.** Photo privacy will be one of the first questions, and many users, directories and app stores expect a policy link |
| 3 | **No support or contact channel.** The FAQ and footer send people to the GitHub repository. There's no email address and no password-reset flow in the app, so a locked-out user has no one to ask. | `landing/components/Faq.tsx:13`, `landing/components/SiteFooter.tsx:30`, `frontend/src/pages/Login.tsx` (no reset) | **Blocker** for a public launch |
| 4 | **Most landing-page photo licences are unconfirmed.** All 11 demo photos come from MIT-licensed theme repositories, but the MIT licence covers the code, not necessarily the photos. Our own credits file records "original photo licence not stated" or "likely Unsplash" for 9 of them, and "verify before launch" for the 2 picjumbo photos. These photos appear in the hero, the demo, the OG images and the gallery. The promo film no longer uses them: it's all Mixkit footage under the Free licence (see [promo-film/CREDITS.md](../videos/promo-film/CREDITS.md)). | `landing/public/photos/credits.json` | **Blocker** for the gallery. **High risk** for the landing page |
| 5 | **App stability and cost under a traffic spike are unknown.** We have no usage history, and we found no error monitoring or analytics in `frontend/` or `landing/`. Every session calls a paid AI vision API, and the backend has rate-limit error handling, which shows limits exist. | `backend/app/ai/model_errors.py`; nothing in `package.json` for analytics or monitoring | **High.** A launch-day outage is the worst possible outcome |
| 6 | **Accessibility hasn't been audited.** We haven't checked keyboard paths, contrast on the pasta palette, screen-reader labels on photo markers, or the fallback when there's no microphone. I-Spy phase 2 has a text input, which helps. | `frontend/src/pages/ISpyPhase2.tsx`, `MicTest.tsx` | Medium |
| 7 | **The "one photo session a day" free limit** is promised on the pricing page. We found no enforcement in the code. That's fine for users, but don't repeat the claim until someone confirms either way. | `landing/components/Pricing.tsx`; nothing found in `backend/` | Medium (copy accuracy) |
| 8 | **Only two languages (Spanish and French from English).** Expect "when is X coming?" in the comments. The FAQ says "Italian is next", so only keep that if it's a commitment. | `landing/data/faq.ts` | Low. Be upfront about it; don't hide it |
| 9 | **No social login.** Email and password only adds friction for Product Hunt visitors. The no-signup demo mostly makes up for it. | App login page | Low |
| 10 | **The app URL setting can silently fall back.** `landing/lib/site.ts` falls back to `http://localhost:5173` if `NEXT_PUBLIC_APP_URL` is missing at build time. The repository audit found it correct in production on 24 September, but one bad deploy would break every CTA. | `landing/lib/site.ts` | Low, but check after every deploy |
| 11 | **No real users or reviews yet.** That's fine for Product Hunt, as long as we don't claim any. Getting 10 to 20 people outside the team through a full session before launch will surface bugs early. | — | Low |

### Must-fix before launch day, ranked

1. **Make pricing honest.** Mark Plus as "Coming soon" with no price button (or keep the price with a "notify me" link), remove "Try Plus free for 7 days", reword the FAQ so pronunciation feedback and review mode are "coming to Plus", and remove the paid `Offer` from `JsonLd.tsx`. On Product Hunt, pricing stays **Free**. *(About half a day.)*
2. **Publish a privacy policy and terms,** at `/privacy` and `/terms` on the landing page, linked from the footer and the app's sign-up screen. Cover what we collect (email, photos, learning history), that photos go to an AI model through OpenRouter (Anthropic's Claude Haiku 4.5 today; summarise OpenRouter's and Anthropic's retention terms), that photos are never shown to other learners, and how to delete an entry or your whole account. If there's no account-deletion button yet, give an email address that handles deletion requests. *(1–2 days, including a team read-through.)*
3. **Add a support email,** such as a shared team inbox, to the FAQ, the footer and the app's login screen, replacing the GitHub link as the contact. Decide how password resets will be handled for launch: build a flow, or handle them manually through support. *(Half a day to 2 days.)*
4. **Replace or confirm every landing-page photo.** The quickest option is our own photos, which also fits the "real places" story. Otherwise, use Unsplash or Pexels photos with the source URL and photographer recorded in `credits.json`. Anything in the Product Hunt gallery, thumbnail or video must be fully cleared. *(1–2 days, including re-marking the object positions for the demo.)*
5. **Launch-day hardening.** Do a full end-to-end rehearsal on phones. Set a spending cap and alerts on the AI provider account and confirm its rate limits. Add uptime and error alerts. Add simple analytics (for example Vercel Web Analytics) to the landing page and the app, so we can measure the launch. *(1–2 days.)*
6. **A quick accessibility pass:** keyboard through the demo, contrast on buttons and word markers, alt text and aria labels on photo markers, and a typed fallback wherever a microphone is needed. *(1 day.)*
7. **Do before launch if there's time:** 10–20 outside testers, and a check on whether the daily free-session limit exists (then fix the copy to match).

Items 1 to 5 are the launch gate. Items 6 and 7 should be done, but they shouldn't move the date.

## Why this launch mode

A pure invite-only Product Hunt announcement would create demand the team cannot immediately satisfy. A fully open app announcement would expose unverified signup links and current placeholder capabilities. Run a **10–20 person supervised beta** with consenting learners first, using access to test the real app. Then launch publicly with the **landing demo open to everyone** and a clearly labeled app availability state: open signup only if the gates pass; otherwise describe the product as a preview/beta, use Product Hunt's availability status, and invite feedback on the demo without promising full access. Do not invent a waitlist or call the landing demo an AI photo analyzer. Product Hunt explicitly supports beta/not-yet-available status, and won't feature a waitlisted product without immediate access. [Posting guide](https://help.producthunt.com/en/articles/479557-how-to-post-a-product)

## Launch goals and definitions

Set final numeric targets after the beta establishes a baseline. Suggested first-launch targets below are **team goals**, not forecasts or externally publishable claims.

| Measure | Target for first 14 days | Definition / source |
| --- | --- | --- |
| Qualified visits | 300 | Unique visits to the landing page from Product Hunt and relevant community links, split by UTM source. Exclude internal testers. |
| Demo activation | 30% of qualified visits | Starts a curated-photo demo and reaches its saved journal ending. Record `demo_started`, `demo_completed` with scene/language only. |
| App signup conversion | 10% of qualified visits, **only if signup is open** | Verified Supabase account and first app page loaded; attribute via first-party anonymous referral/UTM, with consent where needed. |
| First-lesson activation | 50% of new verified learners, **only if app is open** | A learner completes one session. Report both preloaded and uploaded-photo cohorts. |
| D7 learner retention | 20% of first-lesson learners, **only if app is open** | Learner completes a second session on days 1–7 after first completion. Report cohort size and numerator, not just percentage. |
| Feedback loop | 15 substantive reports | A learner describes a task, confusion, bug or useful insight; dedupe and tag by theme. |

Track landing `visit → demo_started → demo_completed → app_cta_clicked → signup_verified → session_completed → second_session_completed`; also track upload failure and session error rates. Keep image contents, raw speech, journal text and email addresses out of analytics events. Use server events for persisted sessions; client events alone may be blocked or duplicated. Review conversion by device, language, source and preloaded-vs-uploaded cohort. Use tagged links such as `?utm_source=producthunt&utm_medium=launch&utm_campaign=linguini_launch`; check that app handoff preserves attribution.

### What to measure on the day

Set this up by T−5. Record a baseline on T−1 and the results at T+1 and T+7.

- **Product Hunt:** upvotes, comments, and the number of *distinct commenters* (a better signal of interest than rank), final daily rank, and whether we were featured.
- **Landing page:** visits from Product Hunt (`utm_source=producthunt` plus the referrer), demo starts, demo completions, and "Start free" clicks.
- **App:** sign-ups, the share of sign-ups who finish a first session (activation), a second session on a later day (D1/D7 return), and journal entries created.
- **Quality:** words unticked or added per photo (a proxy for AI accuracy), error rate, AI cost per session, and uptime.
- **Qualitative:** every feature request and bug, counted and grouped. Also count how many people answered our first-comment question, and what they said.

Aim for learning, not rank. A good result is about 30 thoughtful comments, 100 people who finish a first session, and a clear top-3 list of what to build next.

## Critical path and owner board

Assign one named human to each role before scheduling. A single teammate may hold more than one role, but **incident lead and community responder need separate coverage during peak hours**.

| Due | Owner role | Task / acceptance check |
| --- | --- | --- |
| T−19 to T−14 | Product lead | Choose exact launch promise and audience. Compare landing, app and backend behavior; resolve Plus, AI and pronunciation claims. Decide whether app signup is open or demo-only beta. |
| T−19 to T−14 | Engineer | Set `NEXT_PUBLIC_APP_URL=https://linguini-navy.vercel.app` in the landing deployment, redeploy and prove every CTA reaches the correct route. Confirm production API, Supabase signup/email confirmation, browser permissions, upload and return visit on mobile and desktop. |
| T−14 to T−10 | Beta lead | Recruit 10–20 known learners, ideally beginners/returners in Spanish and French. Observe: understand the pitch, finish demo, sign up, finish a session, return within a week. Record consented feedback and failure counts. |
| T−14 to T−7 | Analytics owner | Instrument and test the funnel above; create a single live dashboard with error rate and source breakdown. Establish baseline from beta. |
| T−14 to T−7 | Marketing owner | Review the listing copy, first comment, gallery, demo video and channel posts in this kit against the actual app. Have two people who did not build Linguini explain the first gallery frame back to the team. Revise once based on confusion. |
| T−10 to T−5 | Maker / Product Hunt owner | Use an established **personal** Product Hunt account, complete onboarding, create a draft, add makers and preview the listing. New accounts require onboarding and may need a week before posting. Select only relevant topics. [Posting guide](https://help.producthunt.com/en/articles/479557-how-to-post-a-product) · [Before launch](https://www.producthunt.com/launch/before-launch) |
| T−7 to T−3 | Outreach owner | Build a consent-aware contact sheet: name, channel, relationship, relevance, planned asset, status and owner. Ask collaborators and beta testers for candid feedback; prepare personalized, unsent notes for creators and moderators. |
| T−3 to T−1 | Incident lead | Freeze launch copy/assets, record links to dashboard, deployment, rollback, logs, support inbox and status page. Run a load check and backup/recovery check appropriate to expected traffic. Create a duty roster spanning the Pacific launch day. |
| T−1 | Product lead | Run go/no-go below. Schedule Product Hunt post only after all hard gates pass. Make a screenshot of the final listing preview for team sign-off. |

### Launch-day roles (4 people)

| Role | Who | Owns |
|---|---|---|
| **A: Launch lead / voice** | Poster of the launch | First comment. Replies to Product Hunt comments on the day shift. Final say on tone |
| **B: Night voice** | Maker | Replies to Product Hunt comments during the US daytime (our night) |
| **C: Outreach** | Maker | Social posts, personal messages, email, community posts. Also watches Product Hunt for questions to route |
| **D: Product on-call** | Maker | App and API health, the AI provider's quotas and costs, hotfixes, and the status of any bug a commenter reports |

Everyone replies to comments when free, but A or B signs off on anything about privacy, pricing or accuracy.

## Tasks

T− counts are days before a Saturday 17 October launch. If the date changes, keep the T− counts and move the dates.

### Three weeks out (by 26 Sep)

- [ ] Agree the promise: beta testers until 16 Oct, open to everyone on launch day
- [ ] Point every landing-page button at the production app, then tap each one on a phone
- [ ] Make every landing claim match the app today: photo analysis, speech, Plus trial
- [ ] Track demo started, demo finished, sign-up, first lesson, second lesson

### Two weeks out (by 3 Oct)

- [ ] Read the [readiness audit](#current-readiness-audit-24-september-2026) together and assign an owner to every must-fix item. The launch date depends on items 1 to 5.
- [ ] **Hunter:** self-hunt. Our launch lead posts from their **personal** Product Hunt account, and the other three are added as makers. We don't use a hunter: Product Hunt says a hunter gives no advantage, and paying one breaks the rules.
- [ ] All four of us make or update personal Product Hunt accounts: a real photo, a headline like "Student at NUS · building Linguini", and a finished onboarding. Product Hunt suggests joining months ahead. We can't do that, so from today we each use the site properly: upvote and comment on launches we genuinely like. Don't join vote-swap groups.
- [ ] Write the launch date in the team calendar in **both** time zones: "Sat 17 Oct, 00:01 PDT = 15:01 SGT".
- [ ] Recruit 10 to 20 beta testers learning Spanish or French
- [ ] Watch five of them use it cold. Fix whatever confused two or more
- [ ] Product-side fixes start (T−12): Plus marked "Coming soon" and the "Try Plus free for 7 days" button removed (must-fix 1); draft the privacy policy and terms (must-fix 2); support email on the landing FAQ and footer, replacing the GitHub link (must-fix 3).
- [ ] Assets (T−10): gallery images at 1270 × 760, following the captions in [listing.md](listing.md#gallery), each checked at phone size; 240 × 240 thumbnail, a PNG or a gentle GIF under 3 MB; every photo in the gallery and video our own or with a confirmed licence (must-fix 4).
- [ ] Upload the chosen listing video to YouTube as *unlisted* and keep the full URL. For the explainer, upload `marketing/media/export/explainer.mp4` with `explainer.srt`. For the promo film, render [`marketing/videos/promo-film/`](../videos/promo-film/) (30 s) and upload `out/linguini-launch-master.mp4` with the title and description from `VIDEO.md`. See the video decision in [listing.md](listing.md#video).
- [ ] Draft the listing on a personal Product Hunt account and add every maker

### One week out (by 10 Oct)

- [ ] Product Hunt teaser, done the current way (T−9): Coming Soon pages no longer exist. Create the Linguini **product forum thread** instead, with one post: what we're building, one gallery image, and "we're launching on [date], and we'd love your feedback on the demo". Link the demo.
- [ ] Soft teaser on our own channels (a personal LinkedIn or X post): "We're launching Linguini on Product Hunt on [date]." No upvote asks.
- [ ] Swap in the X header and LinkedIn cover (`marketing/media/export/banners/`)
- [ ] Reread the rules of every community below; message the r/Spanish mods
- [ ] Personal note to Lindie Botes and ten smaller language creators, with no ask to post
- [ ] Ask NUS Hackers for a Friday Hacks demo slot (active@nushackers.org)
- [ ] Create the **draft** in the Pre-Launch Dashboard and paste everything from [listing.md](listing.md).
- [ ] Preview it on desktop and phone. Check that the description isn't cut off, the captions read in order, and both links open, including with Product Hunt's own `ref` parameter.
- [ ] Schedule the listing for Sat 17 Oct, 00:01 Pacific. Screenshot the confirmation page showing the date.
- [ ] Check again in the dashboard: is there a public "Upcoming" page or a "Notify me" link? If there is, add it to the T−3 messages.

### Five days out (Mon 12 Oct): full rehearsal

- [ ] Each of us does a fresh sign-up on a phone we don't normally use: sign-up, then a photo, word review, a full session, and the journal entry. Log every bug.
- [ ] Load check: can OpenRouter and the five chosen models handle a spike, say 200 sessions in an hour? Check rate limits, the credit balance, spending caps and billing alerts on the OpenRouter account (must-fix 5). The model comparison saw OpenRouter throttle Mistral Small, which is one reason translation runs on GPT-4o-mini.
- [ ] Turn on error alerts, such as Vercel logs and an uptime ping on the app and API, so D gets notified.
- [ ] Add analytics (Vercel Web Analytics or similar) to the landing page, so we can measure [what's listed above](#what-to-measure-on-the-day).

### Three days out (Wed 14 Oct)

- [ ] Countdown post (`countdown-1080x1080.png`) and story (`ig-story-countdown-1080x1920.png`)
- [ ] Write a personal list of the people and groups who would care: classmates, CS3216 alumni, language clubs, friends learning Spanish or French. Aim for a handful of real conversations, not a blast.
- [ ] Tell friends and testers the date, and ask who wants a message on the day. Heads-up text: "We launch on Saturday at 3 pm SGT. Here's the demo if you want a sneak peek." Include the demo link and no upvote ask.
- [ ] Finalise [social-posts.md](social-posts.md) and fill in the date.
- [ ] Write the duty rota: afternoon, night and morning shifts in Singapore time

### Day before (Fri 16 Oct)

- [ ] Go or no-go (below): buttons work, a stranger can sign up, analytics arrive, inbox staffed, someone can roll back
- [ ] Freeze the copy and the assets. No edits after this
- [ ] **Code freeze** on app and landing from noon SGT. Hotfixes only.
- [ ] Walk through the scheduled post in the dashboard one last time.
- [ ] Switch the YouTube video from unlisted to public.
- [ ] Put the first comment in a shared doc, ready to paste.
- [ ] Sleep plan: B and D (the night shift) sleep in the afternoon on launch day, not the night before.

### Launch day (Sat 17 Oct, 15:01 SGT)

- [ ] First comment up within a minute of going live
- [ ] X thread, Instagram post and story, LinkedIn out by 15:10
- [ ] Every Product Hunt comment answered within the hour
- [ ] Hourly check of errors, sign-ups and demo completions

## Go / no-go at T−1

**All must pass:** (1) every production CTA reaches a usable destination; (2) a new person can sign up, verify email if required, complete the advertised path and return; (3) public copy, pricing and beta status match behavior; (4) analytics events and error monitoring arrive live; (5) support inbox and two launch-day responders are staffed; (6) gallery assets render and have rights/credits; (7) a rollback/redeploy owner is available. If any fail, keep the Product Hunt draft and do a smaller preview with known testers. Reschedule rather than push traffic into a broken journey.

Launch only if every answer is yes:

- [ ] Nobody can find a "buy" or "trial" button for Plus anywhere on the landing page or in the app.
- [ ] `/privacy` and `/terms` are live and linked from the landing footer and the app's sign-up screen.
- [ ] A support email is on the landing page, and someone checks it on launch day.
- [ ] Every image in the Product Hunt gallery, thumbnail and video has a confirmed licence or is our own.
- [ ] Two fresh sign-ups on different phones completed photo → words → session → journal on the day before launch.
- [ ] The AI provider has credit, a spending cap and alerts. Uptime and error alerts go to D.
- [ ] Analytics are recording on the landing page and in the app.
- [ ] The Product Hunt post is scheduled for the agreed date and previewed, and the first comment is ready to paste.

## Launch-day runbook (Singapore time, Saturday into Sunday)

Product Hunt's day begins **15:01 SGT / 00:01 PDT**. Replace times if the date changes across a daylight-saving boundary. Schedule the Product Hunt draft; do not rely on a manual race to publish. Product Hunt recommends self-posting with a personal account, a first comment and a direct product URL. [Posting guide](https://help.producthunt.com/en/articles/479557-how-to-post-a-product)

### Timeline

| Time SGT | Owner | What happens |
| --- | --- | --- |
| 14:00 | Incident lead + product lead | Check landing/app/API health. Fresh sign-up on a phone. Tap every landing button. Open logs, traffic and support dashboards. Confirm CTA and pricing state. |
| 15:01 | Maker / PH owner | Listing goes live on schedule. Post the first comment. Check gallery, video and that the primary link opens the correct landing page. Claim/request Product Page management. |
| 15:10 | Outreach | One-to-one messages to people who asked to hear. X thread, Instagram post and story, LinkedIn. Share the direct post link and invite visits, comments and feedback. **Never ask for upvotes or coordinate fake engagement.** [Launch guide](https://www.producthunt.com/launch) |
| 16:00–19:00 | Community | Answer every Product Hunt comment within the hour, with product facts and concrete examples. Post in r/SideProject, the r/Spanish weekly thread and Discord promo channels, only where rules permit self-promotion, with a discussion prompt tailored to that community. |
| 15:00–next day 15:00 | Incident lead | Check error rate, signup, demo completion and support queue at least hourly during high traffic; triage P0/P1 immediately. Keep an incident log and rollback decision. Rotate responders for overnight Pacific hours. |
| 21:00 | Community | 9am Saturday on the US east coast. Second Instagram story. Reply to the new wave. |
| 01:00 | Incident lead | Hand over to one responder and one engineer on call. |
| 08:00 | Product lead | Check errors, sign-ups, demo completions. Second nudge in NUS class chats. |
| 14:59 | Everyone | Day ends. Screenshot numbers, thank commenters, list what broke. |
| Sun 15:00 | Product lead | Short retro. Capture traffic, activation, support themes and defects; thank contributors; publish an honest update and assign next fixes. |

### Hour by hour with four people (SGT, with PT)

Written for the 14 October option; the clock times are the same for 17 October (both are on PDT), so the day names below are for 17 October.

> **Open decision: overnight handover.** The timeline above hands over once at 01:00 SGT. This rota uses two handovers, at 23:30 and 07:30 SGT. Pick one when writing the duty rota.

| SGT (Sat 17 → Sun 18) | PT (Fri 16 → Sat 17) | Who | What |
|---|---|---|---|
| **14:30 Sat** | 23:30 Fri | A, C, D | On a call. D confirms app, API, landing and demo are up and the OpenRouter account has credit. |
| **15:01** | 00:01 Sat | A | Launch goes live. **Post the first comment within the minute.** Open the page logged out and check the gallery, links and video. |
| 15:05 | 00:05 | C | Personal messages to the T−3 list, the Telegram/WhatsApp text, and the email to friends. Everything asks people to *try it and comment*. |
| 15:15 | 00:15 | A, C | X thread and personal LinkedIn posts go out from team members' own accounts. |
| 15:00–18:00 | 00:00–03:00 | A | Reply to every comment within about 15 minutes. |
| 15:00–18:00 | 00:00–03:00 | D | Watch error logs and sign-ups. Post updates in the team chat every 30 minutes. |
| 16:00 | 01:00 | C | Europe is waking up (10:00 CEST). Share in language-learning communities we're **already active in**, following each community's rules. |
| 18:00 | 03:00 | D, then B | D goes to sleep. **B wakes and takes on-call** until D returns. |
| 18:00–21:00 | 03:00–06:00 | A, C | Replies. Reshare to friends in Europe. Instagram/TikTok post. |
| 21:00 | 06:00 | C | US East Coast 09:00. Reply to our own X thread with a short GIF of a session. |
| **23:30** | 08:30 | A → B, C → D | **Handover:** A writes a 5-line summary (open questions, bugs, anything sensitive). A and C sleep. B takes voice, D takes on-call. |
| 23:30–03:00 Sun | 08:30–12:00 | B, D | US morning is the busiest part of the Product Hunt day. B replies to every comment. D fixes anything that blocks sign-up or a session. |
| 03:00–07:00 | 12:00–16:00 | B, D | Replies continue. Only ship a hotfix if it's safe to roll back. |
| **07:30** | 16:30 | B → A, D → C | **Handover.** B and D sleep. A and C take over. |
| 07:30–14:59 | 16:30–23:59 | A, C | US evening and Asia morning. Reply to late comments. C shares once more with Singapore and NUS channels (at breakfast and lunchtime). |
| **14:59 Sun** | 23:59 Sat | All | Product Hunt day ends. |
| 15:00 | 00:00 | A | Thank-you comment on the launch thread saying what we heard and what we'll fix first. |

### Incident policy

If sign-up or lesson completion breaks for more than a few people: stop outbound posts, put an honest availability note on the landing page, route visitors to the working demo, and fix/redeploy with the incident lead. Do not silently funnel users to an error state. The Product Hunt launch dashboard provides comments and performance tracking, and the permanent Product Page should be claimed for follow-up. [Launch-day duties](https://www.producthunt.com/launch/launch-day-duties)

## Distribution

The strongest asset is a **short, real screen recording** of a curated photo going from words to I-Spy to a journal page, with captions and a clear demo label. Pair it with the gallery images and written copy in this kit. Every channel should lead to the same Product Hunt post on launch day, while the Product Hunt primary link leads to the landing page. Preserve the specific communities' posting rules and adapt the opening question; do not dump one identical announcement everywhere.

| Priority | Channel | Angle / ask | Owner action |
| --- | --- | --- | --- |
| 1 | Team's friends, classmates, former project testers and language-learning contacts | “Try a five-minute Spanish/French photo lesson and tell us where you got stuck.” | Ask individually for honest use and comments, without upvote requests. Secure permission before naming anyone. |
| 1 | Existing social accounts: Instagram Reels/Stories, TikTok, X, LinkedIn and Facebook | 15–30 second visual lesson loop, one scene and one word; carousel or short post links to demo. | Record native aspect ratios; use an actual app/demo capture; post launch link and answer replies. |
| 2 | Language-learning communities on Reddit, Discord and Facebook | Ask whether learning from one's own surroundings helps word recall; show an example and invite critique. | First identify active communities and read each rule/mod guidance. Post only in feedback or showcase spaces where allowed; participate before asking attention. |
| 2 | Student, campus, maker and education communities | A student-built language-learning experiment and what testers taught the team. | Ask organizers/moderators to approve a relevant showcase; offer a short live demo. |
| 2 | Micro-creators: language tutors, study accounts, travel photographers, “learn Spanish/French” creators | Offer a test session and ask for independent feedback if it fits their audience. | Curate 10–15 relevant creators by audience fit, not follower count; make no scripted endorsement or paid upvote arrangement. |
| 3 | Hacker News `Show HN`, Indie Hackers and maker forums | Product and implementation story, framed honestly as an interactive prototype/beta. | Use only when there is a working product and a technical/product insight; answer questions rather than cross-posting a sales blurb. |

Do not assume an influencer or community has agreed to post. The outreach sheet must record a confirmed response before any coordinated mention. Product Hunt permits sharing a launch link, but prohibits direct upvote requests; paid promotion of hunters or artificial engagement can result in removal. [Launch guide](https://www.producthunt.com/launch) · [Before launch](https://www.producthunt.com/launch/before-launch)

Sizes and rules checked 24 September 2026. Recheck each the week before; subreddit rules below came from a mirror because Reddit blocked our fetches. The [r/Spanish weekly self-promotion thread](https://www.reddit.com/r/Spanish/comments/1wl7pbz/weekly_selfpromotion_mega_thread/) explicitly accepts language-learning apps; post one honest comment in the *current* weekly thread. [r/languagelearning](https://www.reddit.com/r/languagelearning/comments/1u537kp/announcement_we_are_tightening_the_rules_around/) requires moderator permission for promotion outside its “Share your resources” thread and clear labeling. [Show HN](https://news.ycombinator.com/showhn.html) is suitable only when visitors can try the working project; its guidelines reject a landing page or signup-only pitch and prohibit soliciting votes. Use team members' existing Discord, campus and creator relationships only after identifying a relevant space and its posting policy.

### People who know us (first)

- [ ] Friends and classmates, one message each
- [ ] Beta testers
- [ ] CS3216 cohort chat

### Communities

- [ ] r/SideProject — self-promotion allowed; lead with how we built it
- [ ] r/languagelearning (3.4M) — resources thread only, or mod permission
- [ ] r/Spanish — weekly self-promotion thread; message mods first
- [ ] Discord: Refold Central (~37k), Language Learning Community (~34k), Language Cafe (~28k) — promo channels only
- [ ] Indie Hackers — one Show IH post, framed as a request for feedback
- [ ] NUS Hackers Friday Hacks — speaker slots until 13 Nov
- [ ] r/French: no advertising, so ask the mods for one feedback post
- [ ] HelloTalk: bans promotion, so share our own journal pages in Moments as learners
- [ ] Show HN: live demo with no sign-up wall, no vote requests

Not posting: Tandem (no public feed).

### Creators (personal note, no ask to post)

- [ ] Lindie Botes — YouTube ~357k; reviews language apps, UX designer, worked in Singapore
- [ ] Xiaomanyc — YouTube ~7.1M; speaks to strangers, closest fit to speak-first
- [ ] Matt vs Japan / Refold — comprehensible input
- [ ] Ten smaller tutors and study accounts (under 50k), chosen by audience fit

Not asking: Steve Kaufmann (founded LingQ) and Ikenna (runs Fluyo), both competitors.

### Newsletters (one short pitch each on launch day)

- [ ] The Rundown AI — 2M+, "tool of the day"
- [ ] TLDR AI — ~1.1M
- [ ] Ben's Bites — ~120–170k, submittable news feed

## Assets

Paths are relative to `marketing/media/` unless noted. Gallery and video choices are open decisions in [listing.md](listing.md).

| File | Use |
| --- | --- |
| `export/01…04-*.png` | Product Hunt gallery option A (illustrative), 1270 × 760 |
| `marketing/product-hunt/gallery/01…06-*.png` | Product Hunt gallery option B, 1270 × 760 (`@2x` versions alongside) |
| `export/product-hunt-icon-240.png` | Product Hunt thumbnail option A |
| `marketing/product-hunt/gallery/thumbnail.png` / `thumbnail.gif` | Product Hunt thumbnail option B |
| `export/explainer.mp4` + `.srt` | Listing video option, 50 s |
| `export/banners/x-header-1500x500.png` | X profile header from T−7 |
| `export/banners/linkedin-1584x396.png` | LinkedIn cover |
| `export/banners/launch-card-1200x630.png` | Link previews on the day |
| `export/banners/countdown-1080x1080.png` | T−3 feed post |
| `export/banners/ig-story-countdown-1080x1920.png` | T−3 story |
| `export/banners/ig-post-1080x1350.png` | Launch-day Instagram post |
| `export/banners/ig-story-1080x1920.png` | Launch-day story, link sticker in the clear area |
| `export/social-square.png` | Carousel slide 2 |
| `marketing/product-hunt/gallery/og-social-1200x630.png` | Social card |

Regenerate banners with `python3 marketing/media/banners.py`. The launch date is one constant (`LAUNCH`) at the top.

## After launch

- [ ] Swap `[PH_POST_URL]` into every post, and add the Product Hunt badge to the landing page
- [ ] T+1: keep replying until the Product Hunt day ends at 14:59 SGT. Late comments still deserve answers.
- [ ] T+1, 15:00 SGT: post a short thank-you with what we learned. Don't mention rank.
- [ ] T+1: put every piece of feedback into one list, tagged bug / feature / copy / question.
- [ ] D+1: fix the onboarding bugs people hit on the day
- [ ] T+2: fix the top 3 bugs raised on launch day, then reply in those threads to say they're fixed.
- [ ] T+2: write a retro using the numbers above. What would we change for the next launch?
- [ ] T+2: email everyone who left an email or a detailed comment and thank them personally.
- [ ] D+3: talk to five people who came back and five who didn't
- [ ] D+7: look at who did a second lesson; fix the biggest drop-off
- [ ] D+14: publish what we learned, with the real numbers
- [ ] Put the next launch on the calendar: speaking feedback

## Retention and next announcement

The first week should help learners experience the **second** useful lesson. At session completion, give one clear next step: save a journal line and choose tomorrow's scene. If consent and messaging infrastructure exist, send one helpful day-two reminder tied to their chosen language; offer an easy unsubscribe. Do not build a generic daily email blast around an unverified streak claim. Give people a way to report a wrong word or confusing lesson from the experience itself.

At **D+1**, fix broken onboarding or upload flows and reply to every substantive Product Hunt comment. At **D+3**, interview five activated and five stalled users, comparing what they expected with what the demo/app delivered. At **D+7**, review first lesson, second lesson, D7 retention, language and source cohorts; choose the largest drop-off to fix. At **D+14**, publish a small “what we learned / what changed” update with actual numbers and caveats, continue Product Page replies, and put the next product release on the calendar. Product Hunt recommends following up with users, using feedback and maintaining the Product Page after the launch day. [Post-launch guide](https://www.producthunt.com/launch/days-after-launch)

Candidate next announcement, conditional on shipping: **speaking feedback**, promoted only once speech evaluation is truly available. The learner app already reads your own photos with AI, so that is part of launch one. Product Hunt supports launching significant new iterations ("for significant product iterations"), not repeated copies of the same listing. [Launch guide](https://www.producthunt.com/launch)

## Product Hunt rules: what we verified (24 September 2026)

| Topic | What Product Hunt says | Source |
|---|---|---|
| Tagline | "max 60 characters" | [Launch Guide: Preparing for launch](https://www.producthunt.com/launch/preparing-for-launch) |
| Description | 260 characters in the Help Center; "max 500 characters" in the Launch Guide. **We use ≤260. Check the counter in the form** | [Help Center: How to post a product](https://help.producthunt.com/en/articles/479557-how-to-post-a-product), Launch Guide |
| Name | Product name only, "no description or emojis". No character limit published, **so check it in the form** | Help Center |
| Primary URL | Should be direct | Help Center |
| Thumbnail | Square, 240×240 recommended, GIF allowed, under 3 MB, not "overly animated" | Help Center, Launch Guide |
| Gallery | 1270×760 recommended; at least 2 images | Help Center, Launch Guide |
| Video | YouTube only, full non-private URL, no short links; no direct video file uploads. About 53% of Product of the Day winners since 2021 had a video | Launch Guide, Help Center |
| Launch tags | "Topics" were renamed "Launch Tags" in October 2025. Choose "up to 3" | Launch Guide; [Product Hunt release notes](https://releasebot.io/updates/product-hunt) |
| Tags exist | Education, Languages, Artificial Intelligence and Photography topic pages are all live. "Language Learning" is a *category* | producthunt.com/topics/…, /categories/language-learning |
| Pricing | Free / Paid / Paid (with a free trial or plan) | Launch Guide |
| First comment | "70% of products who achieved Product of the Day, Week, or Month had a first comment by the maker" | Launch Guide |
| Launch time | "12:01 am Pacific Time is the best time to launch for makers that are planning ahead". Scheduling is by day and goes live at midnight PT (September 2025 change) | [Launch Guide](https://www.producthunt.com/launch), release notes |
| Scheduling | Up to 30 days ahead. A scheduled post is not indexed and can't be upvoted until launch, and you can still edit it under "My Products" | [Help Center: How to schedule a post](https://help.producthunt.com/en/articles/2724119-how-to-schedule-a-post) |
| Drafts | "Create Draft" and a Pre-Launch Dashboard replaced "Launch Now" in September 2025 | Release notes |
| Coming Soon / teaser pages | **Discontinued in August 2025.** Product forum threads replaced them for "updates" and "teasers" before launch. The old Help Center teaser article now returns 404 | [PH forum thread](https://www.producthunt.com/p/general/product-hunt-discontinued-coming-soon-teaser-pages-did-they-work-for-you), release notes |
| Hunter vs self-hunt | "We encourage makers to hunt their own products, and there's no discernible advantage to using a third-party hunter." "79% of featured posts were by makers who self-hunted." Paying a hunter is against the guidelines | [Launch Guide](https://www.producthunt.com/launch), [Before launch](https://www.producthunt.com/launch/before-launch) |
| Accounts | Personal accounts only. "Company accounts cannot hunt or post products"; new accounts must finish onboarding first | Help Center |
| Upvotes | "You cannot ask people directly to upvote your product. Instead, ask them to visit and comment." Contests that reward upvotes can get the launch unfeatured | [Sharing your launch](https://www.producthunt.com/launch/sharing-your-launch) |
| Featuring | Judged on Useful, Novel, High Craft and Creative. Not featured: waitlisted products without immediate access, products that aren't live, "vaporware" | [Featuring guidelines](https://help.producthunt.com/en/articles/9883485-product-hunt-featuring-guidelines) |

Not verified (check on the day): whether scheduled launches appear publicly in an "Upcoming" list with a "Notify me" button. Third-party guides say they do, but Product Hunt's own pages don't say so. Check the Pre-Launch Dashboard after you schedule.

### Do and don't

**Do**
- Self-hunt from a personal account, and add all four makers.
- Post the first comment right at launch.
- Share the Product Hunt link anywhere, and ask people to *visit, try the demo and comment*.
- Reply to comments quickly and honestly, including the critical ones.
- Share in communities we're already part of, following their rules.
- Say plainly what isn't built yet (billing, pronunciation feedback, more languages).

**Don't**
- Ask anyone to upvote, whether in DMs, group chats, email, social posts, or as a joke.
- Run contests or giveaways tied to upvotes. Product Hunt says that can get a launch unfeatured.
- Pay for a hunter, upvotes or comments, or join upvote-swap groups.
- Use a company or brand account to post or hunt. Product Hunt doesn't allow it.
- Send the same message in bulk to hundreds of people or to scraped contacts.
- Tell friends to make new Product Hunt accounts just to support us. Brand-new accounts appearing together looks like manipulation.
- Claim users, reviews, ratings or awards we don't have, or suggest that Plus can be bought.
- Use a waitlist: Product Hunt won't feature one.

# Linguini frontend

React 19, TypeScript and Vite frontend for Linguini, the CS3216 final project for
Group 3. The same build serves the learner app and the public marketing site.
The FastAPI backend runs separately under `/api/v1`.

## Run locally

Use Node.js 24 (the CI version), or Node.js 22.19+ on the Node 22 line. From `frontend/`:

```sh
npm ci
cp .env.example .env.local
npm run dev
```

Edit an existing `.env.local` rather than replacing it. Configure:

| Variable | Purpose |
| --- | --- |
| `VITE_API_BASE_URL` | API origin without `/api/v1`; normally `http://127.0.0.1:8000` |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | Public Supabase authentication configuration |
| `VITE_GOOGLE_CLIENT_ID` | Optional public Google OAuth web client ID |
| `VITE_SITE_URL` | Canonical public site URL for metadata and generated site files |
| `VITE_SUPPORT_EMAIL` | Public support contact |
| `VITE_GA_MEASUREMENT_ID` | GA4 measurement ID; see [analytics](../ANALYTICS.md) |
| `VITE_PRODUCT_HUNT_URL`, `VITE_PRODUCT_HUNT_POST_ID` | Optional Product Hunt links |

See [`.env.example`](.env.example) for all public settings. Only public
configuration belongs in Vite variables; provider credentials and database URLs
belong on the backend. Restart Vite after changing environment variables.

The development server normally opens at `http://localhost:5173`. Start the backend
using [its setup guide](../backend/README.md), with that exact origin in
`CORS_ALLOWED_ORIGINS`. Development route guards allow local iteration, while the
backend still enforces its configured authentication mode. Production learner
routes require a Supabase session.

## Photo capture

“Click” / “Open camera” opens a live camera preview on laptops and phones. “Take
photo” captures a JPEG and sends it through the existing photo upload flow; Cancel
or Escape closes the preview. Camera tracks stop on capture, cancellation, or
navigation, including when permission arrives after the preview closes.

No camera environment variables or API keys are needed. Browsers require HTTPS
(or localhost for development), an available camera, and the user's permission.
Plain HTTP on a LAN address does not provide browser camera access. The existing
in-app Camera preference still controls whether the camera button is enabled.
Permission, missing-device, and device-in-use errors explain how to recover;
Upload remains available for choosing an existing image.

## Vocabulary review

Teaching cards are grouped into Objects, Adjectives, then Relations, with a heading
and position within each section. Previous, Next, and swipe navigation follow that
order. Quiz and typing order and saved answer identities are preserved.

During the object section, photo markers select their matching card and play its
target-language pronunciation using the existing language-pack voice settings.
Repeated instances retain their own markers. Adjective and relation cards highlight
associated objects when supplied, with speaker controls for pronunciation. The
photo stays visible throughout review. Marker buttons support keyboard activation;
word cards remain readable when browser pronunciation is unavailable.

## Scene processing progress

Scene analysis shows four stages: loading the photo, finding objects, checking
results, and saving the review. The backend reports these milestones through the
existing session polling response (`sceneAnalysisProgress`). Completed segments
fill solidly; the active segment pulses, with reduced-motion support. Counts
represent completed stages, never a percentage of elapsed or remaining time.
Elapsed time uses the backend's processing start timestamp and survives refresh.
The bar sits above the photo, with only the current stage and elapsed time visible;
stage counts remain available to screen readers.

After confirmation, a separate two-stage bar tracks translation and preparation
of the first vocabulary task using committed session data. Older backend responses
without analysis milestones show an indeterminate state. Polling pauses retain
the last milestone and offer Check again; failures retain the existing retry flow.
No additional environment variables are required.

## Structure

| Path | Purpose |
| --- | --- |
| `src/App.tsx` | Learner route definitions and route guards |
| `src/marketing/` | Public home, blog, language, legal and share pages |
| `src/pages/` | Learner screens |
| `src/components/` | Shared controls, shells, scene and media renderers |
| `src/lib/` | API client, query keys, analytics and browser speech helpers |
| `src/state/` | Authentication, server queries and practice hooks |
| `src/data/types.ts` | Frontend domain types |
| `src/styles/` | Global styles and design tokens |
| `tests/` | Frontend behavior tests |
| `public/` | Bundled photos, brand assets and marketing media |
| `scripts/` | SEO checks, exports and marketing utilities |

The frontend uses Supabase for authentication and TanStack Query for server state.
Profiles, sessions, grading, learning evidence, rewards and journals persist on the
backend. Use `src/lib/api.ts` for requests and `src/lib/queryKeys.ts` for cache keys.
Keep account and language boundaries when reading or invalidating learner data.

## Routes

[`src/App.tsx`](src/App.tsx) is the source of truth for learner routes.

| Route | Screen |
| --- | --- |
| `/login`, `/reset-password`, `/onboarding` | Sign-in, account recovery and learner setup |
| `/demo` | Public bundled-content demonstration |
| `/contact` | Support form |
| `/home`, `/practice` | Home and photo/scene selection |
| `/practice/sessions/:sessionId/analysis` | Resumable scene analysis and fact review |
| `/practice/sessions/:sessionId/learn` | Lesson overview and vocabulary |
| `/practice/sessions/:sessionId/learn/:taskId` | Individual lesson task |
| `/practice/sessions/:sessionId/ispy-1`, `ispy-2` | Two-way I-Spy within a lesson |
| `/practice/sessions/:sessionId/summary` | Session results |
| `/ispy`, `/ispy/play`, `/ispy/challenge`, `/ispy/friends` | Standalone I-Spy, daily challenge and friends lobby |
| `/ispy/games/:sessionId/clues`, `describe`, `results` | Standalone game stages |
| `/rooms/:roomId` | Private friend challenge |
| `/progress`, `/vocabulary` | Learning progress and saved vocabulary |
| `/journal`, `/journal/new`, `/journal/:entryId` | Journal history, creation and detail |
| `/profile`, `/profile/edit`, `/payment` | Account, preferences and billing |

Catalog links under `/practice/:sceneId/*` resolve through `SceneRoute` into a
session. Use `src/lib/sessionRoute.ts` to choose the correct resume destination.
The `/rooms` route preserves existing invitation links and redirects to the
friends lobby.

## Marketing and deployment

`src/main.tsx` selects the learner or marketing root from the URL. The roots
lazy-load separate global stylesheets. `vercel.json` rewrites routes to the Vite
entry point, so refreshes work on both parts of the site. The API is a separate
deployment; see the [root README](../README.md).

Static Open Graph cards live in `public/og/`; replacements should be 1200×630 PNGs.
SEO verification and IndexNow settings are listed in `.env.example`. Source files
and regeneration steps for launch media live in [marketing/](../marketing/README.md).

## Checks and conventions

```sh
npm run lint
npm test
npm run build
npm run preview
```

`lint` runs Oxlint; `test` uses the Node test runner; `build` typechecks and writes
production assets to `dist/`. `preview` serves an existing build.

Read [AGENTS.md](AGENTS.md) and [design.md](design.md) before UI changes. Reuse shared
controls and media components, preserve loading and retry states, and instrument
interactive features with `trackAction`. Document events in
[ANALYTICS.md](../ANALYTICS.md). Repository skills are indexed in
[docs/skills.md](../docs/skills.md).

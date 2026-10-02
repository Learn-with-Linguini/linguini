# Linguini

<p align="center">
  <img src="frontend/public/linguini-logo.png" alt="Linguini logo" width="180" />
  <img src="frontend/public/linguini-wordmark.png" alt="Linguini wordmark" width="360" />
</p>

<p align="center"><strong>Learn the language of your day</strong></p>

**Live application:** [Open Linguini](https://linguini-navy.vercel.app/) &nbsp;·&nbsp; **Landing page:** [linguini-landing](https://linguini-landing.vercel.app)

## Group members

| Matriculation number | Name | GitHub | Contribution to the assignment |
| --- | --- | --- | --- |
| `A0312075N` | `Jain Ananya` | [@ananyaj1515](https://github.com/ananyaj1515) | `Idea, Branding, Frontend (UI/UX), AI Core Tech, Pitch` |
| `A0286908L` | `Govindaraj Roshni Daksha` | [@roshnidaksha](https://github.com/roshnidaksha) | `Backend API, Database, AI Core Tech` |
| `A0307648W` | `Madrid Lim` | [@StarlightsJourney](https://github.com/StarlightsJourney) | `Landing Page, Marketing, User Analytics, Evaluation Dataset` |
| `A0310636M` | `Shamit Gupta` | [@ShamitGupta](https://github.com/ShamitGupta) | `AI Model Analysis, OpenRouter Integration` |

## What Linguini is

Most language apps teach a fixed syllabus of words you may never use. Linguini starts
from a photo of your own day: take or upload a picture, and the app finds the objects in
it, teaches the words for them in your target language, and then quizzes you on the
scene by having you describe it. The day ends as a journal entry, so your vocabulary
history doubles as a diary of what you actually did.

## How a session works

1. **Onboarding** — pick your native and target language and a proficiency level; this
   language profile filters every scene, word and progress figure afterwards.
2. **Capture** — choose a preloaded scene or upload/capture your own photo. Uploads go to
   a private Supabase Storage bucket, are validated and moderated server-side, and become
   a `MediaAsset`.
3. **Analysis & review** — the backend detects candidate objects in the image and saves
   them as a resumable draft. You confirm, remove or add objects before the lesson is
   built, so you control what you are taught.
4. **Learn** — word cards for each confirmed object: translation, article and gender, and
   example usage.
5. **I-Spy** — two-way description practice. Phase 1: Linguini describes an object and you
   pick it out of the scene. Phase 2: you write your own clue for a target word and
   Linguini guesses what you meant.
6. **Summary & journal** — XP, new and reviewed words and streaks are persisted, and the
   session is written into your journal, which supports revisions and photo attachments.

## Features

- Photo-led lessons from your own camera roll, plus curated preloaded scenes.
- Description-led practice in both directions: comprehend Linguini's clues, then write
  your own and have them checked.
- Vocabulary list with per-word progress, encounters and spaced review signals.
- Journal with daily entries, edits and image attachments.
- Progress dashboard: XP, streaks, words learned per language.
- Multiple language profiles per user; switching a profile re-scopes the whole app.
- Supabase authentication with a local `demo` auth mode for development.
- Server-side content moderation and image validation on every upload.

## Screenshots

Captured from the running app (phone width) against the live database.

| Home | Capture a scene | Learning tasks |
| --- | --- | --- |
| <img src="docs/screenshots/home.png" alt="Home screen with streak, XP and the next practice card" width="240" /> | <img src="docs/screenshots/practice.png" alt="Scene capture screen with camera, upload and ready scenes" width="240" /> | <img src="docs/screenshots/learn.png" alt="Learning tasks screen with the scene photo and its translations" width="240" /> |

| Vocabulary | Journal | Profile |
| --- | --- | --- |
| <img src="docs/screenshots/vocabulary.png" alt="Vocabulary screen grouped by the scenes the words came from" width="240" /> | <img src="docs/screenshots/journal.png" alt="Monthly journal with photo entries" width="240" /> | <img src="docs/screenshots/profile.png" alt="Profile screen with learning setup and permissions" width="240" /> |

| I-Spy · Linguini's clues | I-Spy · your turn |
| --- | --- |
| <img src="docs/screenshots/ispy-clues.png" alt="I-Spy phase one: a clue from Linguini and the objects to pick from" width="240" /> | <img src="docs/screenshots/ispy-your-turn.png" alt="I-Spy phase two: writing your own clue for a target word" width="240" /> |

## Launch film

<a href="landing/public/film/linguini-film-1080p.mp4"><img src="docs/media/launch-film-preview.webp" alt="Looping silent preview of the Linguini launch film" width="640" /></a>

The looping clip above is a silent animated WebP that plays on its own; click it for the
full 30-second film with sound
([1080p](landing/public/film/linguini-film-1080p.mp4),
[720p](landing/public/film/linguini-film-720p.mp4)). It is also embedded on the
[landing page](https://linguini-landing.vercel.app), and the narrated cut and 50-second
explainer live in [`landing/public/blog/`](landing/public/blog).

Regenerate the preview after re-cutting the film:

```sh
ffmpeg -i landing/public/film/linguini-film-720p.mp4 \
  -vf "fps=10,scale=640:-2" -loop 0 -c:v libwebp_anim -quality 60 -an \
  docs/media/launch-film-preview.webp
```

## Architecture

```mermaid
flowchart TD
  app["frontend/ — React 19 SPA"]
  api["backend/ — FastAPI, /api/v1"]
  sb["Supabase — PostgreSQL, Storage, Auth"]
  ai["AI models via OpenRouter"]

  app --> api
  api --> sb
  api --> ai
```

`landing/` is a separate Next.js site and does not call the API.

- API JSON is camelCase; Python attributes are snake_case. The API prefix is `/api/v1`.
- PostgreSQL is required: there is no in-memory or JSON fallback, and missing database
  configuration fails at startup.
- Prisma owns schema migrations (`backend/prisma/schema.prisma`); SQLAlchemy is the
  runtime data access layer.
- Model choices and cost comparisons for the AI calls are documented in
  [MODEL_COMPARISON.md](MODEL_COMPARISON.md).

## Repository

| Directory | What it is | Stack | Docs |
| --- | --- | --- | --- |
| [`frontend/`](frontend) | The learner web app | React 19, TypeScript, Vite | [frontend/README.md](frontend/README.md), [design.md](frontend/design.md) |
| [`backend/`](backend) | API, persistence and AI features | FastAPI, SQLAlchemy, PostgreSQL/Supabase, Prisma migrations | [backend/README.md](backend/README.md) |
| [`landing/`](landing) | Marketing site with an interactive demo session | Next.js 16 (App Router) | [landing/README.md](landing/README.md) |
| [`marketing/`](marketing) | Product Hunt launch kit, launch videos, media kit and business model | Markdown, Python/Pillow, FFmpeg, Hyperframes | [marketing/README.md](marketing/README.md) |

Each app manages its own dependencies and deploys on its own. `marketing/` is not deployed; it holds source files and finished exports.

## Quick start

```sh
# Learner app (http://localhost:5173)
cd frontend && npm ci && cp .env.example .env.local && npm run dev

# API (http://127.0.0.1:8000/docs); fill DATABASE_URL and DIRECT_URL in .env.local first
cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]" && npm ci \
  && cp .env.example .env.local && npm run db:deploy \
  && .venv/bin/uvicorn app.main:app --reload --env-file .env.local

# Landing page (http://localhost:3000)
cd landing && npm ci && npm run dev
```

Windows/PowerShell setup, environment variables and API details are in the app READMEs.

Use Node.js 22.12+ (Node 22 line) or Node 24, and Python 3.12+.

### Configuration

Every app reads an ignored `.env.local` copied from its `.env.example`. The variables
that matter most:

| App | Variable | Purpose |
| --- | --- | --- |
| `frontend` | `VITE_API_BASE_URL` | API origin without `/api/v1`, e.g. `http://127.0.0.1:8000`. |
| `frontend` | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | Supabase project used for sign-in. |
| `backend` | `DATABASE_URL`, `DIRECT_URL` | Runtime connection and Prisma migration connection (direct or session pooler, port 5432). |
| `backend` | `AUTH_MODE`, `DEMO_USER_ID` | `supabase` verifies bearer tokens; `demo` falls back to `DEMO_USER_ID` locally only. |
| `backend` | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Media uploads to the private `media-assets` bucket. |
| `backend` | `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins. |
| `landing` | `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_APP_URL` | Canonical site URL and where the call-to-action links point. |

Full tables, including optional AI and SEO settings, are in each app's README.

## Deployment

| Piece | Where | Notes |
| --- | --- | --- |
| Learner app | Vercel project, root directory `frontend` | https://linguini-navy.vercel.app |
| Landing page | Vercel project `linguini-landing`, root directory `landing` | https://linguini-landing.vercel.app |
| API | uvicorn/ASGI host | Needs the backend environment variables above; `AUTH_MODE=supabase`. |
| Database, storage, auth | Supabase | Migrations applied with `npm run db:deploy` from `backend/`. |

## Significant resources

- [React documentation](https://react.dev/learn) — component-based UI development.
- [Vite documentation](https://vite.dev/guide/) — frontend development and production builds.
- [FastAPI documentation](https://fastapi.tiangolo.com/) — backend API design and interactive API documentation.
- [PostgreSQL documentation](https://www.postgresql.org/docs/) — relational data modelling and database behaviour.
- [Supabase documentation](https://supabase.com/docs) — managed PostgreSQL, authentication, storage, and database services.
- [Google People + AI Guidebook](https://pair.withgoogle.com/guidebook/patterns) — human-centred AI interaction patterns, including user control, system status, and error recovery.
- [Microsoft HAX Toolkit](https://www.microsoft.com/en-us/haxtoolkit/ai-guidelines/) — evidence-based guidelines for human–AI interaction and correcting AI output.
- [Impeccable](https://impeccable.style/) — design guidance used during interface refinement to improve hierarchy, spacing, typography, and consistency.
- [OpenAI prompt engineering guidance](https://platform.openai.com/docs/guides/prompt-engineering) — prompt structure, clear instructions, and output constraints.
- [Google Gemini API documentation](https://ai.google.dev/gemini-api/docs) — multimodal model integration and structured AI responses.

## Contributing

- Branch from `main` with a plain descriptive slug, e.g. `session-lifecycle`, and open one pull request per slice of work.
- Commits and pull requests are attributed to the team member who requested the work. AI agents must not add themselves as authors or co-authors, or add "Generated with" lines; the CI `attribution` job rejects pull requests that do.
- Run the checks before opening a pull request:

  ```sh
  cd frontend && npm ci && npm run lint && npm run build
  cd backend  && ruff check . && pytest
  cd landing  && npm ci && npm run lint && npm run build
  ```

- Backend integration tests need `TEST_DATABASE_URL` pointing at a disposable PostgreSQL
  database; without it the PostgreSQL integration tests skip silently. For example:

  ```sh
  docker run -d --name linguini-test-pg -p 55432:5432 \
    -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=linguini_test postgres:16
  cd backend && DATABASE_URL=postgresql://postgres:postgres@localhost:55432/linguini_test npm run db:deploy
  TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:55432/linguini_test pytest
  ```

- Never point tests or migrations at the Supabase project used by the deployed app; treat
  any schema change as destructive until reviewed.
- Keep credentials in ignored `.env.local` files. Never commit database URLs, Supabase keys or API keys.

More agent-facing conventions live in [AGENTS.md](AGENTS.md).
Each section has their own AGENT.md file i.e backend and frontend have separate conventions.

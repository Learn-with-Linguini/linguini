# Linguini

A photo-led, speak-first language-learning app: explore a scene, learn its words,
then play I-Spy with Linguini in both directions.

## Current status

This repository contains a React/TypeScript frontend and a FastAPI/Pydantic backend.
The home greeting loads the demo user from `GET /api/v1/me`. Progress and saved
vocabulary load from `/api/v1/me/progress` and `/api/v1/me/vocabulary`.
Scene summaries load from `/api/v1/preloaded-scenes`; practice routes fetch
`/api/v1/preloaded-scenes/{sceneId}` before rendering their scene content.
The shared user and active language profile load from `/api/v1/me` and
`/api/v1/me/language-profiles`. Profile edits and onboarding save to PostgreSQL. Language selection filters scenes, vocabulary, and progress on the backend.
Practice actions and XP persist in PostgreSQL, as do journal entries and
edits. Vocabulary status changes remain in memory. Scene images are SVG placeholders; word playback uses browser speech synthesis
when available.

The backend defines API routes and validated request/response schemas. Its health
endpoint, user/profile edits, progress, vocabulary, scenes, demo sessions, and journal reads/writes work; remaining business route handlers return
`501 Not Implemented` when reached. The demo user is read from PostgreSQL through a service and repository.
Database configuration is required; authentication and AI integrations are not implemented.

## Repository layout

```text
linguini/
|-- frontend/             React app and frontend tooling
|   |-- src/
|   |   |-- components/   Shared UI, app shells, and scene rendering
|   |   |-- data/         Frontend types (mock.ts removed)
|   |   |-- lib/          Browser speech helper
|   |   |-- pages/        Screen components
|   |   |-- state/        In-memory learner and session state
|   |   `-- styles/       Global styles and design tokens
|   |-- public/          Static assets
|   |-- package.json     npm scripts and dependencies
|   `-- vite.config.ts   Vite configuration
|-- backend/
|   |-- app/             FastAPI entrypoint, routes, and schemas
|   |-- tests/           API contract and schema tests
|   `-- pyproject.toml   Python dependencies and tooling
|-- .oxlintrc.json       Frontend lint configuration
|-- design.md            Product design and visual guidelines
`-- README.md
```

Each app manages its own dependencies. Run npm commands in `frontend/` and Python
commands in `backend/`. Keep the backend virtual environment in `backend/.venv/`,
which is ignored by Git.

## Run locally

### Frontend

Use Node.js 22.12+ on the Node 22 line, or Node 24, with npm.

From the repository root:

```sh
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

In PowerShell, use `Copy-Item .env.example .env.local` for the copy command.
Open `http://localhost:5173/home` to load the demo greeting. The backend must be
running for this request; failures appear on screen without a hardcoded fallback.

### Backend

Use Python 3.12 or newer. In a separate Windows PowerShell terminal, starting
from the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env.local
# Fill DATABASE_URL and DIRECT_URL in .env.local before continuing.
npm ci
npm run db:deploy
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --env-file .env.local
```

Skip environment creation if `backend/.venv` already exists.
Open `http://127.0.0.1:8000/docs` for the API documentation.
See the [backend README](backend/README.md) for macOS/Linux setup and API details.

`frontend/.env.local` sets `VITE_API_BASE_URL=http://127.0.0.1:8000` (the server
origin, without `/api/v1`). Restart Vite after changing it. `backend/.env.local`
sets `CORS_ALLOWED_ORIGINS=http://localhost:5173` and `DEMO_USER_ID` to the UUID
of an existing row in PostgreSQL `users`. Allowed origins are comma-separated; include
the exact frontend origin, including port, if using another host or Vite port.
Restart the backend after changing its environment. Both example files use
matching defaults. No authentication is performed; `/me` always uses this demo ID.

If port 8000 is occupied by another project, add `--port 8001` to the backend
command and set `VITE_API_BASE_URL=http://127.0.0.1:8001` in `frontend/.env.local`.
Open `/progress` or `/vocabulary` to see the integrated screens. Restart the
backend after code changes unless it was started with `--reload`.

PostgreSQL stores users, language profiles, vocabulary, progress, sessions, tasks,
media metadata, journals, and AI generation runs. Configure the database as described
in the [backend README](backend/README.md). Runtime JSON storage and its environment
switches have been removed. Vocabulary status changes remain temporary frontend
state until that action is connected to a backend writer.

The scene catalog, word markers, and bundled demo practice content live in PostgreSQL
`preloaded_scenes`. Run `npm run db:deploy` from `backend/` to create the tables
and seed missing catalog entries. No JSON imports are required.
The SVG artwork remains in frontend components.

The catalog retains the existing scene slugs, so practice links still work. Open
`/practice` to select a scene or `/practice/calle-mayor/analysis` to test a direct
link. Loading, empty catalog, missing scene, and API failures have visible states.
Unknown scene IDs no longer fall back to the first scene. Reload the browser after
editing database scene content. Scene content remains static; camera uploads and AI generation
are not implemented. Demo multiple-choice answers are scored on the backend.

## Profile and language selection

Open `/profile` to edit your name and learning goal, choose a target language,
or change its level and daily minutes. Selections save immediately; name/goal
edits use **Save profile**. Microphone and camera preferences are persisted too,
but browser permissions remain separate. Onboarding configures this same demo
user; it does not create an authenticated account.

PostgreSQL `language_profiles` stores language profiles keyed by user ID, with at most one active profile per user. Switching language reloads content
and reloads practice state for that profile. Your selection and per-language goals survive
refreshes and backend restarts. Name changes appear in Home and the leaderboard.

The demo contains Spanish content only. Choose French (or another language) to
see empty scenes/vocabulary/progress, then return to Spanish to restore its data.
Spanish practice URLs return 404 while another language is active. Speech playback
uses the content language, and journal word suggestions use the filtered vocabulary.
Changing the level saves a preference; adaptive difficulty/content generation is
not implemented.

## Saved practice and journals

XP previously reset because it was only incremented in React state. Practice now
creates/resumes a backend session and saves each action through
`POST /api/v1/sessions/{id}/demo-events`. PostgreSQL stores sessions and XP
in one transaction, keyed by user and target language. The backend calculates awards; retries
of the same action in the same session award XP once. Reloads and backend restarts
preserve totals, completed tasks, answers, and clues. **Practise again** explicitly
starts a new session. The browser stores only the session ID, not XP.

Analysis earns no XP. Tasks use the scene's configured XP, multiple-choice answers
earn 5 XP when correct or 2 when incorrect, and a submitted clue earns 2 participation
XP. Free-form clue feedback is still scripted; it is not AI evaluation. Failed saves
show a retry action. The summary marks finished practice complete on the backend.

Journal history/detail and Save entry use the backend. Entries retain their language
profile; history includes this user's entries across languages. One journal per
user/local day is enforced using the user's timezone. Editing appends a revision;
retrying identical text does not append another revision. Journal illustrations
are selected scene artwork, not photo uploads. Journals do not award XP.

With existing dependencies and `.env.local` files, run in separate PowerShell terminals:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --env-file .env.local
```

```powershell
cd frontend
npm run dev
```

Use `VITE_API_BASE_URL=http://localhost:8000` in `frontend/.env.local` and
`CORS_ALLOWED_ORIGINS=http://localhost:5173` in `backend/.env.local`.
Open `http://localhost:5173/practice`, complete an action, then refresh `/progress`
to verify saved XP. Restart Vite after changing its environment configuration.

## Frontend commands

Run these inside `frontend/`:

| Command | Purpose |
| --- | --- |
| `npm ci` | Install dependencies from the committed lockfile |
| `npm run dev` | Start the development server |
| `npm run build` | Typecheck and build production assets into `dist/` |
| `npm run lint` | Run Oxlint |
| `npm run preview` | Preview an existing production build locally |

There is currently no frontend test script. Backend test and lint commands are
documented in the [backend README](backend/README.md#checks).

## Screens

These are frontend routes, separate from the backend's `/api/v1` endpoints.

| Route | Screen |
| --- | --- |
| `/` | Welcome |
| `/onboarding` | Account, language, goal, and permission setup UI |
| `/login` | Login UI |
| `/home` | Home and practice entry point |
| `/practice` | Scene selection |
| `/practice/:sceneId/analysis` | Scene analysis and word markers |
| `/practice/:sceneId/mic-test` | Microphone setup UI and typing fallback |
| `/practice/:sceneId/learn` | Learning tasks and flashcards |
| `/practice/:sceneId/ispy-1` | I-Spy: Linguini gives clues |
| `/practice/:sceneId/ispy-2` | I-Spy: the learner gives clues |
| `/practice/:sceneId/summary` | Session summary |
| `/progress` | Progress, scenarios, and leaderboard |
| `/vocabulary` | Vocabulary and status filters |
| `/journal`, `/journal/new`, `/journal/:entryId` | Journal list, creation, and entry |
| `/profile` | Profile and preferences |

## Development notes

Use [design.md](design.md) and `frontend/src/styles/tokens.css` for visual conventions.
Frontend types and backend schemas are currently maintained separately. When
connecting additional screens, align the UI with the backend OpenAPI contracts
and use the centralized request helper in `frontend/src/lib/api.ts`.

- `src/styles/tokens.css` — design tokens from [`design.md`](./design.md)
- `src/components/` — UI primitives, bottom-nav shell, scene illustrations and markers
- `src/data/` — types plus the dummy scenes, vocabulary, journal and progress data
- `src/state/` — in-memory app state (XP, task completion, vocabulary status, journal entries)
- `src/pages/` — one file per screen

The ready scenes use real photos where available, while `src/components/SceneArt.tsx` remains the
fallback illustration system for journal entries and incomplete image states.


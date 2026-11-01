# Linguini

<p align="center">
  <img src="frontend/public/linguini-logo.png" alt="Linguini logo" width="120" />
  <img src="frontend/public/linguini-wordmark.png" alt="Linguini wordmark" width="300" />
</p>

**CS3216 final project · Group 3**

Linguini is a photo-led language-learning app. Take or upload a photo, review the
objects the app finds, and learn to describe that scene in your target language.
Lessons combine vocabulary, grammar and two-way I-Spy practice. Progress and
journal entries preserve what you learned from your day.

[Open Linguini](https://www.learnwithlinguini.com/) ·
[Project documentation](docs/README.md) ·
[Development guide](AGENTS.md)

## Application

The learner app supports Supabase sign-in, language profiles, private photo
uploads, scene review, generated lessons, I-Spy, friend challenges, daily
challenges, vocabulary, progress and journals. English-speaking learners can choose Spanish, French, German or Korean. Mission availability
depends on the selected language and level. Speech
playback uses browser speech synthesis. Automated pronunciation grading is not
implemented.

The public marketing pages and interactive `/demo` share the frontend deployment.
The demo uses bundled content; the signed-in app calls the backend. The backend
owns grading, learning evidence, rewards and session state.

## Screenshots and film

| Home | Practice | Journal |
| --- | --- | --- |
| <img src="docs/screenshots/home.png" alt="Home with streak and next practice" width="220" /> | <img src="docs/screenshots/learn.png" alt="Photo-led vocabulary and lesson tasks" width="220" /> | <img src="docs/screenshots/journal.png" alt="Journal history with scene photos" width="220" /> |

[Watch the launch film](frontend/public/film/linguini-film-1080p.mp4)
([720p](frontend/public/film/linguini-film-720p.mp4)). Editable media and regeneration
steps are in [marketing/](marketing/README.md).

## Repository

| Path | Purpose |
| --- | --- |
| [`frontend/`](frontend/README.md) | React 19, TypeScript and Vite; learner routes and marketing pages |
| [`backend/`](backend/README.md) | FastAPI API under `/api/v1`, SQLAlchemy persistence and AI services |
| [`backend/prisma/`](backend/prisma/) | PostgreSQL schema and migrations |
| [`backend/evals/`](backend/evals/README.md) | Model evaluation datasets and runners |
| [`docs/`](docs/README.md) | Project documentation, reward policy and research |
| [`marketing/`](marketing/README.md) | Launch assets, production scripts and dated milestone records |
| [`.agents/skills/`](docs/skills.md) | Shared repository skills |

The Vite frontend is hosted on Vercel. The API runs separately and uses Supabase
for authentication, PostgreSQL and private media storage. AI services call the
providers and models configured in [`backend/ai.toml`](backend/ai.toml). Prisma
owns migrations; SQLAlchemy handles runtime queries.

## Local setup

Use Python 3.12+ and Node.js 24 (the CI version), or Node.js 22.19+ on the Node 22 line.

Frontend, from the repository root:

```sh
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Set `VITE_API_BASE_URL` to the API origin, without `/api/v1`, and fill in the public
Supabase settings in `frontend/.env.local`. Open `http://localhost:5173`.

Backend, in a second terminal:

```sh
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
npm ci
cp .env.example .env.local
```

Fill the backend configuration before starting the API. `DATABASE_URL` and
`DIRECT_URL` must point to your intended development database. Set
`CORS_ALLOWED_ORIGINS=http://localhost:5173`. Sign-in uses `AUTH_MODE=supabase`;
`AUTH_MODE=demo` is for an isolated local account only.

After verifying the database destination:

```sh
npm run db:validate
npm run db:deploy
.venv/bin/uvicorn app.main:app --reload --env-file .env.local
```

The API runs at `http://127.0.0.1:8000`; its interactive schema is at `/docs`.
See the [backend setup guide](backend/README.md) for Supabase, private uploads,
AI providers, Langfuse and PowerShell commands. Existing `.env.local` files should
be edited in place, not overwritten. Keep credentials out of Git and Vite variables.

## Checks

Run each app's checks from its directory:

```sh
cd frontend
npm ci
npm run lint
npm test
npm run build
```

```sh
cd backend
ruff check .
pytest
npm run db:validate
```

Backend integration tests require `TEST_DATABASE_URL` pointing at a disposable,
migrated PostgreSQL database. Without it, those tests skip; a passing run with
skips does not verify persistence or ownership. Never run tests against the
deployed Supabase database.

## Contributing

Branch from `dev` using a descriptive slug and target PRs at `dev`. Keep each PR
focused and include the checks actually run. Follow [AGENTS.md](AGENTS.md) for
attribution, analytics, review and migration rules, and
[frontend/AGENTS.md](frontend/AGENTS.md) for UI conventions.

The [documentation index](docs/README.md) links the current engineering guides.
Dated marketing proposals remain available as project evidence and identify their
original assumptions. Asset credits and licences stay with their source files.

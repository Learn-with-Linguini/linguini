# Linguini agent guide

## Start here

Linguini is a photo-led, speak-first language-learning app. Its core learner loop is:

1. Choose a ready scene or add a photo.
2. Identify and learn useful vocabulary in the image.
3. Play I-Spy: first identify Linguini's clue, then describe an object back.
4. Use the new words in a journal entry.

This checkout is the **root-level React/Vite frontend prototype**. It uses mock data and in-memory state; it does not currently call an API or persist user uploads after a refresh.

## Current checkout

```text
src/
  components/  Shared UI, scene and journal image renderers
  data/        Types plus mock scenes, vocabulary, progress, and journals
  pages/       One React component per route/screen
  state/       In-memory learner, practice session, and journal state
  styles/      Global styles and design tokens
public/        Wordmark, mascot, and local scene photos
design.md      Product/design source of truth
```

Run the frontend from the repository root:

```sh
npm install
npm run dev
npm run build
npm run lint
```

Use `npm run build` and `npm run lint` after a code change. The build includes TypeScript checking.

## Product and data conventions

- Mock scene and lesson data live in `src/data/mock.ts`; shared shapes live in `src/data/types.ts`.
- The six ready scenes are **Street, Classroom, Grocery store, Bedroom, Office, Airport**. Titles shown to learners are English.
- `SceneVisual` displays a scene's real photo and falls back to `SceneArt`. Use it whenever a component receives a `Scene`; do not add a one-off image-rendering path.
- Local supplied photos are in `public/scenes/`. Some ready scenes use hosted Unsplash photo URLs; keep the fallback illustration intact for resilience.
- `ScenePhoto` overlays vocabulary markers on the scene visual. Preserve its marker coordinates and 44px touch targets when changing scene rendering.
- Journal entries hold a `photos` collection of ready-scene images and locally selected uploads. `JournalPhotoVisual` renders one item, and the entry page owns the carousel state. Browser-file uploads use object URLs and are intentionally session-only until backend storage exists.
- The journal is a month view: show one month/year at a time, with previous/next chevrons, including for empty months.

## UI system

Read `design.md` before modifying visuals. Use existing primitives from `src/components/ui.tsx` and styles in `src/components/ui.css` rather than creating page-specific variants.

- Use the supplied `public/linguini-wordmark.png` in the shared pasta-cream header strip. It belongs to the initial page view and scrolls away with content; do not make it fixed or add a separate divider.
- Back navigation uses one shared chevron beside the wordmark. Do not add a second in-page back button.
- Headings use **Baloo 2**; body, labels, and controls use **Nunito Sans**.
- Action buttons are always filled: primary actions are tomato red and secondary actions are teal. Both use the shared press depth. Do not introduce outlined action buttons.
- `quiet` controls, chips, scene tiles, task rows, and I-Spy answer choices are learning controls rather than action buttons; their state styling may differ.
- Keep Home calm: lead with a compact seven-day streak rail using filled farfalle pasta for checked-in days, then show one featured next-step card (start or continue). Keep the word bank below it, an optional journal row after learning, and never restore a ready-scene grid there.
- The image-selection screen is not a numbered step: do not show a progress trail or “Step 1” there. Start visible flow progress after an image is selected, during analysis and learning.

## Routes and state

Key routes are in `src/App.tsx`:

- `/home` — one clear next learning action
- `/practice` — upload/select an environment
- `/practice/:sceneId/analysis` — image analysis and markers
- `/practice/:sceneId/learn` — learning tasks
- `/practice/:sceneId/ispy-1` and `/ispy-2` — two-direction I-Spy
- `/journal`, `/journal/new`, `/journal/:entryId` — monthly journal, editor, and entry carousel

The current `AppState` reducer keeps XP/session updates consistent in memory. Do not assume it is server-backed. Avoid replacing it with API code unless the task explicitly includes backend integration.

## Other branches: integration guidance

The local Git history contains distinct project stages:

| Ref | What it contains |
| --- | --- |
| `main` / `0v` | Initial design document only. |
| `devin/1789437786-react-frontend` | This root-level frontend prototype and its current UI work. |
| `origin/database-implementation` | PostgreSQL schema/migrations and persistence work. |
| `origin/backend-skeleton` | The database branch plus FastAPI routes, repositories, services, API contracts, and tests. |

The backend branches use a **different monorepo layout**: `frontend/` and `backend/`, unlike this checkout's root-level frontend. Do not copy or merge their files piecemeal. Any integration needs a deliberate migration plan for paths, tooling, and frontend API wiring.

On `origin/backend-skeleton`:

- Backend: Python 3.12+, FastAPI/Pydantic, SQLAlchemy/psycopg, PostgreSQL/Supabase runtime, and Prisma migrations.
- API prefix: `/api/v1`; the router includes health, users, home, media, sessions, tasks, vocabulary, progress, and journals.
- Backend setup/checks run from `backend/`: install `.[dev]`, configure `DATABASE_URL`, `DIRECT_URL`, `DEMO_USER_ID`, run `npm run db:validate`, `npm run db:deploy`, then `pytest -q` against a disposable test database.
- The backend owns persistent users, language profiles, media metadata, scenes, practice, vocabulary, journals, and AI-run observability. It does **not** yet implement authentication, camera/media storage, AI generation, or speech evaluation.
- Its frontend uses `VITE_API_BASE_URL` and explicit loading/error states. Align frontend types to OpenAPI contracts rather than querying the database directly.

## Safety and working habits

- Preserve existing uncommitted work; this repository is often intentionally dirty during UI iteration.
- Do not amend or reset unrelated work. Inspect `git status` and targeted diffs before changing a shared file.
- Keep credentials in ignored local environment files. Never commit database URLs, Supabase credentials, or API keys.
- Keep accessibility intact: visible focus states, 44px minimum icon targets, 48px minimum action height, clear text feedback alongside color, and reduced-motion support.

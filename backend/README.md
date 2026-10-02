# Linguini backend

FastAPI/Pydantic API with SQLAlchemy persistence in Supabase PostgreSQL. Prisma
owns schema migrations; it is not the Python runtime client. API JSON uses camelCase
and Python attributes use snake_case. See the [project README](../README.md) for the frontend.

## Setup

Use Python 3.12+ and Node/npm. From `backend/` in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm ci
Copy-Item .env.example .env.local
```

Skip creating the environment or copying the environment file if it already exists.
Fill these variables in `backend/.env.local`:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Backend PostgreSQL URI. In Supabase's Connect dialog, copy the direct or **session pooler** connection URI, replace the password, and use `sslmode=require`. Session pooler port is 5432; transaction pooler port 6543 is not supported by this backend. URL-encode special characters in credentials. |
| `DIRECT_URL` | Prisma migration URI: direct connection or session pooler. Use a database role permitted to apply DDL. |
| `DEMO_USER_ID` | Only applies when `AUTH_MODE=demo` (local dev/tests): UUID of the `users` row used for requests without a bearer token. Must not be set in deployed environments. |
| `AUTH_MODE` | `supabase` (default) verifies `Authorization: Bearer` tokens against the project JWKS; `demo` keeps the unauthenticated `DEMO_USER_ID` fallback. |
| `SUPABASE_JWT_AUDIENCE` | Expected JWT `aud`; defaults to `authenticated`. |
| `SUPABASE_JWT_SECRET` | Legacy HS256-signing projects only; asymmetric projects verify via JWKS. |
| `AUTH_ALLOW_ANONYMOUS` | `true` accepts Supabase anonymous-sign-in tokens (`is_anonymous` claim). |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins, including the port; defaults to `http://localhost:5173`. |
| `MEDIA_PUBLIC_BASE_URL` | Public Supabase Storage bucket URL, e.g. `https://PROJECT.supabase.co/storage/v1/object/public/media-assets`. Shared base URL for public media assets in this bucket. |

Database URLs stay on the backend. No Supabase anon key, service-role key, or AI
provider key is needed for database access. Do not append Prisma's `pgbouncer=true`
option to a SQLAlchemy connection URI. SQLAlchemy uses the psycopg driver internally.

```powershell
npm run db:validate
npm run db:deploy
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --env-file .env.local
```

On macOS/Linux, use `python3 -m venv .venv`, `.venv/bin/python`, and `cp` instead.
API docs: `http://127.0.0.1:8000/docs`; OpenAPI: `/openapi.json`.
Set frontend `VITE_API_BASE_URL=http://127.0.0.1:8000` without `/api/v1`.
Restart the appropriate server after changing environment settings.

**PostgreSQL is required.** The old `USER_STORAGE`, `LANGUAGE_PROFILE_STORAGE`,
`MEDIA_ASSET_STORAGE`, `VOCABULARY_STORAGE`, `SESSION_STORAGE`, and `JOURNAL_STORAGE`
switches have been removed. Existing values are ignored and can be deleted from
local environment files. Missing database configuration fails at startup; connection
or query failures never fall back to JSON. The application creates one SQLAlchemy
engine per process and disposes it at shutdown.

## Persistence and remaining static content

### Image uploads

Uploads use the authenticated user's identity: requests must carry a Supabase
`Authorization: Bearer` access token (or run with `AUTH_MODE=demo` locally).
The server requires `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`; uploads use the
private `media-assets` bucket. Install backend dependencies to include Pillow.

1. `POST /api/v1/media/upload-url` with `fileName`, `fileSize`, `mimeType`, and
   `source` (`camera` or `userUpload`). Sizes must be 1–10,485,760 bytes, and MIME
   types must be JPEG, PNG or WebP. The response includes `assetId`, `storageKey`,
   `uploadUrl`, and `expiresInSeconds`. No metadata row is inserted yet. Keys use
   `users/{userId}/images/{assetId}.{extension}`, with the extension chosen by MIME.
2. PUT the file bytes to `uploadUrl` with its `Content-Type`. Uploads do not permit
   overwrites. The signed upload URL expires after 7,200 seconds.
3. `POST /api/v1/media/confirm-upload` with `assetId`, `storageKey`, and `source`.
   The server checks the key, downloads with a bounded byte limit, verifies and
   decodes the image with Pillow, and saves the detected MIME and dimensions.
   Invalid uploaded objects are deleted; transient Storage failures can be retried.
   Repeated/concurrent confirmations return the existing owned asset.
4. `GET /api/v1/media/{assetId}` returns metadata plus `signedUrl` and
   `expiresInSeconds: 3600`. Missing and unauthorized assets both return 404.

The frontend supports file selection and device camera capture, validation, upload
status, error feedback, and a signed-image preview. Journal uploads can be selected
and saved as attachments. Uploaded images can start a session and run the placeholder
analysis workflow below. Desktop browsers may open a file picker for the camera control.

### Unified image sessions

Both image sources use `MediaAsset -> Session -> SceneObjects -> VocabularyItems ->
SessionTasks -> attempts/completion/skipping -> progress`. The source is read from
`MediaAsset.source`; there is no client-controlled session type.

1. Create a session using `POST /api/v1/sessions` with `mediaAssetId`, the active
   `languageProfileId`, and an optional retry `idempotencyKey`.
2. `POST /api/v1/sessions/{id}/analyze` saves resumable object suggestions in
   `sessions.analysis_draft`. It creates no `scene_objects` or lesson tasks yet;
   `generate-plan` is an alias for this draft step. `GET` returns draft suggestions
   in `sceneObjects` until review is confirmed.
   `GET /api/v1/sessions/{id}/review-word?label=chair` checks an English label
   against vocabulary for the active learning language.
   `PUT /api/v1/sessions/{id}/review` accepts `acceptedObjectIds` and `addedObjects`
   (`id`, English `label`, normalized `x`/`y`). It atomically saves only selected
   objects, clears the draft and builds tasks. Unknown added words are rejected;
   task activity locks further editing. Apply the session-analysis-draft migration
   with `npm run db:deploy` before running this version of the API.
3. Preloaded images use curated catalog objects. Uploaded photos use chair, table,
   and plant samples with fixed positions, explicitly labeled in the UI. No pixels
   are inspected. Vocabulary covers all six UI target languages with English as
   the source language; other pairs return a clear conflict rather than mislabeling data.
4. Both sources share analysis, mic test, practice and summary screens under
   `/practice/sessions/:sessionId`. Every task is skippable. Pronunciation currently
   uses typed answers; there is no speech grading or AI evaluation.
5. `POST /tasks/{id}/start`, `/complete`, `/attempts`, and `/skip` persist actions.
   Only reading tasks accept direct completion. Exercises are evaluated against
   server-only keys. Reflection records participation. One evaluated attempt ends
   each placeholder exercise, including incorrect answers. Retrying the same attempt
   key and payload returns the saved attempt; a changed payload conflicts.
6. Introductions and evaluated attempts atomically create vocabulary encounters and
   increment exposure/correct counters. Analysis, explanations and skips earn no
   vocabulary credit. XP is derived as five points per encounter. No mastery score
   algorithm is implemented. Session completion requires every task completed or skipped.

Vocabulary is bootstrapped idempotently during analysis and existing records are reused.
No separate vocabulary bootstrap script is needed. The old object review and
demo-event routes have been removed.

Migration `20260919020000_normalize_session_workflow` preserves session IDs and
normalized history, closes unfinished legacy sessions, and removes the obsolete JSON
state column. Migration `20260919030000_remove_user_practice_progress` removes the
unused practice snapshot table. Export any historical snapshot rows before deployment
if they need to be retained. Run `npm run db:deploy` before restarting the backend.

XP is not stored as a separate total. `/api/v1/me/progress` calculates five points per
persisted `vocabulary_encounters` row for the current user and active target language.
Session/task rows supply completion progress; `user_vocabulary_progress` retains
per-word exposure and correct-attempt counters. Removing the old snapshot table does
not alter these records or convert historical demo XP into learning credit.

To run the workflow integration tests, set `TEST_DATABASE_URL` to a disposable
PostgreSQL database with all Prisma migrations applied, then run
`python -m pytest tests/test_postgres_sessions.py tests/test_api_workflows.py`
from `backend`. These tests write records; use a separate test database.

### Preloaded scene images

For a private bucket, set these backend-only variables in `backend/.env.local`:

```dotenv
MEDIA_STORAGE_PRIVATE=true
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
MEDIA_STORAGE_BUCKET=media-assets
SUPABASE_SERVICE_ROLE_KEY=your-server-service-role-key
```

The service-role key is available in the project's API key settings. Never put it
in a `VITE_*` variable or frontend code. The backend signs only the assets linked
to the requested preloaded scenes and returns one-hour download URLs in `imageUrl`.
Each scene fetch issues fresh URLs; reload the page if an old URL has expired.
Signing failures return a 503 error instead of silently using a public URL.
`MEDIA_PUBLIC_BASE_URL` is ignored in private mode. Restart the backend after
changing configuration. Keep `storage_key` bucket-relative, for example
`preloaded/scenes/bedroom.jpg`; no schema migration is needed.

For a public bucket, set `MEDIA_STORAGE_PRIVATE=false` and follow the configuration below.

Upload the scene image files to a public Supabase Storage bucket and set
`MEDIA_PUBLIC_BASE_URL` in `backend/.env.local` to that bucket's public URL.
Set each linked `media_assets.storage_key` to its raw, bucket-relative object path,
for example `preloaded/scenes/bedroom.jpg` (without the bucket name). Set the asset's MIME type,
width, and height to match the uploaded file. An existing absolute HTTP(S) image URL
in `storage_key` also works without the base URL setting. Restart the backend after
changing environment variables.

Scene list and detail responses include `imageUrl`; the frontend uses it in catalog
cards and learning/practice views. Practice displays the full image without cropping,
so marker coordinates remain percentages of the image. If you replace an illustration
with a different photo, update the scene content's item coordinates to match it.
Seeded `demo-art/*` keys have no remote image URL. Missing URLs or failed image
downloads display an "Image unavailable" placeholder in scene views. Database seed migrations
create metadata only; they do not upload files. This configuration serves public
preloaded images; use the private mode above for private buckets.
See [Supabase public URLs](https://supabase.com/docs/reference/javascript/file-buckets-getpublicurl).

#### Precomputing scene vocabulary

`python -m app.scripts.precompute_preloaded_scenes` (run from `backend/`)
analyses the six bundled scene images once per image with the configured
scene-analysis provider, translates the detected objects into French and
Spanish, and stores the assembled suggested words in
`preloaded_scenes.content.items` so the Scene Analysis review screen opens
with words already on the photo. Tasks are **not** precomputed — the runtime
workflow still generates real tasks, rounds and prompts; the script only
writes minimal placeholders for them.

```sh
python -m app.scripts.precompute_preloaded_scenes --dry-run --json out.json
python -m app.scripts.precompute_preloaded_scenes --slug calle-mayor --language fr
python -m app.scripts.precompute_preloaded_scenes --emit-migration migration.sql
python -m app.scripts.precompute_preloaded_scenes --from-json out.json --emit-migration migration.sql
```

`--slug` and `--language` are repeatable and default to all six base scenes
and both languages (`fr`, `es`). `--dry-run` computes and validates rows
without writing to the database. `--json` dumps the computed rows and media
assets for reuse; `--from-json` reloads that file (re-validating every row)
instead of calling any AI provider, so SQL regeneration or the database write
never re-bills the model. `--emit-migration` writes an idempotent
`INSERT ... ON CONFLICT (slug) DO UPDATE` migration; the generated French rows
reuse the existing `media_assets` rows, so no asset inserts are emitted.
Environment values are read from `backend/.env.local` (or `--env-file PATH`).

Required environment: `DATABASE_URL`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `MEDIA_STORAGE_BUCKET`, plus the AI
configuration. Canonical key names are `AI_OPENAI_API_KEY` and
`AI_GEMINI_API_KEY`; plain `OPENAI_API_KEY`/`GEMINI_API_KEY` are accepted as
fallbacks. Provider and model selection use `AI_SCENE_ANALYSIS_PROVIDER` /
`AI_SCENE_ANALYSIS_MODEL` and `AI_SCENE_TRANSLATION_PROVIDER` /
`AI_SCENE_TRANSLATION_MODEL`. Keep keys only in `backend/.env.local`; never
commit them.

| Data | Runtime storage |
| --- | --- |
| Users and language profiles | `users`, `language_profiles` |
| Image/audio metadata | `media_assets` (file bytes are not stored here) |
| Vocabulary | `vocabulary_items`, `vocabulary_translations`, `user_vocabulary_progress`, `vocabulary_encounters` |
| Practice | `sessions`, `scene_objects` |
| Tasks | `session_tasks`, `task_attempts`, `task_hints` |
| Journals | `journals`, `journal_media`, `journal_revisions`, `journal_suggestions`, `journal_word_mentions` |
| Preloaded scene definitions, markers, demo questions and prompts | `preloaded_scenes` |

The scene catalog is read from PostgreSQL through `PostgresSceneRepository`.
`preloaded_scenes` stores a UUID, unique URL slug, language code/display name, title,
description, art key, difficulty, media FK, sort order, active flag and timestamps.
JSONB `content` holds the reusable markers/tasks/rounds/prompts and is validated
against `PreloadedSceneDetail` when reading. Metadata comes from columns,
not arbitrary content keys. The image FK restricts deletion; triggers require a
shared preloaded image and prevent changing referenced media to another source/type.
Inactive scenes are excluded from catalog and detail reads. Existing slugs and the
frontend response contract are preserved. SVG artwork remains in the frontend.

The built-in scene catalog is preserved in the
`20260918090000_seed_preloaded_scenes` migration. Run `npm run db:deploy` to apply it.
It inserts missing media IDs and scene slugs without overwriting existing rows.
This supports fresh installations without a JSON file or an import command.

The legacy `app/import_*.py` tools, JSON fixtures, and file-backed test adapters
have been removed. Existing migrated user data stays in PostgreSQL. Fresh databases
contain the catalog but no demo users or learner history; the API provisions a
`users` row on the first authenticated request, or set `AUTH_MODE=demo` with
`DEMO_USER_ID` pointing at an existing row for local development.

Repository interfaces and shared errors remain in `app/repositories/`;
SQLAlchemy implementations live in `app/repositories/postgres/`. Services depend
on these interfaces, while FastAPI dependencies supply PostgreSQL implementations.
They are separate responsibilities rather than duplicate persistence code.

## Behavior and constraints

Users own language profiles; language pairs are unique per user and only one profile
can be active. Switching profiles filters vocabulary and the scene catalog. Name,
learning goal, preferences, level, and daily minutes persist in PostgreSQL. Browser
camera/microphone permissions remain separate from saved preferences.

Vocabulary reads use the active target language and its source-language translation
in one database snapshot. Missing translations remain null. Trusted backend events
use `PostgresVocabularyRepository.record_encounter` to atomically record an event
and update counters. Stable IDs make event retries idempotent; conflicting reuse is
rejected. Mastery/status are not inferred from counters. Composite foreign keys
require every encounter's session to belong to its user, and its task to belong
to that exact session. Missing parents and cross-user/session references are
rejected even for direct SQL writes. These constraints establish ownership and
existence; they do not prove an answer was evaluated or a task was completed.

The `20260918100000_enforce_encounter_parents` migration validates existing history
and fails atomically if invalid references exist. Before deploying it to an existing
database, this query should return no rows:

```sql
SELECT e.id, e.user_id, e.session_id, e.session_task_id
FROM public.vocabulary_encounters e
LEFT JOIN public.sessions s ON s.id = e.session_id AND s.user_id = e.user_id
LEFT JOIN public.session_tasks t ON t.id = e.session_task_id AND t.session_id = e.session_id
WHERE s.id IS NULL OR t.id IS NULL;
```

Reconcile any results with real historical records before deployment; the migration
does not fabricate parents, delete encounters, or adjust counters. Foreign keys use
`NO ACTION`, deferred until transaction commit: individual sessions/tasks cannot be
deleted while referenced, but deleting an entire user's aggregate can cascade
atomically. Prisma records the relations; SQL defines the deferred-check behavior.

Practice actions, evaluated attempts, encounters, and vocabulary counters commit in
one transaction. Stable event identities and a user lock prevent duplicate credit
under concurrent retries. Learners can leave up to three unfinished sessions open and
resume an open session from the home screen. Task answers are private and are omitted
from every public task response.

Journals are unique per user/local date across all target languages. Saves append
immutable revisions, with identical retries avoiding duplicate revisions. Media
must be owned or preloaded images; audio must be owned. Suggestion acceptance
requires the expected base revision and atomically creates a new revision.
Annotation offsets use zero-based Unicode code points with an exclusive end;
JavaScript UTF-16 offsets must be converted for supplementary characters. Child rows
cascade when their journal is deleted; referenced media/vocabulary remain protected.

Tables use UUID identities and timezone-aware timestamps. Migrations define foreign
keys, checks, update triggers, RLS, and revoked browser-role grants. All access is
through backend repositories; the frontend must not query these tables directly.

### AI observability

AI calls can be traced to Langfuse. Tracing is off by default and strictly
best-effort: without keys the app runs a no-op tracer, and a tracing failure
never affects a learner request or blocks the request path (export is
asynchronous). Today exactly one operation is instrumented — I-Spy
description evaluation (`ispy-description-evaluation`), recorded as a
generation with provider/model dimensions, validation outcome, latency and
error codes.

Canonical variables (the Langfuse-native `LANGFUSE_*` names are accepted as
aliases when the canonical one is unset): `AI_OBSERVABILITY_ENABLED`,
`AI_OBSERVABILITY_BASE_URL`, `AI_OBSERVABILITY_PUBLIC_KEY`,
`AI_OBSERVABILITY_SECRET_KEY`, `AI_OBSERVABILITY_ENVIRONMENT`, and
`AI_OBSERVABILITY_CAPTURE_CONTENT`.

Content capture is opt-in. With `AI_OBSERVABILITY_CAPTURE_CONTENT=false`
(the default) no learner text or model output leaves the process: the
client is constructed with a mask that redacts any input/output payload.
Image bytes, base64, keys, signed URLs, raw learner text and full model
responses are never traced by default; observations carry only scalar
dimensions and caller-supplied metadata.

## Remaining integration work

Real image analysis, AI generation and speech evaluation
are not implemented. Uploaded images use validated storage uploads and deterministic
placeholder objects. Vocabulary "Move" is still local frontend state. Session learning credit comes from persisted
vocabulary encounters; analysis and skipped tasks award none. Daily vocabulary, home aggregation, and other unfinished
routes return an explicit 501. Journal eligible-photo/learned-word recommendations
and automatic annotations remain unpopulated. Creating tables does not implement
these provider or frontend flows.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Without `TEST_DATABASE_URL`, PostgreSQL integration tests are skipped. For complete
coverage, point `TEST_DATABASE_URL` to a **disposable migrated test database** and run
the suite. Integration tests create and delete records; never use a live Supabase
project as the test database. Pure schema/error-handling tests run without a database. Persistence and API tests
use PostgreSQL, create their own records in Python, and clean up after themselves.
Scene tests read the catalog installed by migrations; no test JSON files or alternate
storage adapters are used. The tests exercise the production dependency graph.

Production sources are under `app/`, migrations under `prisma/migrations/`,
and database/schema tests under `tests/`.

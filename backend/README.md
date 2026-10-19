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
| `SUPPORT_SMTP_HOST`, `SUPPORT_SMTP_PORT`, `SUPPORT_SMTP_USE_TLS` | SMTP connection used by `POST /api/v1/support/requests`; Gmail uses `smtp.gmail.com`, port `587`, and TLS. |
| `SUPPORT_SMTP_USERNAME`, `SUPPORT_SMTP_PASSWORD` | Credentials for the real mailbox that sends support requests. With Gmail, use a dedicated mailbox and an app password; never commit it. |
| `SUPPORT_FROM_EMAIL`, `SUPPORT_FROM_NAME` | Sender displayed on automatically submitted support mail. `SUPPORT_FROM_EMAIL` must match the authenticated mailbox. |
| `SUPPORT_TO_EMAIL` | Support destination; defaults to `linguini-support@googlegroups.com`. The learner-supplied address is used as `Reply-To`. |

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

### Basil and photo challenges

Apply the game resource, uploaded photo room, room invite, asynchronous challenge
and mission gamification migrations before deploying. Basil and two-player rooms
are available automatically; they require no feature switches in the API or
frontend. The I-Spy tab offers standalone play with AI, saved friends and a
challenge inbox.

Starting or resuming a lesson or photo challenge does not spend Sauce. Legacy
Sauce balances, transactions, daily refill settings and refunds remain for
historical requests; they no longer gate new practice. Sauce Jars now show
mission progress. Basil Points reward accepted lesson questions and room
contributions; 20 Basil unlocks an accent. Today and lifetime totals count earned
credits separately from the spendable balance. Existing XP history is preserved.
See [the reward and badge policy](../docs/gamification.md). Standalone AI I-Spy
games remain free and do not award Basil, XP or vocabulary progress.

Rooms store random invitations privately in the database, so a host can recover
an invitation after reload or an API restart without a separate room secret.
The invite migration rotates existing live invitations; hosts should copy the
new code after deployment. Rooms support two players learning English to Spanish,
French or German at the same A1/A2 level, with 2–4 photos uploaded by either player.
Room photos use the configured scene analyzer and translator, then require the
owner's fact review.
Rooms do not require or call OpenAI image moderation. Photos remain private to the
owner until analysis succeeds, then become accessible only to the invited partner.
Room invitations and preparation expire after seven days; started challenges last
14 days. A host can prepare and consent before their partner joins. The final
player to get ready starts the game automatically, so the host can be offline.
Both players explicitly consent by getting ready. Auto-start and the legacy
start endpoint work even when historical Sauce balances are empty, and retries
do not create duplicate rounds.

`GET /api/v1/rooms` returns every active challenge and completed challenge with
an unread result (up to ten together per learner), plus up to 20 other recent
finished challenges, ordered by `updatedAt`. The older
`GET /api/v1/rooms/active` returns the most recently updated active challenge.
Snapshots include `inviteExpiresAt`, `updatedAt` and `actionRequired` for the
inbox: `inviteFriend`, `preparePhotos`, `ready`, `sendClue`, `guess`, `viewResult`,
`waiting` or `finished`. Setup remains limited to five newly created or joined
rooms per hour. Returning to the inbox does not end a challenge; the explicit
leave command ends it for both players.

Results are acknowledged separately. The first acknowledgement advances the
shared round; a returning partner sees their own oldest unread result before
the current round, including the final result after completion. Only that
partner's pending result photo remains accessible after completion. Ending,
expiry and account deletion revoke room photo access. Clues and guesses retain
server-owned, idempotent Basil contribution rewards, which feed account earned
totals and opted-in daily standings. Existing XP awards are preserved for history.

Friends use explicit, single-use private invitations without email or account
search. `POST /api/v1/friends/invite` accepts a `commandId` and returns a durable
`inviteCode` and `expiresAt` (seven days); `POST /api/v1/friends/accept` accepts
`commandId` and `inviteCode` to create a mutual friendship. `GET /api/v1/friends`
returns display names and active learning setups with `canChallenge`.
`DELETE /api/v1/friends/{userId}` unlinks both sides. Consumed invitations cannot
re-add an unlinked friend; a fresh invitation is required. Invitation creation
is limited to ten per hour and acceptance to 20 per hour. Room partners are
never saved automatically. Creating a room with `friendUserId` adds only an
accepted friend with a matching active learning language and level; it appears
in their inbox without spending Sauce. Removing a friend prevents future direct
challenges; an existing challenge can still be resumed or explicitly ended.
Room images use an authenticated, uncached endpoint; ordinary media access stays
restricted to the photo owner. Rooms require `MEDIA_STORAGE_PRIVATE=true`; the
Supabase bucket must also be configured as private.

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
and saved as attachments. Uploaded images can start a session and run the analysis
workflow below. Desktop browsers may open a file picker for the camera control.

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
   If analysis fails with `sceneAnalysisFailed` (provider error, invalid output or
   a timed-out run), the image and its `media_assets` row stay saved and the
   response sets `analysisRetryable`. `POST /api/v1/sessions/{id}/retry-analysis`
   reruns analysis on that saved image without a new upload, up to three attempts
   per session. It checks ownership and the open-practice limit, and concurrent
   retries run the model once. `imageModerationFailed` and other failures cannot
   be retried. Failed sessions stay out of `GET /sessions/active`.
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

### Personalizing new photo lessons

Set `LEARNER_MEMORY_ENABLED=true` to use the learner's existing history for their
language profile. Previously missed words in the current photo appear first;
grammar exercises can give more practice on earlier mistakes. A short session
summary shows returning words and the skills being revisited. Empty history and
the default `false` setting retain the existing lesson generation path.

History is read from lesson practice and completed journal records; standalone
I-Spy games do not enter this lesson history. No additional schema
change or separate model call is required. Exposure, graded answers, journal
selections and assisted writing remain separate observations. Only a bounded
summary (up to 16 terms and 6 KiB) reaches grammar generation, without journal
prose or submitted answers. Only current-photo vocabulary is eligible for the
exercises. Personalized grammar uses a user-and-profile cache and bypasses
shared curated grammar templates, which can add a grammar model call for a
curated scene. Translation and I-Spy keep their existing template and cache paths.

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
scene-analysis provider and stores the detected objects (English labels,
markers, attributes) in `preloaded_scenes.content.items`, so the Scene Analysis
review screen opens with objects already on the photo. Scenes have no language:
each image has one row, and a learner's session translates the objects into
their target language (or reuses the catalog word for that label). `content.tasks/rounds/prompts` stay minimal
placeholders; real lessons and clues come from the templates below.

Each item's `attributes.color` and the scene's `content.relations` are curated from
the images (migration `20261013010000_preloaded_scene_facts`), so preloaded lessons and
I-Spy games get describing rounds. Re-running the script with `--emit-migration`
replaces them with detected facts; review those before applying.

```sh
python -m app.scripts.precompute_preloaded_scenes --dry-run --json out.json
python -m app.scripts.precompute_preloaded_scenes --slug street --language fr
python -m app.scripts.precompute_preloaded_scenes --emit-migration migration.sql
python -m app.scripts.precompute_preloaded_scenes --from-json out.json --emit-migration migration.sql
```

`--slug` and `--language` are repeatable and default to all six scenes
(`street`, `cafe`, `market`, `bedroom`, `kitchen`, `park`) and both template
languages (`fr`, `es`); `--language` only selects which languages get templates. `--dry-run` computes and validates rows
without writing to the database. `--json` dumps the computed rows and media
assets for reuse; `--from-json` reloads that file (re-validating every row)
instead of calling any AI provider, so SQL regeneration or the database write
never re-bills the model. `--emit-migration` writes an idempotent
`INSERT ... ON CONFLICT (slug) DO UPDATE` migration; rows reuse the existing
`media_assets` rows, so no asset inserts are emitted.
Environment values are read from `backend/.env.local` (or `--env-file PATH`).

##### Lesson and clue templates

After building each row the script runs translation, learning tasks and I-Spy
clues through the normal routed services and validators, using the same
payload a learner session builds when it accepts every suggested object with
its attributes and relations. Each validated result is stored server-only in
`preloaded_scenes.content.generated` (`version: preloaded-templates.v1`) with:

- `feature`, `language` and `variant` (`prompt|schema|validator` versions);
- a `fingerprint` of the scene facts (title, summary, labels, attributes,
  relations, marker positions) and language;
- stable references (`o1`, `o1:color`, `r1`) instead of session IDs;
- provenance (deployment, model, creation time).

A new variant is added next to older ones. The public scene API never returns
`generated` (`CONTENT_FIELDS` in `repositories/postgres/scenes.py`).

At review time, unchanged curated content checks the templates first. A match
is mapped onto the session's own object, attribute and relation IDs, validated
again, and passed to the existing task builders, so each session gets fresh
task records and answer keys stay in `session_tasks`. No model call is made.
Ownership, claims, revision guards and idempotency are unchanged. Edited
scenes, uploaded photos, partial selections, missing or stale templates and
failed remapping fall back to the result cache and normal routed generation.
A model or deployment change alone does not stale a template; rerun the
script to refresh.

```sh
python -m app.scripts.precompute_preloaded_scenes --state state.json --report report.json
python -m app.scripts.precompute_preloaded_scenes --from-json out.json --dry-run --report report.json
python -m app.scripts.precompute_preloaded_scenes --from-json out.json --max-provider-calls 30 --only clues --force
```

- `--state PATH` saves progress after each scene and template; a rerun skips
  finished rows and templates that still match.
- `--max-provider-calls N` is a hard cap on model calls for the whole run. A
  stage starts only if its route's full call budget still fits. `0` only
  checks templates and reports missing ones; with `--from-json` the default
  is `0`, otherwise unlimited.
- `--only translation|lessons|clues` limits which stages may call a model;
  `--force` regenerates them even when they match. `--skip-templates` skips
  the stages.
- `--report PATH` writes each scene, language and stage with its status
  (`reused`, `generated`, `missing`, `failed`) and an error code only, never
  scene text, provider bodies or keys. The script exits non-zero when a stage
  fails; `missing` alone does not fail the run.

Required environment: `DATABASE_URL`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `MEDIA_STORAGE_BUCKET`, plus the AI
configuration: the routes in `ai.toml` (see
[AI configuration](#ai-configuration)) and the API keys their credentials
name. Keep keys only in `backend/.env.local`; never commit them.

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

Proficiency levels are `A0`–`C2`; `A0` stores Pre-A1 in the existing two-character level
columns, and the frontend shows it as "Pre-A1". Pre-A1 has no missions yet, so its lessons
use the regular lesson plan. Photo rooms accept only A1/A2 profiles.

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
under concurrent retries. No AI provider call runs inside a database transaction:
task generation claims `sessions.generation_revision`, calls the models with no
transaction open, then persists only if its revision is still current, so a stale
run never overwrites or fails a newer one. Model-graded I-Spy descriptions claim
`session_tasks.evaluation_claim_id` with the attempt's idempotency-derived ID,
store a SHA-256 fingerprint of the request and a lease
(`evaluation_claim_expires_at`: the model's timeout × attempts plus 15 s), evaluate
outside the transaction, and save only while that claim is still held. Only the
lease holder calls the model: a concurrent request with the same key polls (20–100 ms
backoff) for the holder's saved attempt, the same key with different input gets 409
before any model call, and an expired lease left by a crashed request is taken over.
Unexpected failures release the lease at once, so one key yields one saved attempt,
one model call and at most one XP award.

Round-two I-Spy descriptions (reflection tasks in the `ispy` phase with a
`sceneDescriptionContext`) are a guess-and-revise loop. Each clue saves a new
attempt with the next `attemptNumber` and versioned `evaluationDetails`
(`ispy-description-evaluation.v1`) whose `outcome` is `clearMatch` (target guessed,
not ambiguous, nothing contradicted), `needsClarification` (ambiguous, or the target
is only an alternative), `needsRevision` (target guessed with contradicted
evidence), `noMatch` or `evaluationFailed` (the provider failed; the clue is kept).
The task stays `inProgress` until `POST /tasks/{id}/confirm-guess` names the latest
`clearMatch` attempt; older attempts and other outcomes get 409. Confirmation is
the only path that awards `ispyCorrect` (`ispy-correct:{taskId}`) and
`taskCompleted` (`task:{taskId}`), and it records a `completed` vocabulary
encounter rather than a correct one, because the model naming the object does not
show that the learner produced the noun. The session summary counts each described
task as one round that succeeds only once confirmed.

Described tasks also publish optional `clueFrames` and `avoidWords` in their
`ReflectionContent` (`app/services/ispy_clue_frames.py`). Frames separate sentence
structure from vocabulary choices: Spanish and French get a Colour frame (`Es [colour]` /
`Elle est [colour]`) when the target has a confirmed colour, and a Location frame
(`Está [position] [reference object]` / `Il/Elle est …`) when a confirmed relation
links the target to another word from this session's vocabulary lesson. Slots offer
small banks rather than the answer: five introduced position expressions (each with a
meaning and an example about other objects), the other lesson words as article + noun
(never the target), and common colours agreed with the target's gender. A chip is a
language option, not a scene claim; the guess model still evaluates the finished clue
against confirmed facts. `phrases` maps `"position|reference"` to the composed text so
contractions (`al lado del libro`, `à côté du livre`) stay server-side. The correct
whole phrases sit in `help`, shown only after **Help me**. Frame examples are generic
teaching sentences, so they never reveal the target's clue. New tasks have no Name frame;
Name frames and whole-phrase `chips` saved on older tasks still validate. Up to two
targets are chosen, only those with at least one `help` phrase; a photo without any
yields no described tasks. Other languages and older tasks without frames keep free
typing only.

Before any provider call, `check_clue` rejects a clue containing an actual target form
(whole words, ignoring case and accents, including plurals and the source label) with
`clue_names_target`. Similar spellings are never hard rejections, because they may be a
different valid word (`misa`, `mes`); the frontend only shows a soft warning for them.
Each frame owns its own sentence, so French Colour and Location can share `Elle est`,
and changing one slot rewrites only that frame's sentence. The submitted `assistance`
(`ispy-clue-assistance.v1`: offered and selected frame IDs, inserted chips,
`selectedSlots`, `revealedHelpFrameIds`, `practiceMode: guided`) is validated against
the task's frames and stored in `responsePayload`; it records guided practice and never
changes correctness or vocabulary credit. Frames stay in `publicContent`, so the guess
model never sees them, and `GET /tasks/{id}/latest-attempt` returns the saved assistance
so slot picks and revealed help survive a reload. For round-one clues it returns the
chosen `optionId`, `isCorrect` and feedback, so an answered clue still shows its grade
when the original response was lost.

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

### Uploaded-photo scene facts

`scene-analysis.v5` returns up to 20 clearly visible object instances, ordered with
the most useful and diverse learning candidates first. Repeated objects keep separate
boxes and markers but share a model `groupKey` and `suggestedGroupCount`; the mapped
quantity remains only a suggestion until the learner confirms it in the Counts review.
The full inventory is stored once in `media_scene_analyses`, keyed by the media asset
and prompt/schema versions, so another session can reuse the image without another
vision call. Each session receives its own stable object IDs and snapshots only the
facts it confirms.

Before review, the backend compares the unconfirmed inventory with the implemented
missions for the learner's level. `provisionalMissionPlan` is presentation guidance,
never grading evidence: `suggestedSceneObjectIds` limits the default review to the
smallest useful mission-focused set. The learner may reveal other inventory objects.
After review, mission eligibility is run again using only confirmed facts and that
second result becomes the immutable `missionPlan` consumed by task generation.

The analysis may also return visible action suggestions linked to detected objects and
clearly displayed price suggestions linked to an item. These remain unconfirmed scene
metadata: the vision model may describe visible evidence such as holding or a price tag,
but may not infer ownership, preference, need, routine, intention, availability or a
real price that is not shown. Mission planning must use action or price information only
after the learner confirms it or explicitly selects a labelled role-play value.

### Mission contracts

A mission is the definition of one lesson goal at one practice level. Each mission has
one definition file, `app/missions/definitions/{missionId}-{practiceLevel}.toml`,
validated by `MissionDefinition` (`app/schemas/missions.py`) and read through
`app.missions.get_mission`; its `content_version` is stored on the tasks it creates. The
first is `M01-A1.toml`, "Identify and describe an object": photo eligibility, one objective with its targets, permitted
language patterns (linked to the existing I-Spy clue frames), teaching sequence and
support rules, evaluation criteria and expected performance.

Missions reuse the existing task storage; no table or migration is involved:

| Data | Column | Visibility |
| --- | --- | --- |
| `missionId`, `practiceLevel`, `contentVersion` | `session_tasks.public_content` | public |
| `questionEvaluations` (objective, targets, evidence type, accepted answers or rubric criteria, corrections, hidden vocabulary/object targets) | `session_tasks.answer_key` | private |
| `question_assistance` (supports opened per question) | `task_attempts.response_payload` | owner |
| `questionOutcomes` | `task_attempts.evaluation_details` | released with the graded attempt |

The three mission fields are set together or not at all, must name a known definition,
and are omitted from JSON when absent, so tasks and saved sessions without a mission
keep their stored shape. `questionEvaluations` requires mission metadata, may only name
the task's own questions (`task` for tasks without grouped questions), and must agree
with the definition's objective, targets, evidence types and rubric criteria. A question's
accepted answer is its existing answer-key entry; `acceptedAnswers` is only for questions
without one.

Grouped-lesson attempts on tasks with `questionEvaluations` add `questionOutcomes`
beside the unchanged `questionResults` and `correctAnswers`. Each outcome is `correct`,
`incorrect` (with the matching correction rules as `mistakes`) or `unassessed` (no
evaluation metadata), and records the supports used; `assistanceUsed` is true only for
supports the mission counts as assistance. Outcomes describe the existing grading:
correctness, score, XP, vocabulary progress and learner history still come from
`questionResults`.

#### Mission lesson planning

Mission lessons apply to lesson sessions whose active language profile is A1 and whose
target language has reviewed forms (`es`, `fr`); every other session keeps the existing
lesson.

- **Photo requirements.** Each definition names only the confirmed facts it needs:
  `minConfirmedObjects` (different names), `minColouredObjects` (reviewed colours) and
  `minRelations` with the accepted `relations` types, and `minCountedGroups` with the
  `minQuantity`–`maxQuantity` range. M01 needs two objects with a colour each; M02 needs two
  objects and an on/under/next-to/in-front-of/behind relation; M03 needs one counted
  group of 2–10.
- **Counts.** The review's Counts tab sends `objectCounts` (object ID → 1–10). Each count
  is saved for the group of every confirmed object with the same name, so a group is
  counted once and a second count of it is a 409. Groups are stored in
  `analysisDraft.countedGroups` with `sceneObjectIds`, `label`, `quantity`,
  `suggestedQuantity` and `source` (`confirmed`, `corrected` or `entered`), and returned
  as `countedGroups`. A scene-analysis quantity is only offered as a suggestion, and a
  detected label never implies a count. No migration is needed.
- **Planner** (`app/services/mission_eligibility.py`). Confirming the scene checks every
  implemented A1 mission (M01, M02, then M03) against only the facts the learner
  confirmed, and plans every mission the photo supports, up to three. The plan is saved as
  `analysisDraft.missionPlan` before generation and generation reads only that snapshot.
  Sessions reviewed before plans were saved keep the regular lesson.
- **No mission fits.** The regular lesson runs and `analysisDraft.missionGuidance`
  (returned as `missionGuidance`) lists what each mission is missing; the lesson page
  shows it as a short note. Nothing is inferred and no scene is substituted.
- **Shared teaching.** Translation and one vocabulary introduction are checkpointed first,
  as before. The introduction carries no mission fields because it teaches the nouns for
  every planned mission; its per-word evidence still follows each word's own result.
- **Tasks.** Each planned mission adds one `grammarLesson` carrying its own mission fields,
  in plan order. Mission sessions end on their summary; choosing I-Spy there creates a
  separate game that reuses the confirmed scene inventory. Mission lessons publish no
  `explanation`, so the task page shows only the questions and, after submitting, the
  feedback. `app/services/mission_registry.py` maps each mission to its payload builder,
  generation spec and task builder.

#### M01 A1 lesson path

1. **Lesson** (`M01-A1.toml`; `app/ai/features/learning_tasks/mission_m01.py`,
   `app/services/mission_lessons_m01.py`). M01 needs two differently named confirmed
   objects that each have a confirmed colour with a reviewed form. Two object-colour
   pairs are chosen when the lesson is generated and saved in the task, so resuming
   keeps them. Pairs are ranked least familiar first: the object's
   `user_vocabulary_progress.mastery_score` in the target language plus the colour's
   past correct ratio from the learner-history snapshot (only when
   `LEARNER_MEMORY_ENABLED=true`; colours have no word-progress rows). Words without
   progress or history count as unseen; ties keep scene order. The `grammarLesson` has
   exactly four questions: identify object 1 (`¿Qué es esto?` / `Qu'est-ce que c'est ?`,
   choose `una taza` etc.), describe it with word tiles (`Es una taza roja.` /
   `C'est une tasse rouge.`), then the same for object 2. Identification distractors
   are nouns taught in this lesson or earlier for the same language, with a known
   gender, without duplicates. Every question carries `sceneObjectId` and the English
   `objectLabel`; the app crops the object from its bounding box or rings it on the
   photo. The lesson is built and validated deterministically with no model call.
2. **Bonus I-Spy.** The existing AI I-Spy clue and describing rounds are generated
   alongside the lesson, as in the legacy path, and placed last without mission
   fields. They unlock once the learning tasks are done and are labelled as the
   bonus round.
3. **Grading.** Answers are graded from the private answer key. Each
   `questionOutcomes` entry names its targets; evidence type is derived from the
   interaction (`recognition` for multiple choice, `construction` for sentence
   building) and the word bank is always recorded as support, so a sentence counts as
   supported practice, not independent writing. Supports a question does not offer are
   rejected with a 409. Each word's vocabulary evidence uses only the questions that
   assess it. Replays with the same idempotency key return the saved attempt without
   new results or XP.
4. **Completion.** The session completes through the existing lifecycle and completion
   XP once every task, including every mission task and the bonus rounds, is completed or
   skipped. If no I-Spy task was generated, the final learning step shows "Finish lesson"
   instead.

#### M02 A1 lesson path

`M02-A1.toml`, "Find and locate": say where a photo object is, ask where it is and
check a short answer against the photo. This is supported A1 practice, not independent
A2 location production.

1. **Payload** (`app/services/mission_lessons_m02.py`). Each confirmed relation whose
   position has a reviewed phrase and whose objects have reviewed articles, with its
   statement tiles (`La` / `taza` / `está` / `al lado del` / `libro` / `.`; a contracted
   or multiword phrase is one tile), `whereQuestion` (`¿Dónde está la taza?`), the
   positions true for that pair (including inverse relations), the positions they
   contradict (on/under, in front of/behind) and a proposed answer for the optional check.
   Positions reuse the I-Spy reviewed bank.
2. **Selection.** Relations are ranked by the learner-history correct ratio of their
   position phrase (snapshot only with `LEARNER_MEMORY_ENABLED=true`; otherwise every
   phrase is unseen), ties in photo order. The core questions use the least familiar. A
   second relation is selected only if it has another object pair or position; otherwise
   M02 has three questions. The selection is stored in the generated task.
3. **Lesson** (`app/ai/features/learning_tasks/mission_m02.py`). Built without a model
   call and validated: one `grammarLesson`, "Find and locate", with three core questions
   about the first relation — pick the phrase from three, none of the wrong ones true for
   the pair (`Elige la posición: la taza ___ la mesa.`); build the statement with one
   extra phrase tile (`Describe la posición de la taza.`); build the where-question
   (`Pregunta por la ubicación de la taza.`) — and, only with a second relation, a Yes/No
   check on the photo (`“El libro está debajo de la mesa.” ¿Coincide con la foto?`). The
   proposal is the true statement or, for about half the relations, an opposite position
   the confirmed relation contradicts; the feedback gives the correct statement. Every
   question uses the learner's photo with `sceneObjectId`/`objectLabel` (and
   `referenceObjectId`/`referenceLabel` except the where-question). Prompts are in the
   target language with an English `promptTranslation`, and never contain the sentence
   the learner builds.
4. **Grading.** The questions are one task attempt. Phrase and Yes/No choices are
   recognition with `wrongPosition` corrections; the statement and question are supported
   construction (`wordBank`), and only those name object words for evidence.
   `GET /tasks/{id}/latest-attempt` also returns the saved `answers` and `reviewDetails`
   for mission lessons, so a reloaded graded lesson still shows its answers, grades and
   corrections.

#### M03 A1 lesson path

`M03-A1.toml`, "Say how many": say a confirmed quantity with the taught pattern
(`Hay tres libros.`, `Il y a trois livres.`) and the noun's regular plural.

1. **Payload** (`app/services/mission_lessons_m03.py`, `app/services/quantities.py`). The
   first counted group of 2–10 whose translated noun has a reviewed regular plural, with
   its reviewed number word, singular, plural, statement, English meaning and nearby
   wrong quantities. Plurals come only from regular rules (es vowel + `s`, `-d/-l/-r/-j`
   + `es` without accent changes; fr + `s`, excluding `-s/-x/-z/-au/-eu/-al/-ail` and the
   `-ou` exceptions) and must match any recorded plural. Otherwise the session records
   `analysisDraft.skippedMissions` and keeps its other tasks; with no mission task left
   the regular lesson is used.
2. **Lesson** (`app/ai/features/learning_tasks/mission_m03.py`). Exactly one
   `grammarLesson` with 2–4 questions: quantity comprehension, choosing the statement
   (distractors use a wrong number or the singular), then a word-bank statement whose
   bank adds the singular and a wrong number. Its validator and fallback check the group, quantity
   and plural, and its cache identity is `learning-tasks.m03-a1.v1:M03-A1.v1`.
3. **Grading** follows M01. Corrections name `wrongQuantity` or `pluralForm` when the
   answer shows which (both for a wrong number with a singular noun), and `wordOrder`
   otherwise. A rule without listed answers applies only when no specific rule matches.

### Backend performance

Measured with `tests/test_performance.py` and a profiling run against local
PostgreSQL. All five AI features were configured with test keys, and fake
lesson and clue models each took 0.3 s.

| Measurement | Before | After |
| --- | --- | --- |
| AI clients built per `GET /sessions/{id}` or `/sessions/active` | 5, on every request | 0; each client is built once per process, on first use |
| Queries per `GET /sessions/{id}` / `/sessions/active` | 7 / 8 | 7 / 8 (no repeated reads found) |
| Review until all tasks are ready | 0.85 s | 0.55 s |
| Queries for review plus task generation | 57 | 51 |
| Longest write transaction during generation | 18–22 ms | 19 ms |

- `AiRuntime` (`app/ai/runtime.py`) is stored on `app.state` and shared by every
  request. It builds a feature service only when a workflow first calls it, so
  polling never constructs OpenAI or Gemini clients.
- After translation, learning-task and I-Spy clue generation run at the same time.
  The clue call uses a one-thread executor owned by the generation job, never the
  shared background pool. That allows at most two model calls per
  `BACKGROUND_WORKERS` slot and cannot deadlock the pool. Each call keeps its own
  fallback: failed lessons keep generated clues, and failed clues keep generated
  lessons.
- The generation claim keeps only the session title, objects and relations. The
  translation checkpoint reads only objects and vocabulary, so it no longer re-reads
  the session, media asset, curated scene or the just-cleared task list.
- No responses are cached. `app.repositories.postgres.workflow` logs
  `Task generation <stage> took N ms` at INFO for translation, learning-task
  generation and I-Spy clue generation, and transaction duration at DEBUG.

### AI configuration

Credentials, deployments, models and routes come from a TOML file:
`backend/ai.toml` by default, or the file named by `AI_CONFIG_FILE`. The
default path is resolved from the package, so it loads from any working
directory. The file holds no secrets. It has three sections:

- `[credentials.<id>]`: the `adapter` the credential is for, the `env` variables
  that may hold its secret (the first non-empty one wins), and its shared
  `quota_group` and `billing_group`.
- `[deployments.<id>]`: `adapter`, `api` (`responses` or `generateContent`),
  `model`, `capabilities` (`text`, `vision`, `jsonSchema`), the eligible
  `credentials`, generation `defaults` (`timeout_seconds`,
  `max_output_tokens`, `max_retries`, `temperature`), and, for OpenRouter
  only, a required `upstream_fallback` (see [AI routing](#ai-routing)).
- `[routes.<feature>]`, one for each of `sceneAnalysis`, `sceneTranslation`,
  `learningTask`, `ispyClue` and `ispyGuess`:
  - `enabled`;
  - the approved `deployments`;
  - `policy`: `priority` tries the deployments in listed order; `primary` uses
    only the first. Both rotate the deployment's credentials;
  - `deadline_seconds` and `max_model_calls`: the deadline and total
    outbound-call budget for one feature operation, enforced by the router.

There is no per-feature environment fallback. Variables such as
`AI_SCENE_TRANSLATION_MODEL`, `TRANSLATION_PROVIDER`, `OPENAI_API_KEY` or
`VISION_MODEL_NAME` are no longer read; change the TOML instead. The
environment supplies only:

- secrets, from the variables each credential names (`AI_OPENROUTER_API_KEY`,
  `AI_OPENAI_API_KEY`, `AI_GEMINI_API_KEY` in the default file). OpenAI image
  moderation uses the first `openai` credential with a secret;
- `AI_MODE` and, optionally, `AI_CONFIG_FILE`;
- result cache, observability, image moderation and object grounding settings.

`.env.example` lists exactly these.

Validation runs at startup and makes no network calls. It checks:
- that every reference resolves, and each credential matches its deployment's
  adapter;
- that each adapter supports its deployment's API and capabilities, and each
  route's deployments have the capabilities its feature needs (`sceneAnalysis`
  needs `vision`);
- that enabled routes have deployments, a deadline at least the primary
  timeout, and a call budget covering its retries.

With `AI_MODE=real`, every enabled route must also resolve a secret; with
`demo`, a route without one falls back to deterministic behaviour.

Uploaded-image analysis runs on the `sceneAnalysis` route, which uses OpenRouter
in the default `ai.toml`; `AI_OPENROUTER_API_KEY` is required. In `demo` mode,
missing this secret does not prevent startup, but uploaded photos fail analysis
with a retryable “We couldn't analyse that photo” error instead of receiving
placeholder objects. The backend warning names the missing variable, and this
failure is logged with `code=analysisUnavailable`. Curated scenes are unaffected.

Error messages name keys and variables but never echo values, and secrets
are excluded from `AiSettings` repr.

### AI providers

Feature services in `app/ai/features/` depend only on the contracts in
`app/ai/contracts/`: `TextModelClient` and `VisionModelClient`, their
request/response types, `ProviderError` and `build_strict_json_schema`.
`app/ai/registry.py` picks an adapter from `app/ai/adapters/` for each
configured provider:

| Provider | Adapters | Endpoint |
| --- | --- | --- |
| OpenAI | `OpenAITextClient`, `OpenAIVisionClient` | Responses API |
| OpenRouter | `OpenRouterTextClient`, `OpenRouterVisionClient` | OpenRouter's OpenAI-compatible Responses API |
| Gemini | `GeminiTextClient`, `GeminiVisionClient` | `models.generate_content` (google-genai) |

OpenAI and OpenRouter share the transport in `responses_api.py`. Each
`ResponsesEndpoint` declares the options it is sent (temperature, strict JSON
schema), where its request ID comes from and its own failure scopes. Image
moderation and object grounding don't go through these adapters.

Every successful response carries `metadata` (`ResponseMetadata`): provider,
endpoint, requested model, the model the provider reports serving, request
ID, a normalized `finish_status` plus the provider's own finish reason, and
input/output/total tokens when the provider reports them. Every
`ProviderError` carries a stable `code`, `provider`, HTTP `status_code`,
`retry_after_seconds` (from `Retry-After`, `retry-after-ms` or Gemini's
`RetryInfo`) and a `scope`: `request`, `response`, `model`, `credentials`,
`quota` or `service`. Error messages are fixed text; provider response bodies
and API keys never appear in errors or logs. Validation and fallbacks stay in
each feature.

### Credential pool

Every model call leases a credential from the app-wide `CredentialPool`
(`app/ai/pool.py`), shared by all features through `AiRuntime`:

- **Selection:** a deployment's eligible credentials are tried round robin,
  skipping any without a secret, disabled, or cooling down (itself or its
  `quota_group`). A lock guards only selection and health updates; it is
  never held during a model call.
- **Clients:** one immutable client per deployment, credential and model
  config, built on first use and reused. A shared client's key or model is
  never changed.
- **Health** is tracked separately per credential, quota group and deployment:

| Provider error | Effect |
| --- | --- |
| Authentication failure (`providerAuth`, `credentials` scope) | Disables that credential for the process |
| Rate limit (`providerRateLimited`, `quota` scope) | Cools down the quota group for `retry_after_seconds`, else 10 s |
| Credits exhausted (OpenRouter 402, Gemini `FAILED_PRECONDITION`, OpenAI `insufficient_quota`) | Cools down the quota group for `retry_after_seconds`, else 300 s |
| `model` scope (e.g. 404) | Cools down the deployment for `retry_after_seconds`, else 30 s |
| `service` scope with `retry_after_seconds` | Cools down the deployment for that long |
| `service` scope without it, `request` or `response` scope | No cooldown; service failures only count toward deployment health |

A plain 429 is treated as a rate limit, never as exhausted credits. When
nothing is eligible the call fails at once, with no network request, as `providerRateLimited` (with the soonest retry-after) or
`providerAuth`, and the feature falls back as before. Cooldowns use an
injectable clock, and health lives behind the `PoolState` interface
(`InMemoryPoolState` today). There are no per-user quotas.

### AI routing

Feature services call `RoutedModelClient` (`app/ai/routing/`), which
implements the text and vision contracts. Each feature operation opens one
`InvocationContext` holding the route's `deadline_seconds` and
`max_model_calls`; router failover and the feature's validation repair share
it, so together they never exceed either.

For each outbound call the router picks the route's next deployment in
priority order, leases a credential round robin from the pool, reuses that
deployment and credential's immutable client and caps the call's timeout at
the time left. It never sleeps.

| Failure | Router |
| --- | --- |
| Timeout, 5xx, rate limit, exhausted credits, unknown model | Next credential (quota) or next deployment (service, model) |
| Authentication | Disables that credential, then the next credential or deployment |
| Refusal, content filter, request or schema error (`request` scope) | Stops: terminal |
| Invalid model output (`providerResponseInvalid`) | Returned to the feature's repair step |

Failover stops once the budget or deadline is spent, and the last provider
error is raised. Features no longer retry transport errors themselves; they
keep only their validation repair, at most `max_retries` (≤ 1) repairs and
only while the budget allows. With one deployment per route, call counts and
fallbacks match the previous behaviour. A client injected directly into a
feature (tests, scripts) gets a one-deployment route with a budget of
`1 + max_retries` calls.

**SDK retries:** every adapter makes exactly one HTTP request per call, so
the budget counts every attempt we make. `httpx` never retries, Gemini pins
`HttpRetryOptions(attempts=1)`, and the eval judge's OpenAI SDK uses
`max_retries=0`.

**OpenRouter upstream fallback:** OpenRouter deployments must set
`upstream_fallback`, sent as `provider.allow_fallbacks` (plus `models` when
fallback models are listed). The default keeps OpenRouter's fallback on, as
before. OpenRouter's internal attempts on other hosts or models happen inside
one HTTP request, so `max_model_calls` counts them as one call and cannot
see or limit them; only the deadline bounds them.

**Tracing:** each outbound call is a `model-call` span with the deployment,
credential ID (never the secret), provider, requested model, attempt number,
the fallback reason so far, the outcome (`success`, `failover`, `terminal`),
error code, scope and status, latency and token usage. The feature's
generation records the deployment, credential ID and model that served it,
the route's attempts, the fallback reason and input/output/total tokens.
`retry_count` counts every outbound call after the first.

### AI result cache

Scene translation, learning tasks and I-Spy clues share an in-memory cache of
validated results (`app/ai/cache/`), one per API process, built once by
`AiRuntime`. It is lost on restart and needs no migration; `CacheStore` is the
interface for a shared store later.

- **What is stored:** only results that passed the feature's validators.
  Refusals, provider errors, invalid output and deterministic fallbacks are
  never stored.
- **Key:** SHA-256 of the canonical payload (scene title and summary, labels,
  attributes, relations, anchor points), target language, the feature's
  prompt, schema and validator versions, the model, temperature and max
  output tokens of every deployment the route allows, and the scope.
- **Session IDs:** object, attribute and relation keys are replaced by aliases
  assigned from content (`o1`, `o1:color`, `r1`), so the same scene in another
  session gets the same key. Duplicate objects keep separate aliases and
  relations keep their endpoints. A hit is mapped back to the current IDs and
  validated again; a result referencing an unknown key is never stored.
- **Provenance:** each entry records its deployment, model, versions and
  creation time. A hit whose deployment is no longer in the route is dropped.
- **Scope:** an active preloaded scene whose objects, labels, attributes and
  server-suggested relations are unchanged is shared by all users. Anything
  else (uploaded photos, added objects, edited attributes or relations) is
  scoped to the learner. The cache is consulted where the model was called,
  after ownership checks, review, upload moderation and the generation claim;
  revision guards still apply to cached results.
- **Concurrent misses:** one request generates and the others wait, at most
  for the route's deadline plus 5 s. If it fails, they all get the same
  failure and use the feature's usual fallback, with no extra model calls.
- **Controls:** `AI_RESULT_CACHE_ENABLED` (default `true`),
  `AI_RESULT_CACHE_TTL_SECONDS` (default `86400`) and
  `AI_RESULT_CACHE_MAX_ENTRIES` (default `2000`, least recently used evicted).
  Passing `cache_scope=None` bypasses the cache (the precompute script never
  uses it). `ResultCache.invalidate(feature=..., scope=...)` and `clear()`
  drop entries. Bump a feature's `*_VALIDATOR_VERSION` when its validation
  rules change.
- **Output quality:** a hit already passed the same validators and is checked
  again, and a miss sends the same request as before. Learners replaying a
  curated scene get the same tasks within the TTL; with temperature 0 that
  removes only incidental provider variation. Model updates behind an
  unchanged model name appear once entries expire or are invalidated.

### AI observability

AI calls can be traced to Langfuse. Tracing is off by default and strictly
best-effort: without keys the app runs a no-op tracer, and a tracing failure
never affects a learner request or blocks the request path (export is
asynchronous). Today exactly one operation is instrumented — I-Spy
description evaluation (`ispy-description-evaluation`), recorded as a
generation with provider/model dimensions, validation outcome, latency and
error codes.

Variables: `AI_OBSERVABILITY_ENABLED`,
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

Speech evaluation is not implemented. Without the `sceneAnalysis` secret
(`AI_OPENROUTER_API_KEY` by default), demo mode still starts, but uploaded photos
fail analysis with a retryable “We couldn't analyse that photo” error instead
of getting placeholder objects. The backend logs the missing variable and
`code=analysisUnavailable`; curated scenes are unaffected (see
[AI configuration](#ai-configuration)). Vocabulary "Move" is still local frontend state. Session learning credit comes from persisted
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

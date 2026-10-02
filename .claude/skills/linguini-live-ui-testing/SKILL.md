---
name: linguini-live-ui-testing
description: Set up Linguini browser tests against the intended database and capture session lifecycle evidence without creating unnecessary live data.
---

# Linguini UI testing

## Environment
- Confirm the backend process command, start time, cwd, and reload flag before reusing it; a stale non-reloading process can serve pre-PR behavior.
- Compare database hosts and credential presence without printing secrets. Do not assume `backend/.env.local` targets Supabase: it may contain local test-DB settings and empty storage values while inherited session bindings contain the intended live configuration.
- Never copy live credentials into tracked files or overwrite the user's local env file.
- With live credentials inherited, start from `backend/`: `CORS_ALLOWED_ORIGINS='http://localhost:5173,http://127.0.0.1:5173,<preview-origin>' MEDIA_STORAGE_PRIVATE=true MEDIA_STORAGE_BUCKET=media-assets .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`.
- Vite may run on 5174 behind a single-origin proxy on 5173. Inspect running processes first. Temporarily use `VITE_API_BASE_URL=http://127.0.0.1:8000` for desktop testing; restore the original value afterward.
- Confirm OPTIONS permits the browser origin before session mutations. A CORS failure can hide a successful server-side create; recover by same-scene/idempotent retry rather than creating more sessions.

## Devin Secrets Needed
- `DATABASE_URL` and `DIRECT_URL` for the intended database.
- `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` for private media.
- `DEMO_USER_ID` for the intended demo account.

## UI session flow
- Practice → choose a current catalog scene → Scene analysis → remove unwanted words → Continue → Use typing instead → Continue → learning tasks → I-Spy → reflection → Finish session.
- Keeping one word gives six learning tasks plus one I-Spy and one reflection, minimizing live writes while exercising completion.
- Capture real session/task API responses alongside UI actions. Verify identity and completed task IDs when testing resume, not just the visual page.
- `analyzingScene` and `generatingTasks` may occur entirely within transactions; assert externally observable `created`, `awaitingObjectReview`, `inProgress`, and `completed` without claiming GET can see transaction-internal states.
- If app discard is absent, explicitly label Swagger `POST /api/v1/sessions/{session_id}/abandon` as a backend-only workaround. Do not confuse Exit navigation with abandonment.
- Prefer preloaded scenes for conflict tests to avoid orphan uploads. Finish or explicitly abandon every test-created session; verify GET active returns null at cleanup.

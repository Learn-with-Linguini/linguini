---
name: linguini-live-ui-testing
description: Set up Linguini browser tests against the intended environment and verify saved practice, ownership, retries and session recovery without creating unnecessary live data.
---

# Linguini UI testing

## Environment

- Read the root and frontend `AGENTS.md` files and the app setup guides.
- Prefer a disposable local database. Never run the automated integration suite against the deployed Supabase database.
- Confirm the backend process command, start time, working directory and reload flag before reusing it. A stale process can serve behavior from an earlier checkout.
- Inspect configuration names and database hosts without printing credentials. Do not assume `backend/.env.local` targets the environment named in the task.
- Keep live credentials out of tracked files and preserve the user's existing environment files.
- Match `VITE_API_BASE_URL` to the API origin without `/api/v1`, and include the browser's exact origin in `CORS_ALLOWED_ORIGINS`. Inspect running ports before starting another server.
- Use `AUTH_MODE=demo` only for an isolated local test account. Production checks require real sign-in; a development route guard is not evidence that the API permits unauthenticated access.
- Confirm CORS preflight succeeds before mutations. A browser CORS error can hide a successful create; recover the existing session before retrying a creation.

## Practice flow

- Sign in or select the intended local demo account, then record the active language and proficiency level.
- Open Practice and choose a current catalog scene. Prefer curated scenes for lifecycle checks; use uploads only when the photo flow is under test.
- Follow the returned scene-review and mission-readiness requirements. Do not assume a fixed number of selected words, tasks or lesson stages.
- Review the photo facts, continue into the offered lesson, complete its tasks, and open the summary. Exercise I-Spy only when that session includes it; standalone I-Spy uses `/ispy/games/:sessionId/...`.
- Capture session and task API responses alongside visible UI behavior. Verify the session ID, task IDs and server status when testing resume, not only the rendered screen.
- Refresh at a meaningful boundary and check that saved answers and the resume destination survive. Use `src/lib/sessionRoute.ts` as the route contract.
- Check that ownership failures cannot reveal another account's session, task, journal or private photo. Use separate test accounts and avoid copying private data into screenshots or logs.
- Treat backend-calculated grades, learning evidence and rewards as authoritative. A completed animation or local counter is not proof that a save succeeded.

## Retry and cleanup

- Distinguish navigation away from an explicit abandon action. If a backend-only endpoint is used for cleanup, label it as such in the result.
- Retry lost responses through the existing idempotent action where available; do not create duplicate sessions to hide a failed restore.
- Do not claim that GET requests can observe states that exist only inside a transaction.
- Finish or explicitly abandon sessions created by the test, and verify the active-session endpoint no longer returns them.
- Report the environment, flows exercised, checks that passed and any skipped checks. Do not claim production verification from a local run.

# Linguini frontend guide

Read the root `AGENTS.md` for repository workflow, attribution, checks, and safety.
Read `design.md` before changing visuals.

## Current application

This directory contains the React 19 / TypeScript / Vite SPA. Run frontend commands
from `frontend/`, not the repository root:

```sh
npm ci
npm run lint
npm run build
npm run test
```

The application uses the FastAPI API under `/api/v1`, Supabase authentication, and
TanStack Query. Practice, vocabulary, progress, profiles, and journals persist on
the backend. Do not replace this with mock data or local XP calculations.

```text
src/components/   Shared controls, shells, photo renderers, route guards
src/pages/        Screen components
src/data/types.ts Frontend domain types
src/lib/          API client, query keys, session routes, speech helpers
src/state/        Authentication, queries, account and practice hooks
src/styles/       Global styles and design tokens
tests/            Frontend behavior tests
public/           Brand assets and bundled photos
design.md         Product and visual guidelines
```

## Integration and state

- Use `src/lib/api.ts` for requests. Align types with backend Pydantic/OpenAPI contracts.
- Use `src/lib/queryKeys.ts` and existing query hooks. Scope learner data to the account and active language profile, and invalidate the relevant queries after mutations.
- The backend decides correctness, learning evidence, XP, and session status. The browser renders returned state and preserves pending input; it does not invent rewards or completion.
- Authentication lives in `src/state/Auth.tsx`. Development route behavior does not imply public access is permitted by the backend.
- Practice routes use `/practice/sessions/:sessionId/...` and `SessionRoute`; catalog scene links use `SceneRoute`. Keep `src/lib/sessionRoute.ts` as the canonical resume destination and preserve the current-page feedback after a successful answer.
- Render explicit loading, empty, retry, and error states. Use the existing loading and error components. Do not turn a failed restore into a fresh unanswered task.
- Keep secrets out of frontend code. Only public configuration belongs in Vite variables; service credentials remain on the backend.

## Photos and vocabulary

- Reuse `SceneVisual`, `SceneImage`, `MediaImage`, and `JournalImage` according to the data available. Preserve their image-loading behavior and accessible failed-photo placeholders.
- `ScenePhoto` places object markers over the scene. Preserve the image aspect ratio, normalized coordinates, and 44px marker targets.
- Photo ownership and media access are enforced by the backend. A room code or a frontend URL must never bypass them.
- Vocabulary records include photo provenance. Keep learning evidence distinct from user-selected journal words and participation counters.

## UI system

- Reuse controls from `src/components/ui.tsx` and `ui.css`, with tokens from `src/styles/tokens.css`.
- Keep the supplied wordmark in the shared pasta-cream header; it scrolls with the initial view. Use one shared back chevron, not a second in-page back button.
- Headings use **Baloo 2**; body, labels, and controls use **Nunito Sans**.
- Primary action buttons are filled tomato; meaningful secondary actions are filled teal. Preserve their shared press depth. Quiet controls and answer choices may use their existing state styling.
- Keep Home calm: seven-day streak, one featured next action, vocabulary below it, and an optional journal action. Supporting features must not turn Home into a grid of competing actions.
- Scene selection and analysis are unnumbered. Visible learning progress begins after the scene is selected.
- Preserve visible focus, 44px icon targets, 48px action height, written feedback alongside color, and reduced-motion support.
- The journal shows one month/year with previous/next controls, including empty months. Reuse the existing photo mosaic and entry renderers.

## Analytics convention

Follow the root [analytics convention](../AGENTS.md#analytics-convention). Frontend actions use `trackAction` from `src/lib/analytics.ts`; event and page documentation lives in [ANALYTICS.md](../ANALYTICS.md).

## Review

Run lint, build, and the existing tests after behavior changes. Add tests for material
state, ownership, retry, or rendering regressions; avoid tests that only mirror an
implementation detail. Inspect mobile layouts when changing a learning screen.

# Feature screenshots

Phone captures (440×900, captured at 2× device scale and downsized, like the screenshots one level up) of every learner-facing route in `frontend/src/App.tsx`. They feed the feature posters and tour in [`marketing/feature-posters/`](../../../marketing/feature-posters/features.json).

## How they were captured

- Backend from `backend/` with `AUTH_MODE=demo`, `AI_MODE=demo`, a local PostgreSQL database migrated with `npm run db:deploy`, the seeded demo user (Maya, `DEMO_USER_ID`) and a working OpenRouter key, so scene analysis, translation, lessons and I-Spy guesses are real model output.
- Frontend with `npm run dev`, where `RequireAuth` lets the demo session through.
- A 440×900 mobile viewport at device scale factor 2, driven with Playwright. The practice flow uploads a real desk photo (JPEG, under 10 MB) through the gallery input on `/practice`.
- Spanish A1 for most screens, Spanish A2 for mission M06, and Korean A1 for the grammar tasks and in-lesson I-Spy (see the notes below). Chefs of the Day shows Maya beside five local test learners.

## Prefixes

| Prefix | Route / component |
| --- | --- |
| `onboarding-*` | `/onboarding` (`OnboardingSteps.tsx`), including the placement check |
| `home*` | `/home` |
| `practice-*` | `/practice` (`PracticeSelect.tsx`, `ImageUpload.tsx`) |
| `analysis-*` | `/practice/sessions/:id/analysis` |
| `learn*` | `learn`, `learn/vocabulary-preview`, `learn/:taskId` |
| `mission-m0*` | Mission tasks M01–M06 in `LearningTaskPage.tsx` |
| `lesson-ispy*` | In-lesson `ispy-1` / `ispy-2` |
| `summary*` | `summary` (`SessionSummary.tsx`) |
| `ispy-*` | `/ispy`, `/ispy/play`, `/ispy/games/:id/{clues,describe,results}`, `/ispy/challenge`, `/ispy/friends`, `/rooms/:roomId` |
| `leaderboard-*` | Chefs of the Day (`ChefOfTheDay.tsx`) |
| `progress*` | `/progress` |
| `revisit-*` | `/vocabulary` journey and list views, completed-scene `review` |
| `journal*` | `/journal`, `/journal/new`, `/journal/:entryId` |
| `profile*` | `/profile`, `/profile/edit`, `/payment` |

## Not captured, or only partly

- **Weekly leaderboard.** `GET /api/v1/me/progress` returns a `leaderboard` array, but no screen renders it yet (`Progress.tsx` doesn't read the field), so there's nothing to screenshot. Chefs of the Day is the only leaderboard UI.
- **Mission M06** only appears for an A2 profile, and only when the confirmed scene has an object you could ask for (`requestableItem` in `mission_eligibility_a2.py`). The desk photo qualifies (notebook, pencil). M01–M05 come from Spanish A1 lessons.
- **In-lesson I-Spy** isn't built for mission lessons (`workflow.py` skips the describing tasks when a lesson has missions), so Spanish, French and German lessons that include missions go straight to the "no describing round" screen (`lesson-ispy2-no-round.png`). The `lesson-ispy*` screens come from a Korean lesson, which has no missions.
- **Friends rooms** were captured for one player only (room list and a newly created room). Playing a round with a second account was not exercised.
- **Daily challenge** shows the challenge page. Submitting a challenge photo and the completed state were not captured.
- **Camera capture** opens the device camera through a `capture` file input. Headless Chromium has no camera, so `practice-capture.png` shows the Click/Upload choice and the upload path is the one exercised end to end.

# Linguini Analytics Documentation

Linguini uses dual-dispatch analytics combining **Google Analytics 4 (GA4)** and **Contentsquare**.
All tracking helpers are centralized in `frontend/src/lib/analytics.ts`.

---

## 1. Environment Configuration

### GA4 Measurement IDs

| Environment | Hostname | GA4 Measurement ID |
| :--- | :--- | :--- |
| **Development / Staging** | `dev.learnwithlinguini.com` | `G-ET4KFFXFMZ` |
| **Production** | `www.learnwithlinguini.com` / `learnwithlinguini.com` | `G-CHBF82TVG3` |

### Setting Environment Variables

In `frontend/.env.local` (or in deployment environment variables like Railway/Vercel):

```ini
# Google Analytics 4 Measurement ID
VITE_GA_MEASUREMENT_ID=G-ET4KFFXFMZ
```

> **Automatic Fallback:** If `VITE_GA_MEASUREMENT_ID` is omitted, `resolveGaMeasurementId()` automatically resolves the correct ID by checking `window.location.hostname`.

---

## 2. Contentsquare Integration & SPA Pageview Tracking

The Contentsquare tag script is loaded in `frontend/index.html`:
```html
<script async src="https://t.contentsquare.net/uxa/6a01544c67dfc.js"></script>
```

Because Linguini is a single-page application (SPA), route changes do not reload the document. The `<AnalyticsTracker />` component in `frontend/src/components/AnalyticsTracker.tsx` listens to router location changes and dispatches pageview events on every navigation:
* **Contentsquare:** `window._uxa.push(["trackPageview", currentPath])`
* **GA4:** `gtag("event", "page_view", { page_path, page_title, page_location })`

### Tracked Pages & Routes

#### Marketing Pages
* `/` — Landing page with interactive hero demo and feature highlights
* `/blog` — Engineering & language learning blog index
* `/blog/:slug` — Individual blog posts
* `/pricing` — Pricing and plan comparison table
* `/faq` — Frequently asked questions
* `/about` — About Linguini
* `/privacy` — Privacy policy
* `/terms` — Terms of service
* `/learn/:lang` — Targeted language landing pages (e.g. Spanish, French, German, Korean)

#### Learner Application Pages
* `/home` — Learner dashboard (streak, daily photo lesson, journal prompt, quick links)
* `/onboarding` — Language pairing and level selection
* `/practice` — Photo capture / scene selector
* `/practice/sessions/:sessionId/*` — Active lesson tasks (word cards, grammar, description)
* `/practice/ispy` — Standalone I-Spy mode selector (Solo vs Friends)
* `/practice/ispy/join` — Enter invite code to join a room
* `/practice/ispy/room/:roomCode` — Multiplayer I-Spy gameplay room
* `/rooms` — Active and previous multiplayer rooms list
* `/vocabulary` — Learned words, audio pronunciation, and mastery filters
* `/journal` — Calendar diary of daily practice entries and photo attachments
* `/journal/new` — Create new daily journal entry
* `/journal/entry/:entryId` — View/edit specific journal entry
* `/profile` — User profile, target language settings, account plan, and feedback
* `/payment` — Stripe subscription and tier checkout (Beta / Free / Plus)
* `/contact` — Support and issue reporting
* `/login` — Sign in, registration, and Google OAuth
* `/reset-password` — Password recovery entry and confirmation

---

## 3. GA4 & Contentsquare Action Events Catalog

Actions are logged via `trackAction(eventName, params)`. Each call sends:
1. `gtag("event", action, params)` to GA4.
2. `window._uxa.push(["trackCustomEvent", action, params])` to Contentsquare.

### Authentication & Account Management
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `login_submitted` | `{ method: "email" }` | User submits the email/password sign-in form |
| `signup_submitted` | `{ method: "email" }` | User submits new account registration |
| `google_signin_clicked` | — | User clicks "Continue with Google" button |
| `forgot_password_requested` | — | User submits email to request password reset link |
| `password_reset_completed` | — | User submits and sets a new password on `/reset-password` |
| `profile_password_changed` | — | Authenticated user changes password from Profile page |
| `logout_clicked` | — | User clicks "Log Out" in Profile |
| `account_deleted` | — | User confirms account deletion request |

### Onboarding & Setup
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `onboarding_completed` | `{ language, minutes, level }` | Learner completes initial onboarding questionnaire |

### Practice, Photo Lessons & Scene Analysis
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `practice_session_started` | `{ assetId }` | New photo lesson session initialized |
| `practice_session_resumed` | — | User resumes an existing incomplete practice session |
| `practice_photo_uploaded` | `{ assetId }` | User captures/uploads a personal camera roll photo |
| `practice_scene_selected` | `{ sceneId, title }` | User selects a curated catalog scene |
| `scene_review_confirmed` | `{ acceptedCount, addedCount }` | User confirms detected objects before generating lesson |
| `scene_analysis_retried` | `{ sessionId }` | User requests AI re-analysis of a photo |
| `task_answer_checked` | `{ taskId, isCorrect, kind }` | Learner checks answer on an interactive exercise |
| `task_completed` | `{ taskId, kind }` | Learner completes reading or informational task |
| `session_summary_viewed` | `{ xpEarned, wordsLearnedCount, ispyCorrectCount, completedLessonsCount }` | Session summary screen displays upon finishing a lesson |
| `summary_journal_cta_clicked` | — | User clicks "Write today's journal entry" from summary |
| `summary_review_words_cta_clicked` | — | User clicks "Review difficult words" from summary |
| `summary_play_ispy_clicked` | — | User clicks "Play I-Spy with this scene" from summary |

### I-Spy & Multiplayer Rooms
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `ispy_mode_selected` | `{ mode: "ai" \| "friend" }` | User selects AI solo play or Multiplayer friend mode |
| `ispy_game_resumed` | — | User resumes an active I-Spy game session |
| `ispy_clue_submitted` | `{ optionId, isCorrect }` | Learner chooses an object in response to Linguini's clue |
| `ispy_description_submitted` | `{ outcome }` | Learner writes a description clue for Linguini to guess |
| `ispy_match_confirmed` | — | Learner confirms Linguini guessed their object correctly |
| `room_created` | — | User creates a new multiplayer room |
| `room_joined` | — | User joins a friend's room using a room code |
| `room_action_executed` | `{ intent }` | Multiplayer game action dispatched (ready, turn, etc.) |
| `game_accent_selected` | `{ appearance }` | Learner equips or buys an accent using Sauce/Basil |

### Vocabulary & Journal
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `journal_entry_saved` | `{ hasPhotos, wordCount, isNew }` | Daily journal entry saved or updated |
| `vocabulary_view_toggled` | `{ view }` | Switched between journey tree and list views |
| `vocabulary_filters_applied` | `{ wordClass, category }` | Filter applied to vocabulary collection |
| `vocabulary_audio_played` | `{ word }` | Learner plays audio pronunciation for a target word |

### Payments, Tiers & Subscriptions
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `payment_checkout_started` | `{ tier, price, currency }` | User clicks "Upgrade to Plus" to open Stripe Checkout |
| `payment_portal_opened` | `{ currentTier }` | Active subscriber opens Stripe Customer Portal |
| `payment_checkout_completed` | `{ status: "success" }` | User successfully returns from Stripe Checkout |
| `payment_checkout_cancelled` | `{ status: "cancelled" }` | User cancels Stripe Checkout and returns |
| `payment_test_tier_switched` | `{ targetTier }` | Dev/test toolbox switches tier between beta/free/plus |

### Feedback, Support & Social
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `survey_rating_selected` | `{ rating }` | User taps a 1–5 mascot emotion in the survey overlay |
| `survey_submitted` | `{ rating, triggerSource, receiveFollowUp, lessonCount }` | User submits "Help us improve" in-app survey |
| `support_message_sent` | `{ issueType, authenticated }` | User submits contact/support message |
| `lesson_issue_reported` | `{ reportType, issue }` | Learner reports an error in a lesson translation/task |
| `social_link_clicked` | `{ platform }` | User clicks LinkedIn, Instagram, X, or TikTok link |

### Marketing Site & Interactive Demo
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `demo_stage_viewed` | `{ stage, xpGained }` | Landing page interactive hero demo advances to next stage |
| `demo_completed` | `{ xp, lang }` | Interactive hero demo finished |
| `pricing_cta_clicked` | `{ tier }` | User clicks plan call-to-action on the pricing page |

---

## 4. Requirement for New Functionality

Whenever adding new user-facing features or workflows:
1. **Instrument Actions:** Call `trackAction("feature_action_name", { ...relevantParams })` on key user interactions (CTA clicks, submits, completes, toggles).
2. **SPA Routes:** If introducing a new route, `AnalyticsTracker` automatically tracks pageviews for both Contentsquare and GA4.
3. **Update Documentation:** Add the new event name and parameters to this `ANALYTICS.md` file.

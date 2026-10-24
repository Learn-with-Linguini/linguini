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
* `/practice/sessions/:sessionId/learn/vocabulary-preview` — Photo-level vocabulary introductory preview
* `/practice/ispy` — Standalone I-Spy mode selector (Solo vs Friends)
* `/practice/ispy/join` — Enter invite code to join a room
* `/practice/ispy/room/:roomCode` — Multiplayer I-Spy gameplay room
* `/ispy/challenge` — Daily photo challenge: take a photo of today's scene to start a lesson
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
| `guest_preview_started` | `{ source: "signin" | "signup" }` | Visitor opens the guest photo lesson without signing in |
| `login_submitted` | `{ method: "email" }` | User submits the email/password sign-in form |
| `signup_submitted` | `{ method: "email" }` | User submits new account registration |
| `google_signin_completed` | — | Google ID token is successfully exchanged for a Supabase session |
| `google_signin_failed` | — | Google Identity Services fails or Supabase rejects the Google ID token |
| `forgot_password_requested` | — | User submits email to request password reset link |
| `password_reset_completed` | — | User submits and sets a new password on `/reset-password` |
| `profile_password_changed` | — | Authenticated user changes password from Profile page |
| `logout_clicked` | — | User clicks "Log Out" in Profile |
| `account_deleted` | — | User confirms account deletion request |

### Onboarding & Setup
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `onboarding_completed` | `{ language, minutes, level }` | Learner completes initial onboarding questionnaire |
| `onboarding_resumed` | `{ stage }` | Learner returns to unfinished onboarding after leaving the app |

### Practice, Photo Lessons & Scene Analysis
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `practice_session_started` | `{ assetId }` | New photo lesson session initialized |
| `practice_session_resumed` | — | User resumes an existing incomplete practice session |
| `practice_photo_uploaded` | `{ assetId }` | User captures/uploads a personal camera roll photo |
| `photo_upload_retried` | `{ source: "camera" | "userUpload" }` | Learner retries confirmation of an uploaded image after a connection or server failure |
| `practice_scene_selected` | `{ sceneId, title }` | User selects a curated catalog scene |
| `scene_review_confirmed` | `{ acceptedCount, addedCount }` | User confirms detected objects before generating lesson |
| `scene_shortfall_shown` | `{ missing }` | Review shows that the photo lacks checkable objects, counts, adjectives or connections (`missing` is a comma-separated list) |
| `scene_shortfall_add_clicked` | `{ kind }` | Learner chooses to add the missing kind of fact from the shortfall notice |
| `scene_shortfall_new_photo` | `{ missing }` | Learner leaves a short scene to take or choose another photo |
| `scene_analysis_retried` | `{ sessionId }` | User requests AI re-analysis of a photo |
| `task_answer_checked` | `{ taskId, isCorrect, kind }` | Learner checks answer on an interactive exercise |
| `task_completed` | `{ taskId, kind }` | Learner completes reading or informational task |
| `task_opened` | `{ taskId }` | User opens a specific learning task from the task list |
| `learning_exit_clicked` | — | User exits the learning task overview back to Home |
| `finish_lesson_clicked` | — | User completes all learning tasks and clicks "Finish lesson" |
| `play_ispy_clicked` | — | User proceeds from learning tasks to play I-Spy |
| `vocabulary_preview_started` | — | User starts "Learn the words" vocabulary preview |
| `vocabulary_preview_continue_clicked` | `{ taskId }` | User continues from preview to individual word learning |
| `vocabulary_preview_exit_clicked` | — | User exits from vocabulary preview |
| `vocabulary_flashcard_viewed` | `{ taskId, position, termType, hasSceneObject }` | Learner views a vocabulary teaching card, including whether its object can be highlighted in the scene |
| `vocabulary_typing_checked` | `{ taskId, termType, isCorrect, revealed, basilEarned }` | Learner checks or reveals a typed vocabulary answer and receives any server-awarded Basil |
| `home_continue_practice_clicked` | — | User resumes incomplete practice from dashboard |
| `home_begin_practice_clicked` | — | User starts new practice from dashboard |
| `home_explore_vocabulary_clicked` | — | User clicks vocabulary revisit card on home dashboard |
| `home_explore_ispy_clicked` | — | User clicks I-Spy quick play card on home dashboard |
| `session_summary_viewed` | `{ basilEarned, wordsLearnedCount, completedLessonsCount }` | Session summary screen displays upon finishing a lesson |
| `summary_back_home_clicked` | — | User clicks "Back home" on session summary |
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
| `room_friend_invited` | — | User creates a friend invitation code/link |
| `room_friend_accepted` | — | User accepts a friend invitation code |
| `room_friend_removed` | — | User removes a friend from challenges |
| `room_action_executed` | `{ intent }` | Multiplayer game action dispatched (ready, turn, etc.) |
| `game_accent_selected` | `{ appearance }` | Learner equips or buys an accent using Sauce/Basil |

### Gamification & Leaderboards
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `chef_of_the_day_participation_toggled` | `{ participating }` | User opts in or out of the daily Chef of the Day leaderboard |
| `chef_of_the_day_retry_clicked` | — | User retries loading the daily leaderboard |
| `home_chef_standings_clicked` | — | Learner opens the daily Basil leaderboard from the Home standings card |
| `daily_challenge_start_clicked` | `{ sceneKey }` | User opens today's daily challenge from the Play tab |
| `daily_challenge_resumed` | `{ sceneKey }` | User continues an unfinished daily challenge session from the Play tab |
| `daily_challenge_photo_uploaded` | `{ sceneKey, assetId }` | User uploads or captures a photo for today's challenge |
| `daily_challenge_session_started` | `{ sceneKey, assetId }` | User starts a lesson session tagged as today's challenge entry |
| `daily_challenge_retry_clicked` | — | User retries loading the daily challenge |

### Vocabulary & Journal
| Event Name | Parameters | Trigger Description |
| :--- | :--- | :--- |
| `journal_entry_saved` | `{ hasPhotos, wordCount, isNew }` | Daily journal entry saved or updated |
| `vocabulary_view_toggled` | `{ view }` | Switched between journey tree and list views |
| `revisit_empty_practice_started` | — | Learner starts their first practice session from the empty Revisit page |
| `vocabulary_filters_applied` | `{ wordClass, category }` | Filter applied to vocabulary collection |
| `vocabulary_audio_played` | `{ word }` | Learner plays audio pronunciation for a target word |
| `vocabulary_recap_started` | `{ questionCount, wordCount }` | Learner starts a mixed review of a completed scene |
| `vocabulary_recap_answer_checked` | `{ kind, isCorrect, revealed? }` | Server returns a recognition or recall check during scene review |
| `vocabulary_recap_completed` | `{ questionCount, wordCount }` | Learner finishes the mixed scene review |

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
| `guest_demo_photo_selected` | `{ language }` | Visitor selects their own photo for a guest lesson |
| `guest_demo_photo_analyzed` | `{ language, objectCount }` | Guest photo analysis and translation completes |
| `guest_demo_photo_failed` | `{ language }` | Guest photo analysis or translation fails |
| `guest_demo_stage_viewed` | `{ stage, source: "upload" | "sample" }` | Guest lesson advances through review, translation, task, or completion |
| `guest_demo_completed` | `{ language, source: "upload" | "sample" }` | Visitor finishes the guest lesson task |
| `guest_demo_signup_clicked` | `{ language }` | Visitor chooses account creation after finishing the guest lesson |
| `pricing_cta_clicked` | `{ tier }` | User clicks plan call-to-action on the pricing page |

---

## 4. Requirement for New Functionality

Whenever adding new user-facing features or workflows:
1. **Instrument Actions:** Call `trackAction("feature_action_name", { ...relevantParams })` on key user interactions (CTA clicks, submits, completes, toggles).
2. **SPA Routes:** If introducing a new route, `AnalyticsTracker` automatically tracks pageviews for both Contentsquare and GA4.
3. **Update Documentation:** Add the new event name and parameters to this `ANALYTICS.md` file.

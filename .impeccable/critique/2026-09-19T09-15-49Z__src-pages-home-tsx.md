---
target: Linguini Home screen
total_score: 28
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
target_identity: "file:/Users/ananyajain/linguini/src/pages/Home.tsx"
target_fingerprint: "sha256:f9265f8fbdd41253addeaa283c23267ab33d195de4b0b16e296f063fb310d8f5"
target_path: /Users/ananyajain/linguini/src/pages/Home.tsx
timestamp: 2026-09-19T09-15-49Z
slug: src-pages-home-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|---|---:|---|
| 1 | Visibility of system status | 3/4 | The fresh-start state is clear, but it does not explain what happens after the photo is provided. |
| 2 | Match between system and real world | 4/4 | Capture, scene, vocabulary, and journal language are concrete and familiar. |
| 3 | User control and freedom | 3/4 | The main action is clear, but the user cannot see the choice of photo vs. ready scene before entering practice. |
| 4 | Consistency and standards | 4/4 | Shared visual language, button treatment, and labelled bottom navigation are cohesive. |
| 5 | Error prevention | 2/4 | The starting surface does not prepare users for unsuitable photos or show a no-photo route. |
| 6 | Recognition rather than recall | 4/4 | Camera visual, labels, and prominent Start learning action make the next step easy to recognise. |
| 7 | Flexibility and efficiency | 3/4 | Vocabulary and Progress shortcuts help returning users; no fast route to a preferred ready scene is visible. |
| 8 | Aesthetic and minimalist design | 3/4 | The page is calm and focused, although the secondary shortcuts compete slightly with the one dominant learning path. |
| 9 | Error recovery | 1/4 | No recovery expectation is visible on the Home screen if image analysis cannot help. |
| 10 | Help and documentation | 1/4 | The page offers no contextual explanation of the AI-assisted lesson flow. |
| **Total** | | **28/40** | **Solid visual foundation; the AI collaboration model is still hidden.** |

## Design Specificity Verdict

The Home screen feels authored for Linguini rather than interchangeable: the supplied wordmark, butter-paper surface, tomato and teal tactile actions, and camera-led learning prompt form a coherent brand. The current composition is a strong conventional mobile learning home, but it does not yet make Linguini's distinctive human–AI relationship visible.

The deterministic scan found no issues in `src/pages/Home.tsx`. That is useful but narrow: it validates that the targeted file does not trigger the detector; it does not evaluate the product's AI affordances, flow clarity, or the intentional overlap between Home shortcuts and persistent navigation.

## Overall Impression

The current Home screen is calmer and more usable than an overstuffed dashboard. Its biggest opportunity is to turn "Start learning" from a generic button into an honest preview of the learner-controlled AI flow: bring a photo or scene, review suggestions, then decide what to learn.

## What's Working

- The page has one obvious primary action. The large camera visual, short headline, and tomato CTA make a new learner's first move unmistakable.
- The visual system is unusually cohesive. The wordmark, warm palette, rounded cards, press-depth buttons, and Baloo/Nunito typography feel deliberately connected.
- The page avoids the common learning-app failure of showing every feature at once. Vocabulary and Progress remain available without overtaking the central action.

## Priority Issues

### [P1] The AI-assisted choice is invisible before the user commits

**Why it matters:** “Your photo becomes today’s lesson” suggests automatic conversion rather than the actual product promise: AI proposes vocabulary and the learner decides. This misses the core AI milestone opportunity and risks setting the wrong expectation.

**Fix:** Replace the supporting line with an expectation-setting cue such as “Choose a photo or scene. We’ll suggest a few useful words—you choose what to learn.” On the next screen, use an explicit review-and-confirm suggestion state rather than automatic progression.

**Suggested command:** `$impeccable clarify`

### [P1] The Home CTA hides a meaningful branch: personal photo versus ready scene

**Why it matters:** A learner who does not have a suitable photo may hesitate or abandon, even though ready scenes already exist. The secondary Practice navigation item is too indirect to communicate this choice.

**Fix:** Keep the dominant Start learning button, but add a compact caption below it: “Take a photo, upload one, or choose a ready scene.” The practice screen should preserve those three paths with equal clarity.

**Suggested command:** `$impeccable onboard`

### [P2] No visible recovery expectation for uncertain image results

**Why it matters:** Images can be blurry, dark, or too complex. Because image analysis is probabilistic, learners need to know they will not be blocked or forced to accept a bad result.

**Fix:** On the analysis and vocabulary-confirmation screens, add alternatives such as “Try another photo,” “Choose a ready scene,” and “Add a word yourself.” Avoid numerical confidence; use human language such as “This may be a backpack—does that look right?”

**Suggested command:** `$impeccable harden`

### [P2] Returning-user shortcuts dilute the learning hierarchy slightly

**Why it matters:** Vocabulary and Progress are useful, but the full-width teal buttons have a similar visual weight to the next learning path. On a small mobile screen, this may frame three actions as equally important.

**Fix:** Keep both shortcuts for now, but reduce their prominence with compact tile styling or a quieter "Your learning" section beneath the main card. Retain their accessible labels and hit areas.

**Suggested command:** `$impeccable layout`

## Persona Red Flags

**Jordan (first-time language learner):** The Start learning button is easy to find, but Jordan cannot predict whether they will be asked for camera access, can choose an existing picture, or can use a ready scene. The product's forgiving alternative routes are not visible at the moment confidence matters most.

**Maya (privacy-conscious learner):** “Your photo becomes today’s lesson” does not explain the human decision point after analysis. The likely concern is not a privacy notice; it is whether the app will decide what she should learn from a personal image. Showing an editable suggestion step resolves the immediate trust question.

**Alex (returning learner):** Vocabulary and Progress are efficient shortcuts, but there is no visible route to resume a preferred scene or review the last suggested word set from the fresh-start state.

## Minor Observations

- The camera visual has useful visual impact but is purely decorative; its adjacent supporting text must carry the complete next-step explanation.
- The persistent bottom navigation includes Practice while the Home surface has Start learning. That is acceptable, but the labels should remain semantically aligned as the flow evolves.
- The Home screen uses a broad desktop canvas with a narrow centered learning column. This preserves mobile focus, but tablet/web layouts could use a modest scene preview or recent-learning context without creating dashboard noise.

## Questions to Consider

- Is the main story you want a learner to understand before tapping: “Learn from your photo,” or “Choose the words AI suggests from your world”? The latter better demonstrates learner autonomy.
- Should ready scenes stay a quiet fallback, or become an equally visible route for learners who want to begin immediately?
- Would the lower shortcuts be more useful as compact progress summaries rather than full action buttons?

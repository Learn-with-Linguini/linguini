# Linguini — Design System

> **A curious language-learning companion, served in small real-world moments.**

## Product loop

Linguini is organized around one repeatable promise: **notice a real place, learn the
words inside it, play with those words, then use them in a journal.** The visual design
should make that loop feel like one friendly trail rather than four unrelated features.

1. **Capture:** upload a personal photo or choose a ready-made scene.
2. **Choose:** review useful objects and select what matters.
3. **Learn:** build confidence with pronunciation, meaning, examples, and phrases.
4. **Play I-Spy:** Linguini gives clues first; then the learner describes an object back.
5. **Reflect:** write a journal entry using the words discovered that day.

The primary route through the product becomes visible once active learning begins. Scene
selection and AI scene analysis stay unnumbered so the learner can focus on choosing and
correcting the source material before committing to the lesson. Review, vocabulary,
progress, and profile are supporting routes and should never compete with the next step.

## Product character

Linguini helps learners notice language in the world around them: capture a scene, choose what matters, play a quick visual game, and collect discoveries in a personal word journal. The experience should feel sunny, tactile, and reassuring—like a small illustrated field notebook with a mischievous noodle guide.

The visual system takes its cue from the provided product screens and mascot: cream paper, tomato-orange action moments, a deep herb-teal anchor, and soft pasta-yellow rewards. It is playful without being childish and warm without becoming rustic.

### Brand distinction

Keep the learning product legible and game-like, but avoid copying any competitor’s recognizable treatments. Linguini is defined by:

- **Noodle motion, not feathers:** a single looping strand can lead the eye, celebrate a correct answer, divide sections, or curl around an illustration.
- **Marker-and-menu outlines:** dark-teal hand-drawn-style contours with subtly imperfect geometry; never thick black cartoon outlines.
- **Food-memory warmth:** buttery surfaces, tomato CTAs, herb-teal confirmation, and pasta-yellow moments of discovery.
- **Real-world learning:** photographic scenes paired with illustrated overlays, vocabulary chips, and a journal-like record—not a fantasy-character world.
- **The wordmark is the welcome:** use the supplied orange-yellow “Linguini” wordmark with its looping underline as the visual anchor at the top of the first screen view. Center it in a distinct pasta-cream brand strip so its alignment feels intentional beside left-aligned page content. It scrolls away naturally with the page.

## Design principles

1. **Make the next learning action obvious.** One screen should have one dominant action.
2. **Treat progress as a friendly trail.** Show where a learner is, what they found, and what comes next.
3. **Use play as punctuation.** Noodles, spark marks, and the mascot add delight at transitions, success, and empty states—not behind every piece of information.
4. **Keep the scene credible.** Photos are real and useful; decorative illustration frames the interaction rather than obscuring it.
5. **Use tactile depth sparingly.** Actions should feel pressable; information panels should feel like soft paper layers.

## Color

The supplied palette is the starting point. These refinements preserve its intent while improving harmony and contrast.

| Token | Value | Use |
|---|---:|---|
| `--tomato` | `#E85D32` | Primary actions, active navigation, wordmark accents |
| `--tomato-pressed` | `#C94E2C` | Pressed/active primary action depth, destructive emphasis |
| `--pasta` | `#F9B233` | Rewards, discovery highlights, noodle details, progress fill |
| `--butter` | `#FFF9ED` | App canvas / main background |
| `--cream` | `#FFF1D2` | Cards, panels, soft notices |
| `--sage` | `#DCEBDD` | Learned-state fills and calm supporting surfaces |
| `--teal` | `#2E9C99` | Correct states, secondary actions, progress confirmation |
| `--teal-dark` | `#21716F` | Primary text on light surfaces, accessible teal labels |
| `--ink` | `#263238` | High-contrast text, icons, photo markers |
| `--ink-muted` | `#667579` | Supporting copy, inactive icons |
| `--line` | `#D9D2C3` | Quiet boundaries, dashed capture areas, dividers |
| `--danger` | `#C94E2C` | Errors only; pair with a written explanation |
| `--focus` | `#166C84` | Keyboard focus ring; do not rely only on color |

### Color rules

- Butter is the default page background; cream is the default elevated surface.
- Tomato is reserved for the most important action on a screen. Do not use it as general decoration.
- Teal means confidence, confirmation, or an alternate positive route; it should not compete with tomato in the same action group.
- Pasta yellow is a highlight, not a body-text color. Use dark teal or ink for text on yellow.
- Use the full-color wordmark on butter/cream. Use a one-color tomato or cream version only where contrast requires it.

## Typography

Choose licensed fonts with rounded, human shapes rather than a branded competitor typeface.

| Role | Recommended family | Weight | Desktop / mobile | Notes |
|---|---|---:|---:|---|
| Headings | **Baloo 2** | 700–800 | 52–64 / 32–40 | Warm, rounded headings that support the custom wordmark without copying it |
| UI & body | **Nunito Sans** | 400–800 | 16 / 16 | Clear at small sizes; use 700–800 for controls |
| Numbers / metadata | **Nunito Sans** | 700–800 | 12–16 / 12–16 | Use tabular numerals where progress is compared |

Use sentence case throughout. The supplied wordmark is the only expressive display lettering; use Baloo 2 at 700–800 for headings and keep Nunito Sans body text calm and conversational. Avoid all-caps except tiny status labels if needed.

### Type scale

| Token | Size / line-height | Typical use |
|---|---|---|
| `--text-display` | `clamp(32px, 5vw, 64px) / 1.02` | Marketing or major moments |
| `--text-h1` | `32px / 1.12` | Page titles |
| `--text-h2` | `24px / 1.18` | Screen sections |
| `--text-h3` | `20px / 1.25` | Cards and prompts |
| `--text-body` | `16px / 1.45` | Default reading text |
| `--text-small` | `14px / 1.4` | Supporting descriptions |
| `--text-label` | `12px / 1.2` | Tabs, status, compact metadata |

## Spacing, shape, and depth

**Base unit:** 4px. Use a comfortable, mobile-first rhythm.

| Token | Value |
|---|---:|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-10` | 40px |
| `--space-12` | 48px |

| Token | Value | Use |
|---|---:|---|
| `--radius-sm` | 12px | Chips, fields, compact controls |
| `--radius-md` | 18px | Buttons, cards, image frames |
| `--radius-lg` | 28px | Major panels, sheets |
| `--radius-pill` | 999px | Tabs and status pills only |
| `--stroke` | 2px | Standard dark-teal outline |
| `--shadow-card` | `0 6px 14px rgba(38, 50, 56, .10)` | Soft paper lift |
| `--shadow-action` | `0 4px 0 #C94E2C` | Primary button press depth |

Use rounded rectangles with a little personality: illustrations and large panels may have asymmetrical or hand-sketched edges, but form controls must retain stable geometry for usability. Do not use glass effects, neon glows, or large blurred shadows.

## Iconography and the noodle system

Icons use a 2px rounded stroke, generally in `--teal-dark` or `--ink-muted`. Pair an unfamiliar icon with a text label. Keep icon containers soft and simple.

The Linguini noodle is a branded path, not a generic squiggle. Its rules:

- Draw it as a warm pasta-yellow tube with tomato-orange outer contour and a small cream inner highlight when it is large enough.
- Keep a consistent stroke rhythm; wide turns and loops should feel elastic, never tangled.
- Use one noodle gesture per composition: a loop around a reward, a divider under a message, or a trail leading to the main action.
- Do not let it cross body copy, controls, faces, or essential photo details.
- Animate only on purposeful moments: a 180–300ms curl on completion, a gentle 1.5–2s idle sway for the mascot, and reduced-motion alternatives with no path movement.

### Mascot

The Linguini mascot is a smiling pasta strand on a plate. It should appear as a supportive guide, not as a constant narrator:

- **Welcome / onboarding:** full mascot, warm and inviting.
- **Success:** small celebratory curl or confetti-like sauce dots.
- **Empty journal:** mascot looking through a tiny frame or holding a word card.
- **Errors:** never use a sad or shaming expression; give a neutral, helpful prompt instead.

## Core components

### Primary button

Tomato fill with cream or white label, 18px radius, 48px minimum height, and a 4px darker tomato bottom edge. Use a 700–800 UI label at 16px. On press, translate `2px` down and reduce the bottom edge to `2px`. Include an icon only when it clarifies the action (camera, play, arrow).

### Secondary button

Teal fill with a cream or white label, 18px radius, 48px minimum height, and a 4px dark-teal bottom edge. Use when an action is meaningful but not the screen’s main route. Avoid placing more than one secondary button beside a primary action on small screens.

### Quiet button / icon button

No filled container by default; use teal-dark text or icon with a minimum 44 × 44px hit area. Add a cream hover/pressed surface, not a new border.

### Button consistency rules

- Use **primary** for the one forward-moving action: tomato fill, tomato border, white label, and the same 4px tomato press edge everywhere.
- Use **secondary** for a meaningful alternative: teal fill, white label, teal border, and the same 4px press edge as primary buttons.
- Use **quiet** only for supporting actions such as “Show English”, “Back home”, and close controls. It has no outline or shadow.
- Do not create a new button treatment inside a page. Answer choices, vocabulary chips, scene tiles, and task rows are selectable learning controls, not action buttons, so their selected/correct/incorrect states are the only deliberate exceptions.

### Vocabulary chip

Rounded, tactile selection pill with an illustrated number marker or object icon. Default: cream fill, 1px line border, ink text. Selected: pasta-tint fill with tomato or teal number disc. Chips wrap cleanly; never truncate the word itself.

### Photo scene card

18px rounded photo, 2px teal-dark contour, clipped image, and numbered markers that remain legible over the image. Keep marker labels outside the photo where possible. Provide descriptive alt text and a non-photo route for users who prefer to enter a word manually.

### Progress trail

Use a cream track with a pasta-yellow fill, paired with textual progress such as “1 of 3.” A tiny noodle curl may cap the fill on celebratory screens, but must not replace the numeric status.

### Answer choice

Large 48px-minimum selectable tile on cream. Default state uses a quiet line border; selected state uses teal border plus a pale teal surface; correct uses teal with a check icon; incorrect uses tomato with explanatory text. Never reveal correctness by color alone.

### Journal row

An illustrated thumbnail, a strong target-language word, a smaller translation, and a progress state badge. Use a calm 8–12px vertical gap between rows and clear divider lines rather than a grid of detached cards.

### Toast and feedback panel

Use a cream panel with a color-coded left detail and a concise human message: “Nice catch—*árbol* means tree.” Include a next action only if it moves the learner forward.

## Key screens

### Welcome

Introduce Linguini through one spacious three-step carousel rather than a dense feature list. The steps are Find, Learn, and Use: Find shows a real scene photo with numbered AI-suggested objects and learner-approved word chips; Learn shows a compact I-Spy clue and choices; Use shows two real photos arranged as a journal memory beside a short entry. Keep the current step's title and explanation above one large demonstration card, with previous/next chevrons and three progress dots below. The full Linguini wordmark remains in the shared brand strip. Keep one persistent tomato Get started action beneath the carousel and a quiet existing-account route below it. The page must communicate the complete image-to-practice-to-journal loop without requiring a scroll through separate marketing sections.

### Capture a scene

The home screen answers one question only: “What should I do next?” Begin with a compact mascot welcome using the learner's name and one short encouraging sentence, followed by a quiet seven-day check-in panel. Use the supplied transparent farfalle image—not generic circles or a redrawn bow—for checked-in days; leave missed or future days muted. Below it, show one dominant featured card. For a new learner, use a single tomato “Begin a new practice” action. If practice is underway, let its real scene image lead the card, followed by a compact task trail and one tomato “Continue learning” action; “Start a new practice” becomes a smaller supporting row. Show only three recent words beneath the plan on soft pasta-cream chips, with a quiet route to the full vocabulary library. Keep one gentle journal-entry action directly beneath the words so reflection is always findable without competing with practice. Do not add profile details, full statistics, scene collections, or multiple equally prominent actions to Home.

The scene-selection page is not a staged task and must not show a progress trail. Choosing, capturing, or uploading an image opens analysis immediately. Scene analysis is also unnumbered: use the title “Scene Analysis,” never “Step 2” or a progress bar. Begin staged progress only when the learner moves from their confirmed word list into active learning tasks.

### Scene analysis

Treat AI detection as a suggestion the learner reviews, not a completed decision. Start with a brief image-scanning state that says “Finding objects in your image…” without a card or progress bar. Then show the real photo with numbered markers, followed by a plain-text result count such as “2 words found.” Place the detected English words in one calm card below the count. Every suggestion must have a visible remove action, and the same card must let the learner add a word the analysis missed. Adding a word is a two-part action: the learner names it, then taps its location in the photo before it joins the list. User-added words receive their own orange numbered marker so the photo and list stay directly mapped. Continuing is disabled when no words remain or a new word is still awaiting placement.

### Choose vocabulary

Place the captured photo at the center of the screen. Numbered markers map directly to selectable vocabulary chips underneath. Use tomato for the current selection and pasta / teal for supporting markers, maintaining high-contrast text. The primary action reads “Start I Spy” and remains fixed above the bottom navigation when the chip list scrolls.

### Test your mic

Keep microphone setup short and visually quiet. Use the unnumbered title “Test your mic” with no progress trail. Group the phrase, translation, microphone, and test status in one calm paper panel. “Use typing instead” is an outlined supporting action rather than a competing filled button. Only the forward-moving Continue action uses the filled tomato treatment.

### Learning tasks

The learning-task list is a launch page, not part of the task sequence itself. Do not show a phase label or progress trail there. Show the scene, a calm list of available tasks, and one filled action to begin the first task or continue the next incomplete one. Every task row may also open its task directly.

Each learning task has its own full page rather than opening in a bottom sheet. Put task progress at the top as “Task n of total,” followed by a title row with a compact “× Exit” control that returns home. Repeat this title-row exit on the task-list page so the learner can leave active practice at any time. Follow the title with guidance and one focused word card at a time. Give the card a warm pasta-yellow surface, set the target vocabulary in dark teal, and place the audio action in a generous white circular control so pronunciation remains easy to find. Use a small text counter for progress within the task so two progress bars never compete. Keep the underlined “Back to tasks” link beneath the filled orange action on individual tasks. Completing a task advances to the next task; the final task returns to the completed list, where I-Spy becomes the primary action.

### Play I Spy

Make the challenge feel focused: progress at top, scene photo next, a compact hint card, then 2 × 2 large answer choices. The correct-feedback state should turn the action teal and animate a brief noodle curl around the selected answer. Maintain generous white space around tap targets.

### Word journal

Treat the journal as proof of progress, not a dense database. Put a soft pasta-yellow encouragement panel above or below the list. Segment Review, Learned, and Mastered with text-first tabs. The active tab uses tomato fill; inactive tabs live on a pale cream rail. Each row should feel easy to revisit in under a second.

### Vocabulary library

Vocabulary replaces Progress as a primary navigation destination. Open with a scene-first library: each real scene image introduces the words collected from that place, with target words, translations, and pronunciation controls grouped directly beneath it. A prominent teal book action at the top switches to the complete vocabulary list. Present that full list as calm paper cards, matching the journal’s card language rather than a divided utility list. Give the target-language word clear teal emphasis on the left, align its translation to the right, and keep the example, word type, and topic together below. Use soft teal-green pills for word type and topic so they remain distinct from pasta-yellow actions and surfaces. Anchor pronunciation in a circular control at the card’s bottom-right corner. Open vocabulary filters in a bottom sheet rather than expanding the page; changes stay temporary until the learner selects the filled “Apply filters” action, while close, backdrop, or Escape dismisses the sheet without applying them.

### Session summary

Make the completion state feel celebratory without becoming noisy. Center the noodle flourish beneath the congratulatory heading. Present the three session statistics with strong dark labels, large teal values, and a light sage-green surface so the results remain legible at a glance.

### Profile

Lead with a paper profile card containing a large pasta avatar inside a clean white circular frame, followed by the learner's name and joining month. A right chevron opens a dedicated Edit profile page; never expose editing controls or a separate Edit profile button on the main profile. The editing page owns the learner's name, pasta avatar, language, daily goal, practice preference, and permissions, and returns through the standard header back control. Show the maximum streak in its own compact cream card. Show only this week's quick progress beneath the identity area, then present the saved learning setup and permissions as readable values. End with a concise explanation that AI suggests scene vocabulary and prompts while the learner reviews and controls every decision, followed by a full-width tomato Log out action. Flags may identify languages, but do not use emoji as decoration elsewhere on this page.

The journal list is a single-month view. Use a centered month-and-year label (for example, “September 2026”) with standard previous and next month chevrons on either side. Filter entries to the chosen month and keep the chevrons active when that month is empty. A journal entry can collect multiple ready-scene or uploaded photos; display them as a single-photo carousel with previous/next chevrons and a clear position label.

## Navigation and layout

### Mobile

- Design for 360px wide screens first; allow content padding of 16px, expanding to 20–24px on larger phones.
- Use a persistent five-item bottom bar: Home, Practice, Vocabulary, Journal, Profile. Vocabulary uses an open-book icon and occupies the center position; Journal uses a distinct notebook-and-pencil icon. Each item has an icon and label; the active icon is filled tomato and its label is tomato.
- Keep bottom navigation on the same butter surface as the page, separated only by a quiet line and safe-area padding. It should recede behind the learning content rather than create a new color band.
- Primary actions belong above the navigation and must not be hidden behind it.
- Use full-width action buttons, except compact paired controls that still preserve 44px hit targets.
- Put the single back control beside the centered wordmark in the shared header. Do not add a second back arrow inside a screen title bar. Root destinations (Home, Practice, Journal, Vocabulary, Profile, and Welcome) remain wordmark-only.

### Current implementation guidance

- Use the shared simplified mascot assets (`public/linguini-logo.svg` for happy and `public/linguini-logo-sad.svg` for sad) rather than redrawing the mark in individual pages. Use the `Mascot` component's `expression` prop when a screen needs to acknowledge a setback.
- Keep `BrandBar`, `Button`, `Card`, `ScenePhoto`, `Tabs`, and `ProgressTrail` as the shared source of truth for page styling.
- The page background is warm butter with a subtle pasta-yellow lift near the header. The shared wordmark sits on a richer pasta-cream strip (`#F7E6B4`) without a divider; elevated surfaces are paper/cream, never stark white or glassy.
- Tomato is reserved for the one dominant action and active navigation. Teal is the confidence/confirmation color. Pasta yellow is reserved for progress, rewards, and the wordmark.
- Prefer one large scene or learning panel per screen. Journal and vocabulary collections use calm paper cards with consistent spacing and restrained elevation.
- On the mobile canvas, target 360px first: 16px side padding, 48px controls, 44px icon hit areas, and safe-area space below fixed navigation.

### Tablet and web

- Keep content in a centered column of 680–760px for learning flows; use 1120px maximum for marketing or photo-plus-detail layouts.
- At 768px and above, switch the bottom navigation to a left rail or simple top navigation only if the learning flow benefits from more vertical room.
- Retain the large touch targets and visual hierarchy from mobile; do not turn the journal into a cramped desktop table.

## States and accessibility

- Body text must meet WCAG AA contrast; do not use pasta yellow or muted ink for primary body copy.
- Every control has visible focus: a 3px `--focus` outline with a 3px cream offset.
- Respect `prefers-reduced-motion`; replace noodle movement with a static final state.
- Never make a photo the only source of meaning. Provide labels for scene markers and an alternative vocabulary input path.
- Include text and icons for correct, incorrect, learned, and mastered states.
- Use 44 × 44px minimum touch targets and 48px minimum height for primary, secondary, and answer controls.
- Write feedback as encouragement and instruction: “Almost—look for the bus near the curb,” never “Wrong.”

## Motion

| Moment | Motion | Duration |
|---|---|---:|
| Button press | Down 2px; action edge compresses | 100ms |
| Selection | Border/fill settle with a small scale to 1.01 | 160ms |
| Correct answer | Noodle curl + check appears | 240ms |
| Panel entry | Fade and rise 8px | 180ms |
| Mascot idle | Very subtle 2–3px sway | 1800ms loop |

Use ease-out motion. Avoid bouncing entire layouts, looping attention-grabbers, or animation that delays the next answer.

## Copy voice

Warm, direct, and observant. Use short sentences, active verbs, and concrete cues from the learner’s world.

- Good: “What do you spot on this street?”
- Good: “Save *autobús* to your journal.”
- Good: “A few minutes of review goes a long way.”
- Avoid: “You have failed this exercise.”
- Avoid: “Complete module 1 to unlock linguistic mastery.”

## Implementation starter tokens

```css
:root {
  --tomato: #E85D32;
  --tomato-pressed: #C94E2C;
  --pasta: #F9B233;
  --butter: #FFF9ED;
  --cream: #FFF1D2;
  --sage: #DCEBDD;
  --teal: #2E9C99;
  --teal-dark: #21716F;
  --ink: #263238;
  --ink-muted: #667579;
  --line: #D9D2C3;
  --focus: #166C84;

  --font-display: "Baloo 2", ui-rounded, sans-serif;
  --font-ui: "Nunito Sans", ui-sans-serif, system-ui, sans-serif;

  --radius-sm: 12px;
  --radius-md: 18px;
  --radius-lg: 28px;
  --shadow-card: 0 6px 14px rgba(38, 50, 56, 0.10);
  --shadow-action: 0 4px 0 var(--tomato-pressed);
}
```

## Guardrails

- Do not use a green-led palette, owl imagery, feather motifs, or a copied game layout from another language-learning product.
- Do not make every card float; reserve lifted panels for capture, feedback, and key journal moments.
- Do not use the mascot as a replacement for clear instructions.
- Do not overuse the noodle. It is a signature flourish, not a pattern fill.
- Do not use more than one saturated action color as “primary” on the same screen.
- Do not sacrifice readability for hand-drawn styling: text, touch areas, focus states, and photo markers remain crisp and predictable.

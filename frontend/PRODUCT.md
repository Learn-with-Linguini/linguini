# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Linguini is for language learners of any age. Its primary audience is young adults and college-age learners who want to build practical vocabulary from places and objects in their everyday lives.

## Product Purpose

Linguini is a photo-led, speak-first language-learning app. It helps a learner capture or choose a real-world scene, identify useful vocabulary within it, practise that vocabulary through learning and I-Spy activities, and use it in a personal journal.

Success means learners can recognise, describe, and use words connected to their own surroundings—not merely memorise isolated translations.

## Positioning

Linguini turns the learner's own visual world into the source material for a complete language-practice loop. Rather than giving a generic word list, it starts with a scene the learner chose and carries their confirmed vocabulary through practice and reflection.

## Operating Context

Learners can upload a personal photo or select a ready-made scene. The current learning loop is:

1. Choose or capture a scene.
2. Review vocabulary suggested for that scene.
3. Learn and practise those words, including two-direction I-Spy activities.
4. Record a journal entry using the day's words and one or more photos.

English is the base/interface language. The initial target languages are French, Spanish, and Italian.

## Capabilities and Constraints

- AI may analyse a scene and suggest vocabulary, examples, or practice material.
- The learner has the final say over every AI-supported decision. AI suggestions must be reviewable, editable, removable, and never silently accepted as the learner's chosen vocabulary or journal content.
- The current repository is a frontend prototype with mock data and in-memory state. It has no backend persistence, authentication, or live LLM integration yet.
- User-uploaded images currently exist only for the browser session; future storage, retention, and consent decisions remain open.

## Brand Commitments

Linguini is warm, curious, playful, and grounded in real places. The pasta theme is an implicit part of the product identity: the supplied Linguini wordmark and mascot remain core assets, and user avatars may be different pasta shapes such as penne and fusilli.

The product should communicate learner autonomy through its interface. It should present AI as a helpful collaborator, not an authority or replacement for the learner's judgment.

## Evidence on Hand

- Existing prototype and route-level flows in `src/`.
- Current visual system and product flow in `design.md`.
- Supplied Linguini wordmark and mascot assets in `public/`.
- Six ready-made scenes: Street, Classroom, Grocery store, Bedroom, Office, and Airport.
- Mock vocabulary, progress, journal, and session data in `src/data/mock.ts`.

There is no live user research, production analytics, backend, or functioning AI provider in this checkout. Future product claims must not imply that those systems already exist.

## Product Principles

1. Start with the learner's world: scenes and words should feel immediately useful in daily life.
2. Keep the learner in charge: AI proposes, explains, and adapts; the learner confirms and decides.
3. Practise in context: carry learner-confirmed words from image to recognition, description, and writing.
4. Make progress feel encouraging: short, playful practice should build confidence without judgment.
5. Make the product understandable: show what a suggestion affects and provide a clear way to change it.

## Accessibility & Inclusion

Linguini serves learners across ages and language experience. Maintain readable interface language, clear non-colour feedback, keyboard focus, touch-friendly controls, reduced-motion support, and an alternative to photo-only or speech-only input.

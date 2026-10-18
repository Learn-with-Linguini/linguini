# Shared multilingual M01 contracts

This document describes the shared A0/A1/A2 multilingual M01 path. Generation requires
`MULTILINGUAL_ENABLED=true` and an enabled language/level pair in
`MULTILINGUAL_COMBINATIONS`; both default to off. The legacy builders remain
available for existing language/level combinations.

Set combinations explicitly in the backend environment. For example:

```sh
MULTILINGUAL_ENABLED=true
MULTILINGUAL_COMBINATIONS="es:A1,fr:A0,de:A2"
```

`es:*` enables all M01 levels for Spanish, while a bare `*` enables every registered
language and M01 level. A combination is written `code:LEVEL`; code matching ignores
case. An unset or empty combinations value enables none, even when the global flag is
on. Malformed entries are ignored with a warning.

## Language registry

`backend/app/languages/registry.toml` is the central source for language names, script,
direction, word separation, picker availability, instruction-language eligibility,
browser speech locale, and optional linguistic metadata. Direction is derived from the
ISO 15924 script; it is not stored in the registry. The public `GET /api/v1/languages`
response also derives legacy mission levels and reports browser-voice synthesis with
recognition disabled. These fields describe current implementation and do not advertise
unimplemented support.

To register a language, add one `[[languages]]` entry with a canonical BCP 47 code, ISO
15924 script, and speech synthesis locale. `grammar` is optional metadata. Article
validation requires an article only when `grammar.articles = true`; otherwise normalized
objects have no article while their gender metadata is preserved. Optional reviewed
examples can be added to the mission definition's `language_patterns.examples` table.
A registered target can use the feature-flagged M01 path without adding a legacy
builder or language allowlist entry.

Speech synthesis uses browser voices only. The app selects a voice from the registry's
`speech.synthesisLocale` (falling back to the language code) and does not provide speech
recognition. If the device has no matching voice, audio controls are omitted and the
lesson displays: “Audio isn't available for <language> on this device. You can complete
this lesson without it.”

Registry registration alone does not expose a language in pickers: only after review
should `learnable = true` be set so it appears in target pickers.

## M01 contract input

| Field | Meaning |
| --- | --- |
| `contractVersion` | `m01-multilingual.v1` |
| `mission` | M01 mission id, practice level, and content version resolved by `get_mission` |
| `targetLanguage` / `instructionLanguage` | Registered, different languages; the instruction language must be enabled for instruction |
| `sceneFacts` | Learner-confirmed objects, attributes, relations, and counted groups |
| `vocabulary` | Approved target terms explicitly tied to confirmed scene facts |
| `reviewedExamples` | Optional examples from the mission definition or a reviewed override |
| `learner` | Matching proficiency, familiarity, recent missions, and whether plural forms have been taught |

Every scene fact has a unique `factId`. All attribute, relation, count, and vocabulary
references must resolve to confirmed facts. Object references resolve to object fact IDs,
and a relation cannot point an object to itself.

Stable fact ID helpers produce:

| Fact | Identifier |
| --- | --- |
| Object | `object:<scene-object-uuid>` |
| Attribute | `attribute:<scene-object-uuid>:<key>` |
| Relation | `relation:<subject>:<relation-type>:<reference>` |
| Count group | `count:<label>` |

Approved terms may carry optional, extensible `linguistic` metadata such as `gender`,
`number`, `article`, `plural`, `classifier`, `elides`, `batchim`, or `honorific`.
Metadata keys are contract identifiers and values may be strings, booleans, integers, or
lists of strings. No language requires any such value.

## M01 contract output

| Field | Meaning |
| --- | --- |
| `contractVersion`, `mission`, language codes | Version and routing context matching the input |
| `objectiveId`, `title`, `explanation` | Definition objective and learner-facing lesson framing |
| `preparation` | Target-language cards, optional instruction translations, evidence facts, and audio availability |
| `questions` | Target IDs, prompts, interaction type, choices/markers or sentence chunks, and feedback |
| `private` | Correct choice/chunk answers and `QuestionEvaluation` records; excluded by `public_dump()` |

`SentenceChunk.join` describes how a chunk attaches to the previous chunk. The first
chunk's join value is ignored. `join_chunks()` inserts a space for `space` and nothing
for `none`. `default_join()` suppresses spaces before punctuation and for languages whose
registry uses `word_separator = "none"`. Builders must handle elision explicitly; it is
not inferred from text.

The output validator checks the exact ordered question slots, their targets,
interactions, focus objects and option/distractor counts, preparation-card counts,
required target coverage, confirmed fact kinds and references, option labels, marker
mappings, answer grounding, chunk bounds, explanation-answer leakage, and A2
connection/follow-up ordering. Per-object preparation cards must teach every assessed
object; levels without per-object preparation have no cards. Attribute and relation
strings are not text-grounded because natural inflection can change their surface
form. Structural validation does not establish that a translation is linguistically
correct: there is no linguistic evaluator in this stage.

## Level-plan slots

Each level's `questions` list is exact and ordered. `focus` is a one-based object
index: slots sharing an index assess the same object, and different indices use
different objects. Choice counts are shown as `options min–max`; sentence-building
counts are `distractor_chunks min–max`. Every slot also fixes its target IDs,
interaction, evidence and rubric criteria.

| Level | Focus objects | Preparation | Required objects | Detail facts | Questions | Max answer chunks |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| A0 | 2 | One per object + 2 extra cards | 2 | 0 | 6 | 6 |
| A1 | 2 | 0 cards | 2 | 1 | 4 | 8 |
| A2 | 1 | 0 cards | 3 | 2 | 5 | 12 |

A1 eligibility requires an approved colour fact for each of its two focus objects;
a relation-only detail cannot supply the colour questions.

### A0

| # | Purpose | Focus | Target IDs | Interaction | Count | Evidence | Criteria |
| ---: | --- | ---: | --- | --- | --- | --- | --- |
| 1 | `matchName` | 1 | `recognise-name` | `markerChoice` | options 2–3 | `recognition` | `name-matches-object` |
| 2 | `confirmName` | 1 | `identify-object` | `multipleChoice` | options 2 | `recognition` | `identifies-object` |
| 3 | `buildIdentify` | 1 | `identify-object` | `sentenceBuilding` | distractors 1 | `construction` | `identifies-object` |
| 4 | `matchName` | 2 | `recognise-name` | `markerChoice` | options 2–3 | `recognition` | `name-matches-object` |
| 5 | `confirmName` | 2 | `identify-object` | `multipleChoice` | options 2 | `recognition` | `identifies-object` |
| 6 | `buildIdentify` | 2 | `identify-object` | `sentenceBuilding` | distractors 1 | `construction` | `identifies-object` |

### A1

| # | Purpose | Focus | Target IDs | Interaction | Count | Evidence | Criteria |
| ---: | --- | ---: | --- | --- | --- | --- | --- |
| 1 | `confirmObject` | 1 | `identify-object`, `name-object` | `multipleChoice` | options 2 | `recognition` | `selects-described-object`, `article-matches-noun` |
| 2 | `confirmObject` | 2 | `identify-object`, `name-object` | `multipleChoice` | options 2 | `recognition` | `selects-described-object`, `article-matches-noun` |
| 3 | `chooseAttribute` | 1 | `describe-colour` | `multipleChoice` | options 2–3 | `recognition` | `colour-matches-photo` |
| 4 | `describeObject` | 2 | `name-object`, `describe-colour` | `sentenceBuilding` | distractors 0–1 | `construction` | `article-matches-noun`, `colour-matches-photo` |

### A2

| # | Purpose | Focus | Target IDs | Interaction | Count | Evidence | Criteria |
| ---: | --- | ---: | --- | --- | --- | --- | --- |
| 1 | `chooseSceneMarker` | 1 | `identify-scene-object` | `markerChoice` | options 2 | `objectSelection` | `scene-object-matches-fact` |
| 2 | `buildSceneFact` | 1 | `describe-scene-facts` | `sentenceBuilding` | distractors 1 | `construction` | `scene-sentence-matches-facts` |
| 3 | `chooseSceneDescription` | 1 | `describe-scene-facts` | `multipleChoice` | options 3 | `recognition` | `scene-sentence-matches-facts` |
| 4 | `buildSceneDescription` | 1 | `connect-scene-facts` | `sentenceBuilding` | distractors 1 | `construction` | `scene-facts-connected` |
| 5 | `followUpSceneFact` | 1 | `follow-up-scene-fact` | `multipleChoice` | options 2–3 | `recognition` | `scene-follow-up-matches` |

## Routing and compatibility

`M01_VARIANTS` explicitly routes M01 A0/A1/A2 version 1. Missing mission, level, or
version combinations raise `UnroutedMissionVariant`; there is no level fallback. With
the flag enabled, initial mission planning uses confirmed object/detail facts and the
level plan, before translation. After translation, the workflow requires the minimum
number of approved session-translation terms; if that check fails it skips M01 with
`insufficientApprovedVocabulary` without generating or falling back to legacy content.

If generation fails, a ready legacy lesson is used only when the requested language is
in that level's legacy allowlist. Otherwise M01 is skipped with reason
`generationFailed`; the skip is non-retryable and does not complete the mission. The
workflow never generates using a different target language. The flag-off path and
other mission allowlists are unchanged. No database migration is needed.

## Manual test procedure

1. Start the app against a disposable local PostgreSQL database and use the normal
   authenticated demo account and a language profile whose target is registered.
2. Set `MULTILINGUAL_ENABLED=true` in the backend environment, restart the backend,
   and open the normal photo-led learning flow from a scene with reviewed objects,
   details, and translated vocabulary.
3. Confirm M01 appears only when the level's confirmed-fact counts and post-translation
   approved-vocabulary counts meet the plan. Check preparation cards, sentence chunks,
   language direction, and target-language rendering.
4. To exercise a generation failure, use a controlled test client rather than
   deliberately corrupting stored session data. Confirm an allowlisted, ready legacy
   lesson can be used, and that other languages receive a non-retryable
   `generationFailed` skip. A failed approved-vocabulary check must not call generation
   or use the legacy fallback.
5. Turn the flag off and confirm the existing M01 lessons and other mission behavior
   remain on their legacy paths.

## Adding and evaluating another language

1. Add a registry entry only. The shared builder, validator, and frontend should not
   need language-specific edits. Add optional reviewed examples to the mission
   definition when useful.
2. Run the mocked fixed-scene matrix and structural validation tests. These check
   contract shape, grounding, and rendering behavior; they are not linguistic
   verification.
3. Run a bounded live smoke with `AI_MODE=real` for each M01 level using the manual
   procedure above. Record the environment, language/level, session, task, and outcome.
4. Have a native speaker review generated lessons and corrections.
5. Add only reviewed language/level pairs to `MULTILINGUAL_COMBINATIONS`.
6. Set `learnable = true` only after those reviews are complete.

Structural validation and mocked tests alone do not establish linguistic quality.

## Evaluation matrix

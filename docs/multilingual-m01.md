# Shared multilingual M01 contracts

This document describes the shared A0/A1/A2 multilingual M01 path. Its generation path
is gated by `MULTILINGUAL_M01_ENABLED` and defaults off; the legacy builders remain
available for existing language/level combinations.

## Language registry

`backend/app/languages/registry.toml` is the central source for language names, script,
direction, word separation, picker availability, instruction-language eligibility,
browser speech locale, and optional linguistic metadata. Direction is derived from the
ISO 15924 script; it is not stored in the registry. The public `GET /api/v1/languages`
response also derives legacy mission levels and reports browser-voice synthesis with
recognition disabled. These fields describe current implementation and do not advertise
unimplemented support.

To register a language, add one `[[languages]]` entry with a canonical BCP 47 code,
ISO 15924 script, and speech synthesis locale. `grammar` is optional free-form metadata;
no contract requires grammatical features. Optional reviewed examples can be added to
the mission definition's `language_patterns.examples` table. A registered target can
use the feature-flagged M01 path without adding a legacy builder or language allowlist
entry. Registry registration alone does not expose it in pickers: only then set
`learnable = true` for a new language so it appears in target pickers.

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
| `workedExamples` | Joined sentence chunks, instruction translation, evidence facts, and optional note |
| `questions` | Target IDs, prompts, interaction type, choices/markers or sentence chunks, hints, and feedback |
| `private` | Correct choice/chunk answers and `QuestionEvaluation` records; excluded by `public_dump()` |

`SentenceChunk.join` describes how a chunk attaches to the previous chunk. The first
chunk's join value is ignored. `join_chunks()` inserts a space for `space` and nothing
for `none`. `default_join()` suppresses spaces before punctuation and for languages whose
registry uses `word_separator = "none"`. Builders must handle elision explicitly; it is
not inferred from text.

The output validator checks plan question/preparation/example bounds, allowed
interactions, required target coverage, confirmed fact kinds and references, option
labels, marker mappings, answer grounding, chunk bounds, progressive hints,
teach-before-assess examples, example/answer distinctness, and A2 connection/follow-up
ordering. Attribute and relation strings are not text-grounded because natural
inflection can change their surface form. Structural validation does not establish
that a translation is linguistically correct: there is no linguistic evaluator in
this stage.

## Routing and compatibility

`M01_VARIANTS` explicitly routes M01 A0/A1/A2 version 1. Missing mission, level, or
version combinations raise `UnroutedMissionVariant`; there is no level fallback. With
the flag enabled, initial mission planning uses confirmed object/detail facts and the
level plan, before translation. After translation, the workflow requires the minimum
number of approved session-translation terms; if that check fails it skips M01 with
`insufficientApprovedVocabulary` without generating or falling back to legacy content.

If generation fails, a ready legacy lesson is used only when the requested language is
in that level's legacy allowlist. Otherwise M01 is skipped as a retryable
`generationFailed` mission; a learner can use **Try again** from the learning page.
The flag-off path and other mission allowlists are unchanged. Grammar lessons store
their saved checks, disclosed hint levels, and retry claim in existing JSON columns;
no database migration is needed.

## Manual test procedure

1. Start the app against a disposable local PostgreSQL database and use the normal
   authenticated demo account and a language profile whose target is registered.
2. Set `MULTILINGUAL_M01_ENABLED=true` in the backend environment, restart the backend,
   and open the normal photo-led learning flow from a scene with reviewed objects,
   details, and translated vocabulary.
3. Confirm M01 appears only when the level's confirmed-fact counts and post-translation
   approved-vocabulary counts meet the plan. Check prepared cards, labeled worked
   examples, sentence chunks, language direction, sequential hints, and refresh
   restoration. Verify a checked answer cannot receive more hints.
4. To exercise a generation failure, use a controlled test client rather than
   deliberately corrupting stored session data. Confirm an allowlisted, ready legacy
   lesson can be used, and that other languages receive the retryable skip and
   **Try again** action. A failed approved-vocabulary check must not call generation or
   use the legacy fallback.
5. Turn the flag off and confirm the existing M01 lessons and other mission behavior
   remain on their legacy paths.

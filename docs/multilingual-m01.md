# Shared multilingual M01 contracts

This is the stage 1 foundation for shared M01 contracts across A0, A1, and A2. It adds
language metadata, typed input/output contracts, and explicit routing only. Contract
generation remains disabled.

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
no contract requires grammatical features. Set `learnable = true` only when it should
appear in target-language pickers. Optional reviewed examples can be added to the
mission definition's `language_patterns.examples` table. New multilingual contract
languages do not require edits to the legacy builder or language allowlists.

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

The output validator checks facts, mission targets, required target groups, assessed
question count, unique chunks, answers, ordered hints, and definition-compatible
evaluations. It does not enforce article, gender, or plural rules.

## Routing and compatibility

`M01_VARIANTS` explicitly routes M01 A0/A1/A2 version 1. Missing mission, level, or
version combinations raise `UnroutedMissionVariant`; there is no A1 fallback.
`MULTILINGUAL_M01_ENABLED` remains `False`, and no workflow calls this path in stage 1.

The existing A0, A1, and A2 M01 lesson builders, their generated lesson behavior, and
saved v1 plans are unchanged. The legacy lesson registry now dispatches only explicit
A0/A1/A2 levels and rejects unknown variants instead of falling back. Existing JSON
storage in `answer_key.missionState` / `analysisDraft` is sufficient for later stages, so
there is no migration.

## Remaining stages

- **Stage 2:** produce contract output from contract input, adapt it to
  `GrammarLessonContent` and `TaskAnswerKey`, then enable the path per level.
- **Stage 3:** integrate UI rendering for chunk joins, hints, worked examples, RTL and
  non-Latin scripts, and registry TTS locales; only then consider offering Hindi, Tamil,
  and Simplified Chinese in target pickers.

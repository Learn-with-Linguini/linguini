# Language-pack foundation

This package supplies the default-off A0/A1/A2 runtime path for pack missions (M01,
M02, M03, M04, M05 and M06) as well as explicit local previews. Packs are loaded lazily only when the flag
is enabled or a command explicitly requests one. Other missions use their existing
implementations.

Packs live at `<root>/<locale>/<register>/` (for example `packs/es-ES/everyday/`). `pack.toml`
holds metadata and references every content file: `labels.toml` (fixed learner-facing text keyed by
semantic IDs), the optional `numbers.toml` (number words for counting missions),
the optional `possessives.toml` (possessive words and a role-play cast for ownership and
preference missions), the optional `requests.toml` (order quantities and requested details
for request role-plays),
`constructions/*.toml` (grammar guidance, features, constraints, version),
`examples/*.toml` (scene facts, bindings, sentences, chunks, alternatives, contrasts, mistakes) and
`evaluations/*.toml` (held-out cases per mission level). Evaluations are loaded only through
`load_evaluation_cases` and never appear in guidance or cache fingerprints. Release configuration and
evaluation reports are kept outside packs. The preview CLI validates and prints local plans without
accessing a database, calling a model, or writing output files (run from `backend/`):

```sh
python -m app.language_packs.preview validate --pack-dir app/language_packs/packs/es-ES/everyday
python -m app.language_packs.preview capability --pack-dir app/language_packs/packs/es-ES/everyday --language es --register everyday
python -m app.language_packs.preview plan --pack-dir app/language_packs/packs/es-ES/everyday --language es --register everyday --level A0 --scene scene.json
```

Release allowlists are explicit and default to empty. Structural validation checks
references, reviewed vocabulary forms, labels, chunk reconstruction, and Unicode
normalization; it does not infer meaning, grammaticality, or learner readiness.

The fixture pack is unreviewed test data and is not a claim of linguistic validation.

## Normal workflow and local switches

`LINGUINI_LANGUAGE_PACKS` is a boolean switch, default `false`. Only `true`
(case-insensitive) enables it. Off retains the legacy dispatch, including its
deterministic builders. On uses the existing mission eligibility/planning flow,
then binds the actual session's confirmed object instances, attributes, relations,
counts, translated vocabulary and register to the mission's slots. With the flag on,
M01, M02, M03, M04, M05 and M06 never use their legacy builders. No sample input or handwritten
`plan_specs` is used by the application.

Set these values in the ignored **backend/.env.local** for a local experiment:

```dotenv
APP_ENV=local
LINGUINI_LANGUAGE_PACKS=true
LINGUINI_LANGUAGE_PACK_DIRS=app/language_packs/packs/es-ES/everyday
LINGUINI_LANGUAGE_PACK_REGISTER=everyday
LINGUINI_LANGUAGE_PACK_EXPERIMENTAL=true
```

To discover multiple packs, the directory setting also accepts a recursive parent
root (`app/language_packs/packs`) or a glob (`app/language_packs/packs/*`). This is
a discovery setting, separate from the boolean feature flag. Multiple entries use
the platform path separator (`;` on Windows). Overlapping roots load a manifest
once; genuinely duplicated pack IDs across different manifests remain errors.
Unmatched globs report a configuration error. Restart the backend after changes.

The existing **Profile → Target language** selector requests additional choices
from `GET /api/v1/me/practice-languages`. It retains existing language choices and
adds configured pack languages that pass the selected register's runtime gates,
with experimental choices labelled accordingly. Display names come from language
codes through `Intl.DisplayNames`, rather than a new hard-coded language list.
The existing onboarding language selector and profile save validation also use
these discovery results. Placement content is still legacy; use Profile after
signing in for pack experiments, without assuming placement is pack-backed. Supported M01 levels determine the initial level when
selecting a pack-only language; existing profiles can also be patched through the
existing profile API to exercise another supported level.

Pack availability extends mission candidates only with pack missions (M01-M06)
that the app offers at the level and the pack has ready.
Photo eligibility and release checks still apply. Other missions and I-Spy retain
their existing language availability. Discovery does not constitute linguistic
validation or release approval. With the feature flag off no packs are discovered
for the selector or mission planning. Invalid discovery configuration is exposed
as a recoverable selector error with a retry action.

Run from `backend/`, retaining the existing database/authentication/provider setup:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --env-file .env.local
```

In another terminal, from `frontend/`:

```powershell
npm run dev
```

The normal UI uses the configured `learningTask` provider when this flag is on;
using a live provider there incurs model calls. The automated commands below use
mocked responses and do not need AI credentials. Changing a flag does not rewrite
saved tasks: start a new lesson after each change. Restart the backend after environment
configuration changes. Pack-file revisions are detected for new sessions; an
operation already running keeps its original snapshot. Generation cache entries include
pack content/version, selected construction content/versions, lexical data,
generator, assessor, contract and validator versions. Personal scenes retain the
workflow's cache scope.

To exercise the normal workflow manually at each Spanish level, use a local test
account with an active Spanish profile. Change its level through the existing
profile API (use `A0`, then `A1`, then `A2`), creating a new lesson each time:

```powershell
$api = 'http://localhost:8000/api/v1'
$headers = @{}
# For authenticated mode, use your local test account's access token:
if ($env:LINGUINI_ACCESS_TOKEN) {
  $headers.Authorization = "Bearer $env:LINGUINI_ACCESS_TOKEN"
}
$profiles = Invoke-RestMethod "$api/me/language-profiles" -Headers $headers
$spanish = $profiles | Where-Object targetLanguageCode -eq 'es' | Select-Object -First 1
$level = 'A0' # Repeat with A1 and A2, finishing/abandoning the previous lesson first.
Invoke-RestMethod "$api/me/language-profiles/$($spanish.id)" -Method Patch `
  -Headers $headers -ContentType 'application/json' `
  -Body (@{ proficiencyLevel = $level; isActive = $true } | ConvertTo-Json)
```

Confirm two differently named objects for A0. For A1, confirm two objects with
details and at least two clearly distinct taught colour options, such as a red
cup and a green book. For A2, confirm three objects and a detail or relation; a
red cup on a table plus a book exercises both detail and location. Confirm only
facts visible in the photo. Keep the existing review flow and complete the lesson.
Inspect `GET /api/v1/sessions/<session-id>/tasks`: M01 has 6/4/5 questions for
A0/A1/A2, respectively. Mission selection still follows existing history and
eligibility; use a fresh local test profile/account if previous mission history
prioritizes other missions. No progression or mission selection override is added.

Production/release use requires **all** existing review, current evaluation and
release-allowlist gates. `LINGUINI_LANGUAGE_PACK_EXPERIMENTAL` is honored only for
`APP_ENV=local`, `development` or `test`; it never grants production readiness.
For release evidence, `LINGUINI_LANGUAGE_PACK_EVIDENCE_DIR` contains files named
`<pack-id>-M01-<level>.json`; `LINGUINI_LANGUAGE_PACK_RELEASES` retains the explicit
`es:M01:A0,es:M01:A1,es:M01:A2` allowlist syntax. The included Spanish pack remains
**unreviewed**, so setting the flag and allowlist alone cannot release it. Do not
create review metadata to make the gates pass.

## Pack missions

`missions.toml` is the language-independent catalog of pack lessons: for each
mission, level and content version it lists the question slots in order (purpose,
construction, targets, repeats) and the fixed labels and minimum construction
versions they need. Readiness checks it against each pack, planning expands it into
slots, and generation guidance is selected per slot from it. It contains no
sentences; those come from packs and the model.

Mission-specific code lives in the `lessons` package, one module per mission, each
exposing `MISSION = PackMission(...)` (`lessons/base.py` defines the contract):

```text
lessons/
  __init__.py   registry: PACK_MISSION_IDS and pack_mission(id), loading modules lazily
  base.py       PackMission contract and for_level()
  common.py     SpecBuilder (planning), LessonContext and with_romanization (assembly)
  m01.py        M01: plan_lesson, build_lesson, checks, MISSION
  m02.py        M02: same layout
  m03.py        M03: same layout, plus number_vocabulary
  m04.py        M04: same layout, plus ownership_facts and possessive_vocabulary
  m05.py        M05: same layout (A0 and A1), plus preference_facts and preference_vocabulary
  m06.py        M06: same layout (A2), plus order_facts and request_vocabulary; builds two tasks
```

Every mission module has the same sections:

1. **Planning**: `plan_lesson` dispatches to `_plan_a0`/`_plan_a1`/`_plan_a2`, which
   add specs (construction, use, bindings, truth, labels, counterfactuals) to a
   `SpecBuilder`. `specs.skip(slot)` marks a slot that reuses other slots' sentences.
2. **Assembly**: `build_lesson` creates a `LessonContext` and dispatches to
   `_build_a0`/`_build_a1`/`_build_a2`. Each looks up accepted sentences
   (`ctx.sentence`, `ctx.sentence_by_id`), labels (`ctx.label`), seeded shuffles and
   tiles (`ctx.shuffle`, `ctx.chunks`), and returns dev's existing result model and
   task builder output, so grading and corrections stay unchanged. `ctx.finish` adds
   romanization and tile join modes.
3. **Checks**: `check_inputs` (before any model call), `check_lesson` (the assembled
   question count, order and interactions; `common.check_questions` covers the shared
   rules) and `photo_reasons` (replacing dictionary-based legacy photo rules; it also
   receives the learner's `counted_groups` and `mission_choices`).

A mission may also set `vocabulary`, which adds closed pack words to the lesson
vocabulary before proposals and planning (M03 adds the pack's number words, M04 its
possessives, M05 its cast names, M06 its order words), and `facts`, which adds the lesson's
own facts first (M04's owners, M05's preferences, M06's order). The
`facts` hook receives the saved mission plan's `learner_facts` and `roleplay_facts`,
which the workflow now passes to pack lessons as dev's builders already received them.

To add a mission: add its templates to `missions.toml` (matching the content version
of its `missions/definitions` file), write `lessons/mXX.py` in this layout, add it to
`_MODULES` in `lessons/__init__.py`, and give each pack the constructions, labels,
examples and evaluations it needs. The pipeline, checks, evaluation (`--mission`) and
release gates are shared. The definition files still supply each mission's objective,
targets, photo requirements and content version; their `language_patterns` example
sentences are not used by pack lessons.

A session's language context records which mission templates are ready and which
the pack declares (`readyMissions`, `declaredMissions`; older snapshots load as M01).
With the flag on, every registered mission is pack-owned: its ready versions are
planned and others are not offered, never replaced by the legacy builder. Missions
without a pack implementation keep their legacy builders. Learner-confirmed counts
are bound as `counted_groups` facts for missions that need them.

M02 reuses dev's M02 task builders, grading and corrections at every level; the
model writes its target-language text through five pack constructions:
`find-object` (A0 "find the X"), `where-question` and `location-phrase` (A1 question
and position choices, with false positions from model-proposed alternatives),
`target-clue` (A2 detail/location clues and clarifications that never name the
object) and `target-location` (A2 named, described and located target), plus
M02 examples for `identify-object` and `scene-location`. M02 evaluation cases
(`evaluations/M02-<level>.toml`; A1 is content version 2) cover finding and naming
objects, locations, position phrases, where-questions, clues that hide the target,
the `No, ...` clarification and the named, described and located target. False
position options are not cases: a case scene declares no alternative relation.

M03 (count objects) needs the pack's `numbers.toml`: reviewed number words with the
form each takes next to a counted noun when it differs (`with_noun`: Spanish
un/una by agreement, Korean 두 개 with its counter), plus romanization where the pack
requires it. Its templates list `required_numbers` (1–3 at A0, 2–10 at A1/A2); a
pack missing them, or their romanization, does not support M03. Number words become
`number-N` terms (alternatives: practice boards, the friend's wrong count) and each
learner count a `count-K` term in its noun's form, both with the `determiner` role.
The model writes the sentences through five constructions: `how-many-question`,
`quantity-chunk` (A0 "two apples", not a sentence), `quantity-statement` (A1/A2
counts, the practice board and the role-play correction), `quantity-comparison` (A2,
with the `more`/`fewer` sentence labels) and `quantity-pair` (A2 both counts in one
sentence). A0 and A2 reuse dev's builders; A1 builds dev's task here because dev's
A1 corrections are written per language. Proposals now also supply `plural` noun
forms. As in dev, A0 counts the first learner-counted group of 2 or 3; further groups
never block it. M03 evaluation cases are described under the evaluation section below.

M04 (whose is it?) needs the pack's `possessives.toml`: reviewed possessive words for
`first` (my), `second` (your) and `third-masculine`/`third-feminine`, each form a
`determiner` (mi, ma, meine, 제) or a `predicate` (mía, moi, mir), limited to one
noun gender where it agrees (French `before_vowel` marks mon before a feminine vowel),
and a role-play `cast` (Ana and Leo, with the names each script uses). Templates list
`required_possessors`. Who owns what is a lesson fact (`owners`): the object the learner
says is theirs (A0, `learnerFacts`), the saved role-play (A1, `roleplayFacts`), or, at
A2, an object a confirmed detail tells apart from another, assigned to the learner and
the other to Ana. Each owner becomes a term written with its possessor's forms; the
other possessors are alternatives (`possessor-second` for "is it yours?", the learner
or a cast owner for wrong-owner options). Six constructions write the sentences:
`ownership-question` (¿Es tuya?), `ownership-statement` (Es mía. / No es mía.),
`owned-object` (La taza es mía. / El libro es de Ana.), `possessive-statement` (Es mi
taza.), `whose-question` (¿De quién es la taza?) and `owned-description` (Mi taza es
roja.); A2 also reuses M02's `target-clue`. The lessons reuse dev's M04 question sets
and task builders: A0's six-question lost-and-found situation (dev's
`a0_situation_lesson_task` now accepts content prepared elsewhere), A1's role-play and
A2's five questions. A deterministic rule checks possessive agreement: when a sentence
uses gendered forms of the bound possessive and none is the noun's own (mein Tasse, la
taza es mío), it fails; forms for any gender (mi, mir) and genderless languages are not
judged, and French mon/ma before a vowel is left to the model review. Possessive words
are pack data, so proposals never change them (proposals v5).

M05 (say what you like) exists at A0 and A1. Who likes what is a lesson fact
(`preferences`: an object, a `person` and `likes`): the learner's own choice at A0
(`learnerFacts.preference`: the chosen object, the one it was compared with and the
reaction) or the saved role-play at A1, where, as in dev, the learner and Leo like their
objects and Ana does not. The cast comes from `possessives.toml`; each cast member's
preference becomes a term with their name, so a sentence must name the bound person and
naming another is an unbound fact. A spec's use is its polarity: `like` says the person
likes the object and `dislike` that they do not, with `truth` false for a deliberate
contrast. Constructions check polarity by use (`[[checks]]` with `uses = ["dislike"]`
demand the negative, `uses = ["like"]` forbid it). Four constructions write the
sentences: `my-preference` (Me gusta la taza. / No me gusta la taza.),
`their-preference` (A Ana no le gusta el libro.), `preference-question` (¿Te gusta la
taza? / ¿A Ana le gusta el libro?) and, at A0, `choice-statement` (Elijo el libro.). A0
reuses dev's six-question picnic situation: the noun phrases for picture and dialogue
gaps are what two sentences in one frame write differently (la taza / el libro, 컵을 /
책을), and the like/dislike chunk is the side of the noun phrase that differs (___ la
taza.), or the whole sentence when one side would be empty (Ich mag die Tasse [nicht].).
The situation validator takes the lesson's own negative chunk (`negativeMarker`) for
languages it has no fixed marker for. A1 reuses dev's three role-play questions and task;
its explanation shows the lesson's frames with the noun taken out (Me gusta… = I like…),
so no answer is shown whole. The A0 photo rule needs the learner's choice, as M04's does.

M06 (ask for the details) exists at A2. The order is a lesson fact (`orders` and
`requests`): dev's seeded M06 transaction for the first requestable photo object (dev's
English item list decides which objects are requestable and their scenario: café, shop,
classroom, home), or the transaction saved with the session plan, so a regenerated lesson
keeps its order and the reply mode follows the learner's M06 history as in dev
(`progress` in the mission context). Its quantity and details become `request:<field>`
facts: `quantity`, a café drink's `size`, and the detail the server asks about
(`serviceSetting`, `temperature`, `size` or `colour`). The pack's `requests.toml` gives
every form an order writes them in (un/una, einen, 두 before a counter; pequeño/pequeña…;
para llevar, 포장); templates list `required_requests`. Order words become terms:
`request-<field>` for the order itself and `number-N`/`detail-<field>-<value>`
alternatives, so the structural checks reject a wrong quantity, size or detail (the bound
one is missing or an unbound one appears). Seven constructions write the sentences:
`polite-request` (Quisiera dos cafés pequeños, por favor. / ¿Me prestas un bolígrafo, por
favor?; the use names the frame: `order`, `borrow`, `pass`), `order-phrase` (the order as
written inside the request, which locates the polite frame for the gap question, and the
same phrase with a wrong quantity for the extra tiles), `detail-question` (use
`askServiceSetting` and so on), `detail-reply` (Para llevar, por favor.; the wrong value
and another detail as choices), `order-repeat` (the server's check; false when the
transaction gives the server a mistake), `order-confirmation` (Sí, eso es.) and
`order-repair` (En realidad, tres, por favor.; also with the served value, for the
wrong-value tile). A `target` binding is context for agreement and never named. The
lesson reuses dev's six M06 questions, validator and `build_m06_tasks`, so the mission
builds two tasks (place the order, finish it) with the same transaction, scenario card,
feedback and assistance steps. The polite-frame distractors are labels
(`request-distractor-have`/`-exists`: Tengo, Hay). Choosing another item would need new
sentences, so a pack lesson offers no alternatives on its scenario card. Request
constructions recognise regular plurals after a quantity (cafés, Stifte) as counting ones do.

Several objects can share a target-language name (two cabinets). A question that only
names the object accepts every marker on an object with that name: A0 marker questions
list the others in `acceptedOptionIds` on the private answer key, which grading checks
alongside the correct option. Contrasts need another name, so planners pick
differently named objects for false statements, name choices, focus objects and
marker distractors. Descriptive questions ("the cabinet next to the window") still
accept only the described object.

## One language context per normal M01 generation

Scene analysis resolves the selected pack before provisional eligibility/planning.
Review and the background generation claim restore that same session snapshot before
final planning and translation; older sessions capture it at the first such operation. Its immutable serialized snapshot supplies translation, vocabulary
preparation, M01 generation and validation; later stages never resolve another pack.
It records pack ID/version and a guidance/version fingerprint, locale, variety,
register, script/direction, grammatical requirements, transliteration convention and
speech preferences. Private snapshot metadata uses the existing session analysis
JSON; vocabulary and M01 task JSON persist the public `languageContext` for reload.
No migration is required. Old saved tasks omit this optional metadata and retain
legacy rendering. Pack changes affect new operations rather than rewriting tasks.

The default register is deterministically `everyday`. Set
`LINGUINI_LANGUAGE_PACK_REGISTER` explicitly to select another register. An empty
setting selects the only matching pack; multiple matches require an explicit
register. Missing/ambiguous configurations and unmet readiness gates are errors,
with no silent selection of a different language/register.

Optional `[language]` fields `articles` and `grammatical_gender` accept `required`,
`optional` (the compatibility default), or `none`. These requirements apply to
object translation metadata. Spanish explicitly requires articles and gender.
`inflection = "suffixing"` (default `none`) tells the structural check that
particles and case endings attach to words, so a bound noun or detail may appear
inside a longer word (Korean 컵이에요); `stem_endings` lists final letters a stem may
lose before a suffix. This only finds a bound role that whole-word matching missed;
`modifier` forms (Korean 빨간) never take suffixes, and meaning stays model-assessed.
Korean also has a targeted validator (`validators/ko.py`) for particle forms after a
final consonant (문이에요, not 문예요).
`nativeDisplay` is required throughout the pack translation path and is displayed
as returned after validation; the application adds no article prefix. Required
`romanization` is separate from optional legacy `phoneticText` (English-sound
respelling). `romanization_convention` describes the pack's Latin spelling rules;
older packs requiring romanization use a generic Latin-transliteration instruction
when that field is absent. Reference vocabulary remains optional guidance.

Translation cache identity includes this context and its guidance fingerprint.
Preparation checks required native/Latin text before committing task 1; incomplete
output fails recoverably rather than publishing incomplete cards. Fixed preparation
fallback choices require pack labels `vocabulary-unsure` and `vocabulary-other`
when needed, plus Latin spellings if required. Missing target labels never silently
become English options. Raw scene suitability and validated translation readiness
remain separate; accepting an object name does not claim its translation is ready.

The existing learner screen applies saved direction/locale to target text and inputs,
keeping English controls separate. Native text remains the grading and TTS input.
Speech policy/locale is only a preference: audio controls depend on installed browser
voices and respect `synthesis = "none"`. Required Latin spelling is rendered alongside
native vocabulary and sentence supports, with English-sound pronunciation separately
labelled. These structural checks and model assessments do not prove linguistic
correctness. Reviewer stages, correction generation and grading normalization remain
later milestones; this change does not migrate placement or other missions.

## Shared contracts and failure behavior

Packs supply construction guidance, register, labels and reference examples/forms.
Optional `lexical` data supplies supporting vocabulary, never an exhaustive runtime
dictionary. The Spanish runtime pack contains no `lexical.*` tables: session
translation and model proposals supply new words, grammatical forms and distractors.
Small finite reference data is confined to explicit scripted parity-test fixtures.
Normal M01 first asks the model for candidate grammatical forms and
meaning-anchored distractors, then asks for the application-planned sentences.
Missing reference words/forms can be proposed. The historical `ApprovedVocabulary`
container name is retained for compatibility; `modelProposal` provenance explicitly
identifies unreviewed proposals, not reviewed vocabulary or new confirmed facts.
Original session meanings and instance IDs remain separate and authoritative.

Proposal identities, duplicate forms and target/distractor equality are checked
mechanically. A mandatory contextual model assessment then checks original meanings,
sentence/form grammar, level/register, distractor policy, distinctness, ambiguity
and supported scene claims before sentences are accepted and tiles are derived.
An additional assessment checks the rendered choices, supports, feedback and answer
map together. A synonym distractor must not become another correct answer. Absent
objects may be alternatives (including distractor tiles), never newly asserted
scene facts. Detector omission does not prove absence. Semantic MCQs require
grammatical distractors; existing grammar-discrimination tile policy is preserved.

These are fallible **model assessments**, reported as `modelAssessed`, not human
review or proof of correctness. Negative or uncertain assessments fail recoverably,
including in experimental mode. The release/eligibility gates remain unchanged.
The normal path now uses proposal generation, sentence generation, pre-assembly
review and rendered-task review (four routed requests before repairs, without a
sentence cache hit). Extra assessment adds latency/cost for explicit live runs.
Scripted demo fixtures explicitly retain reference-only mode (`propose=False`);
they are not proof of open-vocabulary model performance.

Sentence prompts contain bound facts, candidate forms, register, selected
construction guidance, examples and corrections filtered by level/task. Held-out
evaluations are never generation guidance. Spanish checks remain scoped to Spanish;
open wording is not forced into reference-example templates. Structural success
is not proof of meaning or grammaticality. Unsupported languages do not inherit
Spanish grammar checks. Non-Spanish linguistic quality has not been tested.

`language.romanization_required` defaults to false. When true, the generator must
provide aligned native/Latin spans for **every new sentence**, plus spellings for
displayed supports and vocabulary. Concatenating native spans must reproduce the
canonical sentence exactly. Response `romanizations`, preparation-card
`romanization` and `sentenceJoinModes` are optional display contracts. The browser
shows Latin spelling alongside visible native text; native text alone remains
the answer/grading/TTS input. Missing/misaligned spelling fails recoverably.
Existing packs and Spanish responses can omit all romanization fields.

Sentence repair is limited to two additional generation attempts and only failing
specs (a failed whole-batch assessment conservatively retries the batch). Each
attempt is assessed again. Missing/invalid proposal identities and rejected final
rendered-task assessments fail immediately; retrying through the UI requests new
proposals. No model verdict creates human-review metadata or release evidence.
Each sentence spec lists its permitted realization term IDs (distinct from scene
fact IDs). Unknown or unbound realization claims remain validation failures and
enter bounded sentence repair; they are never silently accepted or discarded as
successful mappings. Exhaustion reports the offending ID, surface and exact spec.
Failure after that raises the existing `learning_task_generation_failed` error;
the pack path does not silently replace the lesson with a legacy lesson or mark
it completed. Retry through the normal generation UI. Tile reconstruction keeps
Unicode, punctuation and join modes; identical tiles can swap positions, but a
tile ID cannot be reused. Unsupported spacing is rejected rather than normalized
into a different sentence.

## Verification for every bundled pack and optional live smoke

From `backend/`, the new tests exercise flag-off and flag-on **normal dispatch**
at all three levels with mocked Spanish provider responses:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_language_pack_runtime.py `
  tests/test_m01_language_context.py tests/test_language_pack_discovery.py `
  tests/test_language_pack_proposals.py `
  tests/test_language_pack_runtime_workflow.py tests/test_language_pack_pilot.py `
  tests/test_language_pack_assembly.py tests/test_language_pack_cache.py -q
```

`tests/test_language_pack_multilingual.py` runs the same normal dispatch for every
bundled pack (es, fr, de, ko) at A0/A1/A2 with a mocked provider that writes
each pack's taught patterns, including Korean particle realizations and
aligned romanization. It also evaluates each pack against its sample vocabulary.
The mocked sentences are test data, not model evidence:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_language_pack_multilingual.py -q
```

Persistence/completion tests require `TEST_DATABASE_URL` for an already migrated,
disposable PostgreSQL database. They skip without it. Never point tests at the
live Supabase database. No schema migration is part of this change.

Each pack has demo inputs in `samples/<locale>/`: `scene.json` (a red cup on a
table and a green book, planned automatically) and `vocabulary.json` (those facts
plus every fact used by the pack's evaluation cases, with the `plural` forms that
model proposals supply at runtime for counted nouns). Evaluate any pack locally
(`--mission` defaults to M01):

```powershell
$packs = @{ es = 'es-ES'; fr = 'fr-FR'; de = 'de-DE'; ko = 'ko-KR' }
foreach ($language in $packs.Keys) { foreach ($mission in 'M01','M02','M03','M04','M05','M06') { 'A0','A1','A2' | ForEach-Object {
  if ($mission -eq 'M05' -and $_ -eq 'A2') { return }  # M05 has A0 and A1 only
  if ($mission -eq 'M06' -and $_ -ne 'A2') { return }  # M06 has A2 only
  .\.venv\Scripts\python.exe -m app.language_packs.preview evaluate `
    --pack-dir "app/language_packs/packs/$($packs[$language])/everyday" `
    --language $language --register everyday --level $_ --mission $mission `
    --vocabulary "app/language_packs/samples/$($packs[$language])/vocabulary.json"
} } }
```

Every pack meets the evaluation thresholds at every level it has a template for: every valid sentence
is accepted and no reject is missed. Cases whose IDs contain `-held-` were written
after the rules below, with other nouns, genders and constructions, to check
that the rules generalize rather than fit the original cases. Thresholds are
evidence only: release still needs fluent human review and the allowlist, and a
small AI-authored case set is not proof of linguistic quality. Held-out
sentences are judged as native text; required romanization is checked on
generated candidates instead. A case may set `use` (for example `use = "name"`)
when its plan use cannot be inferred from its input.

M03 cases (`evaluations/M03-<level>.toml`) declare learner counts as scene `counts`;
the evaluator binds them as counted groups and adds the mission's number words, as
lessons do. A false case may bind a pack number (`count = "number:7"`: a practice
board or a friend's wrong count), which is pack data rather than a scene fact. A
labelled sentence is planned in the slot that allows its labels (`No, ...` in the
A2 correction slot). Rejects cover the wrong object, the wrong count (`wrongCount`),
a missing plural or a number in the wrong form, broken frames and punctuation, the
wrong comparison word and decomposed text. Counting is checked for every pack by the
deterministic count-agreement rule: a bound number is written in the form the pack
gives it next to that noun (`numbers.toml` `with_noun`: una manzana, 두 개), and a
count above one takes the noun's `plural` form when the session has one that differs
from the bare noun. Korean has no plural forms, so only its counter forms are judged.

M04 cases declare who owns what as scene `owners` (`{ fact_id = "owner:bag",
object = "object:bag", owner = "first" }`, or a cast owner such as `ana`); any case may
bind a pack possessor (`owner = "possessor:second"`: "is it yours?"). Rejects add the
wrong owner (`wrongOwner`) and possessive agreement where a pack's rule judges it
(Spanish mío/mía, German mein/meine). Fixed frames with one natural wording
(Gehört das dir?) use another valid wording in held-out cases, since evaluation
sentences never repeat a generation example.

M05 cases declare who likes what as scene `preferences` (`{ fact_id =
"preference:bag", object = "object:bag", person = "ana", likes = false }`) and set
`use = "like"`, `"dislike"` or `"question"`. Rejects add the opposite polarity, the wrong
person (another cast member's name), the wrong object and broken question frames.

M06 cases declare the order as scene `requests` (`{ fact_id = "request:quantity", object =
"object:tea", field = "quantity", value = "2" }`, `field = "temperature", value = "hot"`)
and set the spec `use` (`order`, `borrow`, `pass`, `request`, `askTemperature`, `reply`,
`repeat`, `confirm`, `repair`). A false repeat binds a pack value (`size =
"detail:size:small"` or `quantity = "number:3"`): the server's mistake. Rejects add the
wrong quantity, size, detail and item, a statement instead of a request (Hay…, Es gibt…),
a missing politeness tail, a reply or repair that confirms, and broken question marks.

## Shared noun-phrase validator

Packs with `articles = "required"` (es, fr, de) also run `validators/noun_phrase.py`,
generalized from the Spanish validator. It reads only the session's own forms:

- the bound noun appears with one of its own determiners, taken from its
  `article_*`, `definite*`, `indefinite*` and `negative*` forms (so German
  `einen Löffel`, `dem Tisch` and French `l'assiette` count), with up to two
  adjectives in between;
- identifying, confirming and existence sentences use the indefinite kind; names
  and detail questions use the definite kind; locations, connected descriptions and
  descriptions (including predicative *La porte est rouge*) accept either;
- after an indefinite article, an attributive adjective uses the noun's
  `masculine`/`feminine`/`neuter` form (German weak endings after a definite
  article are not judged);
- an attributive adjective sits on the side given by its `position`; predicative
  forms are not judged.

Negated existence (`pas de`, `kein`), counting constructions (a number or quantity
word introduces the noun: `cinco libros`, `combien de`, `wie viele`), ownership and
preference constructions (a possessive introduces the noun, or the verb sets its case:
`Ich mag den Teller`; noun-phrase v4), request constructions (a quantity introduces the
item, in the case its verb takes: `einen Stift`; noun-phrase v5) and
model-proposed wording are skipped; the last is judged by the mandatory model review. `validators/es.py` keeps the
Spanish-only rules (name chunks, `del`/`al` references, `¿…?`, ser/estar/hay).

## Declarative construction checks

Each construction file can declare `[[checks]]`: high-precision surface rules run by
the shared `pack-checks` validator (`validators/checks.py`) for every language,
alongside any targeted validator such as `validators/es.py`:

```toml
[[checks]]
check_id = "negated-existence"
message = "A false existence statement uses il n'y a pas de."
must_contain = ["n'y a pas"]      # every pattern must match
must_not_contain = []             # no pattern may match
except_uses = ["falseFirst"]      # or uses = [...]; empty means every use
truth = false                     # optional: only true or only false specs
```

Patterns are Python regular expressions, matched case-insensitively (set
`case_sensitive = true` to change that) against NFC text with typographic
apostrophes folded to `'`. Patterns are kept exactly as written, so edge spaces act
as word boundaries (`" y "` never matches the y of *hay*). Uses are plan spec uses: `name`, `question`, `prompt`,
`answer`, `option`, `followup`, `fact1`-`fact3`, `connected`, `wrongAttribute`,
`falseFirst` and `wrongExistence`. Invalid patterns, empty checks and duplicate
IDs are pack load errors.

Checks apply to model-proposed wording too, so they must never depend on exact
word spellings: prefer punctuation, fixed construction frames, negation markers,
verb position, register endings, elision/contraction and case after location
prepositions. A check that rejects a valid sentence uses up repair attempts and
can fail a lesson. `tests/test_language_pack_checks.py` therefore runs every
check against every pack example and accepted alternative, and the multilingual
evaluation test requires every valid evaluation sentence to be accepted. A failed
check's message is returned to the generator as a repair reason. Check content is
part of the pack fingerprint, so editing a check invalidates cached sentences and
evaluation evidence; `pack-checks.v1` versions only the runner. The starter checks
are AI-authored and unreviewed.

Optional **live demo smoke** for the user to run explicitly (incurs model calls;
these sample files are demo inputs only, not runtime dependencies). Replace the
locale and language code to try another pack:

```powershell
'A0','A1','A2' | ForEach-Object {
  .\.venv\Scripts\python.exe -m app.language_packs.preview --env-file .env.local generate `
    --pack-dir app/language_packs/packs/es-ES/everyday --language es `
    --register everyday --level $_ --source model --preview `
    --scene app/language_packs/samples/es-ES/scene.json `
    --vocabulary app/language_packs/samples/es-ES/vocabulary.json
}
```

The command uses the existing configured learning-task route and credentials;
load local environment settings as in the backend README. Passing `--preview`
does not create release evidence. Evaluation commands now require an explicit
`--vocabulary` argument; generic commands never silently select Spanish samples.
Non-Spanish linguistic quality and live model generation behavior were not tested.

Detail choices (A1 colour choice, A2 follow-up) use a proposed `predicative` form
when one differs from the in-sentence agreement forms (German *rot* beside
*rote/roter/rotes*). Wrong-agreement tiles come only from `masculine`, `feminine`
and `neuter` forms, and never for packs with `grammatical_gender = "none"`.

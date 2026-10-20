# Language-pack foundation

This package supplies the default-off M01 A0/A1/A2 runtime path as well as explicit
local previews. Packs are loaded lazily only when the flag is enabled or a command
explicitly requests one. Other missions use their existing implementations.

Packs live at `<root>/<locale>/<register>/` (for example `packs/es-ES/everyday/`). `pack.toml`
holds metadata and references every content file: `labels.toml` (fixed learner-facing text keyed by
semantic IDs), `constructions/*.toml` (grammar guidance, features, constraints, version),
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

`LINGUINI_M01_LANGUAGE_PACKS` is a boolean switch, default `false`. Only `true`
(case-insensitive) enables it. Off retains the legacy dispatch, including its
deterministic builders. On uses the existing mission eligibility/planning flow,
then binds the actual session's confirmed object instances, attributes, relations,
translated vocabulary and register to M01 slots. No sample input or handwritten
`plan_specs` is used by the application.

Set these values in the ignored **backend/.env.local** for a local experiment:

```dotenv
APP_ENV=local
LINGUINI_M01_LANGUAGE_PACKS=true
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

Pack availability extends mission candidates only with M01 at supported levels.
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

## Missions beyond M01

`missions.toml` is the language-independent catalog of pack lessons: for each
mission, level and content version it lists the question slots in order (purpose,
construction, targets, repeats) and the fixed labels and minimum construction
versions they need. Readiness checks it against each pack, planning expands it into
slots, and generation guidance is selected per slot from it. It contains no
sentences; those come from packs and the model.

`registry.py` holds the mission-specific code (`PACK_MISSIONS`): a planner that binds
confirmed facts to the slots, an adapter that turns accepted sentences into the
existing task contract, input and assembled-lesson checks, phrase-tile slots and pack
photo rules. Only M01 is registered today. To add a mission: add its templates to
`missions.toml`, register its code, and give each pack the constructions, labels,
examples and evaluations it needs. The pipeline, checks, evaluation (`--mission`)
and release gates are shared.

A session's language context records which mission templates are ready and which
the pack declares (`readyMissions`, `declaredMissions`; older snapshots load as M01).
A declared mission is owned by the pack: its ready versions are planned and blocked
ones are not offered, never silently replaced by the legacy builder. Missions a pack
does not declare keep their legacy implementation. Learner-confirmed counts are
bound as `counted_groups` facts for missions that need them.

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
plus every fact used by the pack's evaluation cases). Evaluate any pack locally:

```powershell
$packs = @{ es = 'es-ES'; fr = 'fr-FR'; de = 'de-DE'; ko = 'ko-KR' }
foreach ($language in $packs.Keys) { 'A0','A1','A2' | ForEach-Object {
  .\.venv\Scripts\python.exe -m app.language_packs.preview evaluate `
    --pack-dir "app/language_packs/packs/$($packs[$language])/everyday" `
    --language $language --register everyday --level $_ `
    --vocabulary "app/language_packs/samples/$($packs[$language])/vocabulary.json"
} }
```

Every pack meets the evaluation thresholds at A0, A1 and A2: every valid sentence
is accepted and no reject is missed. Cases whose IDs contain `-held-` were written
after the rules below, with other nouns, genders and constructions, to check
that the rules generalize rather than fit the original cases. Thresholds are
evidence only: release still needs fluent human review and the allowlist, and a
small AI-authored case set is not proof of linguistic quality. Held-out
sentences are judged as native text; required romanization is checked on
generated candidates instead. A case may set `use` (for example `use = "name"`)
when its plan use cannot be inferred from its input.

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

Negated existence (`pas de`, `kein`) and model-proposed wording are skipped; the
latter is judged by the mandatory model review. `validators/es.py` keeps the
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
apostrophes folded to `'`. Uses are plan spec uses: `name`, `question`, `prompt`,
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

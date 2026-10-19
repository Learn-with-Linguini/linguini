# Learner memory and progress tracking

Research for [#19](https://github.com/Learn-with-Linguini/linguini/issues/19), reviewed 17 October 2026 against `dev` at `f2b1fee`. This is a proposal: no scheduler, schema migration, or production setting changes. Recheck the mission contracts after active PRs #62 and #63 settle.

## Architecture and existing behavior

| Area | Responsibility |
| --- | --- |
| `frontend/` | React/Vite learner routes, scene review, tasks, journals, rooms, and marketing routes. TanStack Query carries backend state. |
| `backend/app/repositories/postgres/workflow.py` | Session lifecycle, generation claims, grading, attempts, vocabulary evidence, and rewards. |
| `backend/app/ai/features/` | Schema-constrained scene analysis, translation, lesson generation, and I-Spy interpretation. |
| `backend/app/repositories/postgres/` | SQLAlchemy persistence on PostgreSQL/Supabase; Prisma owns migrations. |
| `marketing/` | Undeployed launch materials; not part of learner memory. |

The photo loop already preserves useful provenance: approved objects, attributes and relations become translated learning material; accepted attempts and journal revisions persist separately. The backend controls correctness, XP, Basil, and session status.

[Rooms](../../backend/app/repositories/postgres/rooms.py) are separate, transactional two-player games. The baseline requires both players ready, expires invitations after ten minutes and play after thirty minutes, and waits for both acknowledgements between turns. Commands carry revisions and idempotency keys. Clue choice and object guesses award participation rewards; they do not establish unaided language production. Saved friends and asynchronous challenges should retain this distinction when their evidence eventually enters memory.

## Memory dataflow

1. [`_claim_generation`](../../backend/app/repositories/postgres/workflow.py) loads history only for lessons when `LEARNER_MEMORY_ENABLED=true` (default false). The current session is excluded, and generation retains an immutable claim and revision check.
2. [`snapshot_learner_history`](../../backend/app/repositories/postgres/learner_history.py) verifies ownership and isolates the language profile. It reads earlier lesson encounters, tasks, graded attempts, and completed journals. Accepted practice in incomplete sessions remains eligible; completion totals remain separate. Standalone I-Spy and room turns are outside this history.
3. All eligible history contributes before selection. The snapshot ranks scene-relevant terms, recent mistakes and recency, then limits model context to sixteen terms and 6 KiB. It excludes submitted answers and journal prose. Journal mentions, assisted mentions, selections, and accepted corrections remain distinct observations.
4. [`session_personalization`](../../backend/app/services/session_personalization.py) prioritizes previously missed current-photo words and summarizes returning vocabulary. Legacy grammar generation receives bounded history, preserves approved scene grounding, bypasses shared curated grammar templates, and uses a user-and-profile cache scope. This is adaptation by observed counts, not review scheduling.

## Gaps to resolve first

**Mission evidence stops before memory.** [`question_outcomes.py`](../../backend/app/services/question_outcomes.py) persists objective/target IDs, recognition or construction evidence, supports, assistance classification, and mistakes in `questionOutcomes`. The history query reads only `evaluationDetails.questionResults` (lines 267–295). Its word mapping recognizes introduction `word-…` questions; its grammar aggregation recognizes four legacy focuses. New focuses `identifyDescribeObject`, `findAndLocate`, and `sayHowMany` do not enter those grammar counters. Mission grammar can write object vocabulary encounters, but the richer skill and support evidence is lost to personalization. A construction with a word bank must stay construction even when the mission does not classify that support as assistance.

**Familiarity mixes different scopes and meanings.** `_mission_progress` reads object `mastery_score` by user and target language, while history is profile-specific. Sharing target-language familiarity across source profiles may be intentional, but it needs an explicit rule. Colour and position familiarity uses correct ratios from the already capped history; omission can make an observed term look unseen. Mission grading does not feed those term ratios directly.

[`vocabulary.py`](../../backend/app/repositories/postgres/vocabulary.py) maps status monotonically to scores 0, 0.5, and 1. Incorrect attempts do not lower them; time does not decay them. Journal selected words can advance status to `mastered` through `record_journal_usage`, even though the memory prompt correctly treats selection and assisted prose as participation. These scores are neither calibrated recall probabilities nor evidence of independent mastery.

**Bounded output still requires unbounded work.** Each snapshot scans eligible encounters, tasks and attempts, plus journals; term matching also grows with journal and vocabulary history. Sixteen output terms do not bound database work or Python aggregation. Measure rows scanned and latency before changing the cap.

## Proposed incremental work

**1. Establish typed evidence and projections.** Normalize accepted per-question outcomes into replayable observations keyed by attempt and question. Preserve profile, mission/content version, objective, targets, evidence type, supports, outcome, timestamp, and provenance. Treat missing legacy support data as unknown; do not invent independence. Derive SQL projections for each term/skill and retain enough source references to explain or rebuild them. Separate XP/Basil and user-selected vocabulary status from performance.

**2. Add a small due-review queue.** Schedule recognition, supported construction, and unaided production separately. Begin with explicit conservative intervals and a daily workload cap; compare alternatives by delayed recall. [Settles and Meeder's HLR paper](https://aclanthology.org/P16-1174.pdf) models recall using elapsed time and learned half-life. [FSRS-6](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm) models difficulty, stability and retrievability; [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) consumes Again/Hard/Good/Easy ratings and review timestamps. Binary multiple-choice correctness cannot supply those four ratings without a documented, evaluated mapping. Neither approach is validated for Linguini's interactions yet. Add no dependency until the evidence contract and comparison justify one.

**3. Connect terms, skills and photo facts.** Represent relationships in ordinary PostgreSQL tables: a sense-specific term appears in an approved photo object, has a confirmed attribute, participates in a directed relation, and is assessed by a mission target. Link attempts to the exact assessed nodes rather than crediting every word in a sentence. Use this graph to vary context and explain review choices. A dedicated graph database or vector store needs a demonstrated query or retrieval benefit. Optional interests, preferred practice style and remembered personal context should be user-editable and separate from performance.

## Validation and operating rules

Replay observations offline in chronological order, including repeated commands, late events and corrections. Version the reducer, scheduler, evidence schema and content. Freeze the evidence cutoff, selected targets and policy version for generation retries; a retry must not silently change its lesson. Isolate caches by owner/profile/version and invalidate affected projections and cached context after deletion or correction of photos and journals.

Keep regression coverage for feature-off and empty-history behavior, incomplete sessions, cross-profile isolation, deleted media, shared-template privacy and duplicate attempts. Start with shadow scheduling. Compare due-review adherence, workload and delayed unaided recall, with calibration and error rates by interaction and support use; completion and reward totals are supporting measures.

## Choices for discussion

1. Put due review into Home's existing next action, or offer a separate short review session?
2. Start scheduling recognition only, or add a deliberate unaided naming check alongside it?
3. Keep performance strictly per language profile, or explicitly share selected target-language evidence across source profiles?

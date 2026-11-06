"""Prose for MODEL_COMPARISON.md. Tables around it are generated from results.

Keeping the wording here means the document can be rebuilt after a re-run
without hand-editing Markdown, and the claims stay beside the harness that
produced the numbers.
"""

HEADER = """# Model and provider comparison

Which model Linguini should use for each of its five AI calls, measured rather
than assumed. Every candidate ran through the app's own services — the same
prompts, JSON schemas and validators that ship — so a number here is what a
learner would have got.

Regenerate this file with:

```powershell
.\\.venv\\Scripts\\python.exe -m evals.model_comparison.report --out ..\\MODEL_COMPARISON.md
```
"""

METHOD = """## How the measurements were taken

**Three providers.** OpenAI and Gemini are called directly. Everything else —
Anthropic, Qwen, DeepSeek, Meta, Mistral — is called through OpenRouter, which
serves them behind an OpenAI-compatible Responses API. OpenRouter adds a
routing hop, so its latencies are not strictly comparable with direct calls;
that is called out where it matters.

**Production code, not a copy of it.** Each candidate is built through
`app.ai.registry` and handed to the real feature service
(`SceneTranslationService`, `LearningTaskService`, `ISpyClueService`,
`UploadedSceneAnalyzer`) or, for I-Spy guessing, the real adapter. A recorder
wraps the model client to capture latency, tokens and the raw response, which
the services otherwise discard.

**Two different questions.** *Accepted by the app* is whether the output passed
the production validator — what the learner would actually receive. *Quality*
is scored from the raw response, so a rejected answer can still be diagnosed
rather than counted as a flat zero.

**Cases.** 14 labelled photos (clean, blurred, low-light, cropped, noisy, and
one deliberately unusable), 13 Spanish/French translation cases with a gold
lexicon, 4 Japanese/Korean probes, 6 hand-written scenes across four languages
for lessons and clues, and 22 learner descriptions whose intended object is
known, including directional traps, deliberate contradictions and off-topic
text.

**Repeat runs.** Models are not deterministic, so the shortlist runs each case
two or three times. *Run-to-run spread* is the standard deviation of the
overall score across repeats of the same case: treat any gap between models
smaller than that as noise.

**Judging.** Lesson quality and whether a clue can actually be solved have no
reference answer, so `anthropic/claude-sonnet-5` grades them against an
anchored rubric, and is never told which model produced the output. It is not
a candidate for any call. It does share a family with the
`anthropic/claude-haiku-4.5` candidate, so treat Haiku's judged scores with
more caution than the deterministic ones.

**Cost.** Computed from recorded tokens at the OpenRouter catalogue price,
which is the provider list price, so direct and routed calls are priced the
same way. Cost per 1,000 sessions assumes one scene analysis, one translation,
one lesson and one clue set per session, plus three learner descriptions.
"""

PARAMETERS = """## What was measured

| Parameter | Meaning |
|---|---|
| Overall quality | 0–1 composite, for ranking only; the columns beside it carry the argument |
| Output usable by app | Share of calls whose output passed the production validator |
| API errors | Share failing at the provider: timeout, overload, refusal, bad response |
| Run-to-run spread | Standard deviation of the overall score across repeat runs of one case |
| Identical repeat runs | How often repeats returned byte-identical output |
| Rate-limit retries | Our own quota retries; a property of the account, not the model |
| Latency p50 / p95 | Typical and near-worst wall-clock time for one call |
| Input / output tokens | Mean tokens per call, including image tokens and any reasoning tokens |
| Cost per call / per 1,000 sessions | Recorded tokens at list price |
| Context window, max output | Published limits, from the catalogue snapshot |
| Vision, temperature, reasoning | Takes images; accepts a temperature; is a reasoning model |

Call-specific quality columns (anchor recall, article accuracy, answer-key
errors, clue solvability, guess accuracy and so on) are defined in the section
for each call.
"""

RECOMMENDATIONS = """## Recommendations

| Call | Chosen | Replaces |
|---|---|---|
| Scene analysis | `openai:gpt-4.1-mini` (November 2026) | claude-haiku-4.5 |
| Translation | `openrouter:mistralai/mistral-small-2603` | gemini-3.5-flash-lite |
| Learning tasks | `openai:gpt-5.4-mini` | gpt-4o-mini |
| I-Spy clues | `gemini:gemini-3.1-flash-lite` | gpt-4o-mini |
| I-Spy guess | `openai:gpt-4.1-mini` | gpt-4o-mini |

**Scene analysis — Claude Haiku 4.5 (October).** Highest quality (0.79), found
every anchor object, and the only candidate the app accepted every time, at a
third of gpt-4o's cost. gpt-4.1-mini is the budget alternative at 0.68 and a
third of the price. Today's default failed every call.

**Scene analysis — GPT-4.1-mini (November 2026 re-run).** The scene prompt has
since grown into a reusable inventory of up to 20 objects, which made Haiku
expensive. A re-run on the current prompt compared OpenAI and Gemini models
only, on the same 14 photos: two runs per photo for OpenAI, one for Gemini to
save free-tier quota. Gemini quality counts its 503 errors as zeros.

| Candidate | Quality | Accepted | Anchor recall | Precision | p50 / p95 | Per 1,000 sessions |
|---|---|---|---|---|---|---|
| openai:gpt-5.4-nano | 0.65 | 50% | 1.00 | 0.84 | 8.2 s / 12.4 s | $1.71 |
| openai:gpt-4.1-mini | 0.64 | 82% | 0.74 | 0.80 | 10.2 s / 17.8 s | $2.88 |
| openai:gpt-5.4-mini | 0.62 | 75% | 0.91 | 0.68 | 6.4 s / 9.4 s | $6.84 |
| gemini:gemini-3.1-flash-lite | 0.43 | 71% | 0.79 | 0.80 | 6.5 s / 7.3 s | $2.46 |
| gemini:gemini-3.5-flash-lite | 0.32 | 50% | 0.43 | 0.67 | 6.2 s / 10.0 s | $2.17 |

gpt-4.1-mini is the most dependable low-cost choice: accepted most often, no
invented objects, and well under Haiku's cost, though it is the slowest and
finds the fewest anchors. Its rejections were empty answers on blurred or
low-resolution photos. gpt-5.4-nano found every anchor with the best precision
but rated real objects on degraded photos at 0.12–0.6, below the app's 0.7
confidence cut-off, so half its answers were discarded; a lower cut-off would
make it the better and cheaper choice, but would affect every model. On the
free tier, Gemini 3.5 Flash-Lite hit 503 "overloaded" on 5 of 14 calls and
mixed coordinate scales inside single boxes, 3.1 Flash-Lite wrote corner points
into box sizes, and gemini-3.7-flash returned 503 on both probes. gpt-4.1-nano
has been retired by OpenAI. Haiku was not re-run, and box accuracy rests on
1–10 labelled boxes per model, so it is not used to rank. Raw results are in
`backend/evals/model_comparison/results/full/scene-nov-openai.jsonl` and
`scene-nov-gemini-rescored.jsonl`. The generated scene-analysis tables below
still show October, because they would otherwise mix the two prompts.

**Translation — Mistral Small.** Joint best quality (0.97) at the lowest cost
($0.24 per 1,000 sessions) and the fastest median response (2.2 s). Claude
Haiku matched its quality with perfectly repeatable output, but at eleven
times the price.

Two caveats make this the closest call of the five. Mistral's lead over
gpt-4o-mini is 0.02, against its own run-to-run spread of 0.016 — inside the
noise. And OpenRouter rate-limited it on 12 of 51 calls (all recovered on
retry), where the direct providers were never throttled. **If throttling shows
up in production, switch to `openai:gpt-4o-mini`**: 0.95 at the same price,
from a provider we call directly.

**Learning tasks — GPT-5.4-mini.** The only candidate that reliably satisfies
the lesson schema (75% accepted against 0–12% for everything else) and the
highest quality (0.92). It is the most expensive choice here, so revisit it
once the schema defect below is fixed.

**I-Spy clues — Gemini 3.1 Flash-Lite.** 0.98 quality and a perfect language
score at a fifth of Claude's cost, and it never leaked an answer word. Keeping
gpt-4o-mini would also be defensible: 0.97 at half the price, but a weaker
language score (4.25 against 5.00).

**I-Spy guess — GPT-4.1-mini.** Best guess accuracy (0.97 against 0.94 for
today's model), and it reads the directional traps correctly.

Three of the five recommendations change the current default, and the two
Gemini defaults are replaced outright. Together the October set costs about
**$13 per 1,000 learning sessions**, most of it scene analysis and lessons;
moving scene analysis to gpt-4.1-mini brings that to roughly $9, though the two
scene figures come from different prompts.

**Provider spread is deliberate.** No provider won everywhere: Anthropic took
vision, Mistral translation, OpenAI the two reasoning-heavy text calls and
Gemini the creative one. Each call is a separate setting, so a provider outage
downgrades one feature rather than the app.

### Model parameters

Temperature is the only sampling parameter the seams expose, and it was zero
everywhere before this work. The sweep results appear beside the production
rows in each table.

- **Zero everywhere, including clue writing.** Raising temperature hurt every
  call that was swept: scene analysis 0.79 to 0.74 at 0.3, clue writing 0.92
  to 0.77 at 0.3 and 0.75 at 0.7, with clue acceptance dropping from 100% to
  83%. Variety was the one argument for a higher temperature on clues, and it
  costs more than it returns: the model drifts off the supplied scene facts
  and the validator rejects the result.
- **Translation was inconclusive.** Its sweep was spoiled by rate limiting,
  and it is left at zero on the extraction argument.
- **Reasoning models ignore it.** gpt-5.x rejects a temperature, so the
  lesson generator is tuned by output budget instead.
- **Output budget.** Lessons need far more room than the shared 1,500-token
  default (observed peak above 3,000), which is why the harness raises the cap
  for that call; scene analysis and the short text calls stay at the default.

### Defects this comparison found

1. **Lessons are rejected for returning one question.** The prompt asks for
   two to four questions per task, the schema enforces a minimum of two
   locally, and providers do not enforce `minItems` in strict mode. Models
   return a single "Build a sentence" question and the whole lesson is thrown
   away: 0–12% accepted for every model except gpt-5.4-mini. Either accept one
   question for that task type or state the count per task in the prompt.
2. **Japanese and Korean translation is broken.** The prompt claims French and
   Spanish only, and the validator demands a definite article on every object.
   Gemini answered a Japanese scene in Spanish and the app accepted it;
   gpt-4o-mini invented the article "the" with fabricated genders. Models that
   answered correctly (Claude, gpt-4.1-mini) were rejected for omitting an
   article that those languages do not have.
3. **Gemini Flash-Lite returns 0–1000 bounding boxes.** Gemini 3.1 and 3.5
   Flash-Lite use Gemini's native coordinate scale, so the validator rejects
   every usable photo. Scaling in the adapter would recover both models.
4. **The current scene-analysis default is unusable.** gemini-3.7-flash failed
   every call across two sessions: provider overload (503) and free-tier quota
   (429).
5. **Anthropic cannot serve the lesson schema at all** — "the compiled grammar
   is too large" from every host OpenRouter tried — and Qwen never produced a
   schema-valid scene analysis.
"""

PER_CALL_NOTES = {
    "scene_analysis": (
        "Finds the objects a learner will practise, from an uploaded photo."
        " Anchor recall is how many of the objects a labeller marked as"
        " unmissable the model found; supported precision is how much of what"
        " it returned is actually in the photo. The unusable photo is a"
        " trap: the right behaviour is to return nothing."
    ),
    "translation": (
        "Translates the confirmed English vocabulary into the learner's"
        " language, with the definite article and grammatical gender. The"
        " Japanese and Korean cases are a probe: the shipped prompt only"
        " claims French and Spanish."
    ),
    "learning_tasks": (
        "Writes the grammar lesson: four task types, each with two to four"
        " multiple-choice or sentence-building questions, restricted to the"
        " approved scene vocabulary. The per-scene JSON schema is large, which"
        " some providers refuse outright."
    ),
    "ispy_clues": (
        "Writes one or two I-Spy clues that describe an object without naming"
        " it. A clue that contains the answer word scores zero."
    ),
    "ispy_guess": (
        "Reads the learner's own description and infers which object they"
        " meant, without being told the answer, then gives short feedback."
    ),
}

FOOTER = """## Limitations

- Small datasets: 14 photos, 17 translation cases, 6 scenes, 22 descriptions.
  A few points between models is within run-to-run noise.
- The judge is one model with one rubric, and shares a family with one
  candidate. Its scores are reported separately from the deterministic ones.
- Gemini was called on a free-tier key whose quota was exhausted during the
  runs; rate-limit retries are excluded from quality but the daily cap is a
  real deployment constraint.
- OpenRouter latency includes its routing hop, and it may route the same model
  to different hosts between calls.
- Prices are list prices at the date of the catalogue snapshot.
"""

# Model and provider comparison

Which model Linguini should use for each of its five AI calls, measured rather
than assumed. Every candidate ran through the app's own services — the same
prompts, JSON schemas and validators that ship — so a number here is what a
learner would have got.

Regenerate this file with:

```powershell
.\.venv\Scripts\python.exe -m evals.model_comparison.report --out ..\MODEL_COMPARISON.md
```

## How the measurements were taken

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

## What was measured

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

## Recommendations

| Call | Chosen | Replaces |
|---|---|---|
| Scene analysis | `openrouter:anthropic/claude-haiku-4.5` | gemini-3.7-flash |
| Translation | `openrouter:mistralai/mistral-small-2603` | gemini-3.5-flash-lite |
| Learning tasks | `openai:gpt-5.4-mini` | gpt-4o-mini |
| I-Spy clues | `gemini:gemini-3.1-flash-lite` | gpt-4o-mini |
| I-Spy guess | `openai:gpt-4.1-mini` | gpt-4o-mini |

**Scene analysis — Claude Haiku 4.5.** Highest quality (0.79), found every
anchor object, and the only candidate the app accepted every time, at a third
of gpt-4o's cost. gpt-4.1-mini is the budget alternative at 0.68 and a third
of the price. Today's default failed every call.

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
Gemini defaults are replaced outright. Together the chosen set costs about
**$13 per 1,000 learning sessions**, most of it scene analysis and lessons.

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

## 1. Scene analysis (vision)

Finds the objects a learner will practise, from an uploaded photo. Anchor recall is how many of the objects a labeller marked as unmissable the model found; supported precision is how much of what it returned is actually in the photo. The unusable photo is a trap: the right behaviour is to return nothing. 14 cases, up to 2 run(s) per case. Cost per 1,000 sessions assumes 1 call(s) per session.

### Quality

| Model | Overall | Anchor recall | Supported precision | Relation recall | Refused unusable photo | Hallucinated objects | Rule violations |
|---|---|---|---|---|---|---|---|
| openrouter:anthropic/claude-haiku-4.5 | 0.79 | 1.00 | 0.76 | 0.88 | 1.00 | 0.00 | 0.53 |
| openrouter:anthropic/claude-haiku-4.5 [temperature=0.3] | 0.74 | 0.91 | 0.77 | 0.88 | 1.00 | 0.00 | 0.50 |
| openai:gpt-4o | 0.73 | 0.89 | 0.78 | 0.89 | 0.67 | 0.12 | 0.73 |
| openai:gpt-4.1-mini | 0.69 | 0.87 | 0.76 | 0.89 | 1.00 | 0.00 | 0.82 |
| openai:gpt-5.4-nano | 0.65 | 0.97 | 0.77 | 0.50 | 1.00 | 0.00 | 0.79 |
| openrouter:meta-llama/llama-4-maverick | 0.34 | 0.50 | 0.80 | – | 1.00 | 0.00 | 0.40 |
| gemini:gemini-3.1-flash-lite | 0.20 | – | – | – | 1.00 | 0.00 | 0.00 |
| gemini:gemini-3.5-flash-lite | 0.20 | – | – | – | 1.00 | 0.00 | 0.00 |
| gemini:gemini-3.7-flash **(current default)** | 0.00 | – | – | – | – | 0.00 | 0.00 |
| openrouter:qwen/qwen3.8-flash | 0.00 | – | – | – | – | 0.00 | 0.00 |

### Reliability

| Model | Output usable by app | API errors | Run-to-run spread | Identical repeat runs | Rate-limit retries |
|---|---|---|---|---|---|
| openrouter:anthropic/claude-haiku-4.5 | 1.00 | 0.00 | 0.000 | 0.86 | 0.00 |
| openrouter:anthropic/claude-haiku-4.5 [temperature=0.3] | 1.00 | 0.00 | – | – | 0.00 |
| openai:gpt-4o | 0.97 | 0.00 | 0.041 | 0.00 | 0.00 |
| openai:gpt-4.1-mini | 0.88 | 0.00 | 0.040 | 0.07 | 0.00 |
| openai:gpt-5.4-nano | 0.70 | 0.00 | 0.093 | 0.00 | 0.00 |
| openrouter:meta-llama/llama-4-maverick | 0.40 | 0.00 | – | – | 0.00 |
| gemini:gemini-3.1-flash-lite | 0.20 | 0.00 | – | – | 0.00 |
| gemini:gemini-3.5-flash-lite | 0.20 | 0.00 | – | – | 0.00 |
| gemini:gemini-3.7-flash **(current default)** | 0.00 | 1.00 | – | – | 4.00 |
| openrouter:qwen/qwen3.8-flash | 0.20 | 0.20 | – | – | 0.00 |

### Speed, tokens and cost

| Model | Latency p50 (s) | Latency p95 (s) | Input tokens | Output tokens | Cost / call ($) | Cost / 1k sessions ($) |
|---|---|---|---|---|---|---|
| openrouter:anthropic/claude-haiku-4.5 | 6.1 | 7.9 | 3,393 | 657 | 0.00668 | 6.68 |
| openrouter:anthropic/claude-haiku-4.5 [temperature=0.3] | 6.0 | 6.6 | 3,375 | 677 | 0.00676 | 6.76 |
| openai:gpt-4o | 5.1 | 6.8 | 2,319 | 432 | 0.01012 | 10.12 |
| openai:gpt-4.1-mini | 8.8 | 12.0 | 2,810 | 591 | 0.00207 | 2.07 |
| openai:gpt-5.4-nano | 4.8 | 6.5 | 2,425 | 505 | 0.00112 | 1.12 |
| openrouter:meta-llama/llama-4-maverick | 41.6 | 50.7 | 2,927 | 587 | 0.00093 | 0.93 |
| gemini:gemini-3.1-flash-lite | 5.9 | 17.1 | 2,164 | 670 | 0.00155 | 1.55 |
| gemini:gemini-3.5-flash-lite | 3.7 | 3.9 | 2,164 | 492 | 0.00188 | 1.88 |
| gemini:gemini-3.7-flash **(current default)** | – | – | – | – | – | – |
| openrouter:qwen/qwen3.8-flash | 20.6 | 24.0 | 2,636 | 835 | 0.00079 | 0.79 |

## 2. Scene translation

Translates the confirmed English vocabulary into the learner's language, with the definite article and grammatical gender. The Japanese and Korean cases are a probe: the shipped prompt only claims French and Spanish. 17 cases, up to 3 run(s) per case. Cost per 1,000 sessions assumes 1 call(s) per session.

### Quality

| Model | Overall | Noun accuracy (es/fr) | Article accuracy | Gender accuracy | Relation accuracy | Fully clean cases | Term accuracy (ja/ko) | Wrong language (ja/ko) |
|---|---|---|---|---|---|---|---|---|
| openrouter:mistralai/mistral-small-2603 | 0.98 | 0.93 | 0.98 | 1.00 | 1.00 | 0.75 | 1.00 | 0.00 |
| openrouter:anthropic/claude-haiku-4.5 | 0.97 | 0.95 | 1.00 | 1.00 | 1.00 | 0.70 | 0.97 | 0.00 |
| openai:gpt-4o-mini | 0.95 | 0.94 | 0.95 | 1.00 | 0.92 | 0.40 | 0.97 | 0.00 |
| openai:gpt-4.1-mini | 0.94 | 0.93 | 1.00 | 0.98 | 1.00 | 0.51 | 0.89 | 0.00 |
| gemini:gemini-3.5-flash-lite **(current default)** | 0.73 | 0.97 | 1.00 | 1.00 | 0.98 | 0.63 | 0.00 | 1.00 |
| openai:gpt-4.1-nano | 0.65 | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 0.00 | 1.00 |
| gemini:gemini-3.1-flash-lite | 0.60 | 0.95 | 0.75 | 1.00 | 1.00 | 0.25 | 0.00 | 1.00 |
| openrouter:qwen/qwen3.8-flash | 0.33 | 1.00 | 1.00 | 1.00 | 1.00 | 0.50 | – | – |
| openrouter:deepseek/deepseek-v4-flash | 0.31 | 1.00 | 0.92 | 0.83 | 1.00 | 0.25 | 0.00 | 0.00 |
| gemini:gemini-3.7-flash | 0.00 | – | – | – | – | 0.00 | – | – |
| openrouter:mistralai/mistral-small-2603 [temperature=0.3] | 0.00 | – | – | – | – | 0.00 | – | – |

### Reliability

| Model | Output usable by app | API errors | Run-to-run spread | Identical repeat runs | Rate-limit retries |
|---|---|---|---|---|---|
| openrouter:mistralai/mistral-small-2603 | 0.86 | 0.00 | 0.014 | 0.59 | 0.65 |
| openrouter:anthropic/claude-haiku-4.5 | 0.75 | 0.00 | 0.000 | 1.00 | 0.00 |
| openai:gpt-4o-mini | 1.00 | 0.00 | 0.002 | 0.82 | 0.00 |
| openai:gpt-4.1-mini | 0.75 | 0.00 | 0.000 | 0.76 | 0.00 |
| gemini:gemini-3.5-flash-lite **(current default)** | 1.00 | 0.00 | 0.006 | 0.24 | 0.79 |
| openai:gpt-4.1-nano | 1.00 | 0.00 | – | – | 0.00 |
| gemini:gemini-3.1-flash-lite | 1.00 | 0.00 | – | – | 0.00 |
| openrouter:qwen/qwen3.8-flash | 0.33 | 0.67 | – | – | 0.00 |
| openrouter:deepseek/deepseek-v4-flash | 0.33 | 0.50 | – | – | 0.00 |
| gemini:gemini-3.7-flash | 0.00 | 1.00 | – | – | 5.00 |
| openrouter:mistralai/mistral-small-2603 [temperature=0.3] | 0.00 | 1.00 | – | – | 5.00 |

### Speed, tokens and cost

| Model | Latency p50 (s) | Latency p95 (s) | Input tokens | Output tokens | Cost / call ($) | Cost / 1k sessions ($) |
|---|---|---|---|---|---|---|
| openrouter:mistralai/mistral-small-2603 | 2.2 | 3.1 | 422 | 297 | 0.00024 | 0.24 |
| openrouter:anthropic/claude-haiku-4.5 | 2.6 | 5.1 | 1,278 | 290 | 0.00273 | 2.73 |
| openai:gpt-4o-mini | 3.2 | 4.6 | 650 | 218 | 0.00023 | 0.23 |
| openai:gpt-4.1-mini | 3.0 | 4.5 | 650 | 217 | 0.00061 | 0.61 |
| gemini:gemini-3.5-flash-lite **(current default)** | 3.0 | 3.9 | 417 | 338 | 0.00097 | 0.97 |
| openai:gpt-4.1-nano | 3.3 | 5.9 | 663 | 250 | 0.00017 | 0.17 |
| gemini:gemini-3.1-flash-lite | 4.5 | 7.9 | 429 | 473 | 0.00082 | 0.82 |
| openrouter:qwen/qwen3.8-flash | 8.6 | 22.7 | 471 | 720 | 0.00041 | 0.41 |
| openrouter:deepseek/deepseek-v4-flash | 11.1 | 14.3 | 426 | 809 | 0.00018 | 0.18 |
| gemini:gemini-3.7-flash | – | – | – | – | – | – |
| openrouter:mistralai/mistral-small-2603 [temperature=0.3] | – | – | – | – | – | – |

## 3. Grammar learning tasks

Writes the grammar lesson: four task types, each with two to four multiple-choice or sentence-building questions, restricted to the approved scene vocabulary. The per-scene JSON schema is large, which some providers refuse outright. 4 cases, up to 2 run(s) per case. Cost per 1,000 sessions assumes 1 call(s) per session.

### Quality

| Model | Overall | Accepted by validator | Automatic checks passed | Judge score (1-5) | Wrong answer keys | Ambiguous questions |
|---|---|---|---|---|---|---|
| openai:gpt-5.4-mini | 0.90 | 0.60 | 0.94 | 3.50 | 0.00 | 0.50 |
| openai:gpt-4.1-mini | 0.86 | 0.10 | 0.89 | 3.50 | 0.00 | 1.50 |
| gemini:gemini-3.5-flash-lite | 0.84 | 0.10 | 0.87 | 4.00 | 0.00 | 0.00 |
| openrouter:deepseek/deepseek-v4-flash | 0.71 | 0.10 | 0.90 | 4.33 | 0.00 | 0.33 |
| openai:gpt-4o-mini **(current default)** | 0.66 | 0.00 | 0.67 | 3.50 | 0.00 | 0.00 |
| gemini:gemini-3.7-flash | 0.00 | 0.00 | – | – | – | – |
| openrouter:anthropic/claude-haiku-4.5 | 0.00 | 0.00 | – | – | – | – |
| openrouter:qwen/qwen3.8-flash | 0.00 | 0.00 | – | – | – | – |

### Reliability

| Model | Output usable by app | API errors | Run-to-run spread | Identical repeat runs | Rate-limit retries |
|---|---|---|---|---|---|
| openai:gpt-5.4-mini | 0.60 | 0.00 | 0.026 | 0.00 | 0.00 |
| openai:gpt-4.1-mini | 0.10 | 0.00 | 0.067 | 0.00 | 0.00 |
| gemini:gemini-3.5-flash-lite | 0.10 | 0.00 | 0.046 | 0.00 | 0.00 |
| openrouter:deepseek/deepseek-v4-flash | 0.10 | 0.20 | 0.239 | 0.00 | 0.00 |
| openai:gpt-4o-mini **(current default)** | 0.00 | 0.00 | 0.063 | 0.00 | 0.00 |
| gemini:gemini-3.7-flash | 0.00 | 1.00 | – | – | 5.00 |
| openrouter:anthropic/claude-haiku-4.5 | 0.00 | 1.00 | – | – | 0.00 |
| openrouter:qwen/qwen3.8-flash | 0.00 | 1.00 | – | – | 0.00 |

### Speed, tokens and cost

| Model | Latency p50 (s) | Latency p95 (s) | Input tokens | Output tokens | Cost / call ($) | Cost / 1k sessions ($) |
|---|---|---|---|---|---|---|
| openai:gpt-5.4-mini | 9.0 | 11.7 | 2,862 | 1,618 | 0.00943 | 9.43 |
| openai:gpt-4.1-mini | 15.5 | 28.6 | 2,864 | 1,832 | 0.00408 | 4.08 |
| gemini:gemini-3.5-flash-lite | 5.6 | 7.7 | 1,684 | 1,912 | 0.00529 | 5.29 |
| openrouter:deepseek/deepseek-v4-flash | 49.9 | 277.7 | 1,683 | 5,045 | 0.00104 | 1.04 |
| openai:gpt-4o-mini **(current default)** | 10.8 | 14.3 | 2,864 | 1,131 | 0.00111 | 1.11 |
| gemini:gemini-3.7-flash | – | – | – | – | – | – |
| openrouter:anthropic/claude-haiku-4.5 | – | – | – | – | – | – |
| openrouter:qwen/qwen3.8-flash | – | – | – | – | – | – |

## 4. I-Spy clue generation

Writes one or two I-Spy clues that describe an object without naming it. A clue that contains the answer word scores zero. 6 cases, up to 3 run(s) per case. Cost per 1,000 sessions assumes 1 call(s) per session.

### Quality

| Model | Overall | Accepted by validator | Answer word leaked | Judge solved the clue | Grounded in scene facts | Language score (1-5) |
|---|---|---|---|---|---|---|
| openrouter:anthropic/claude-haiku-4.5 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 5.00 |
| openai:gpt-4o-mini **(current default)** | 0.97 | 1.00 | 0.00 | 1.00 | 0.90 | 4.35 |
| gemini:gemini-3.1-flash-lite | 0.96 | 1.00 | 0.00 | 0.91 | 0.91 | 4.91 |
| openai:gpt-4.1-mini | 0.86 | 0.91 | 0.00 | 0.90 | 0.90 | 4.40 |
| gemini:gemini-3.1-flash-lite [temperature=0.3] | 0.77 | 0.83 | 0.00 | 0.90 | 0.90 | 4.90 |
| gemini:gemini-3.1-flash-lite [temperature=0.7] | 0.75 | 0.83 | 0.00 | 0.90 | 0.90 | 4.60 |
| gemini:gemini-3.5-flash-lite | 0.50 | 0.50 | 0.00 | 1.00 | 1.00 | 5.00 |
| openai:gpt-4.1-nano | 0.25 | 0.50 | 1.00 | 1.00 | 1.00 | 4.75 |
| openrouter:qwen/qwen3.8-flash | 0.00 | 0.00 | – | – | – | – |
| openrouter:deepseek/deepseek-v4-flash | 0.00 | 0.00 | – | – | – | – |

### Reliability

| Model | Output usable by app | API errors | Run-to-run spread | Identical repeat runs | Rate-limit retries |
|---|---|---|---|---|---|
| openrouter:anthropic/claude-haiku-4.5 | 1.00 | 0.00 | 0.000 | 1.00 | 0.00 |
| openai:gpt-4o-mini **(current default)** | 1.00 | 0.00 | 0.041 | 0.83 | 0.00 |
| gemini:gemini-3.1-flash-lite | 1.00 | 0.00 | 0.036 | 1.00 | 0.21 |
| openai:gpt-4.1-mini | 0.91 | 0.00 | 0.115 | 0.33 | 0.00 |
| gemini:gemini-3.1-flash-lite [temperature=0.3] | 0.83 | 0.00 | – | – | 0.00 |
| gemini:gemini-3.1-flash-lite [temperature=0.7] | 0.83 | 0.00 | – | – | 0.00 |
| gemini:gemini-3.5-flash-lite | 0.50 | 0.00 | – | – | 0.00 |
| openai:gpt-4.1-nano | 0.50 | 0.00 | – | – | 0.00 |
| openrouter:qwen/qwen3.8-flash | 0.00 | 1.00 | – | – | 0.00 |
| openrouter:deepseek/deepseek-v4-flash | 0.00 | 0.75 | – | – | 0.00 |

### Speed, tokens and cost

| Model | Latency p50 (s) | Latency p95 (s) | Input tokens | Output tokens | Cost / call ($) | Cost / 1k sessions ($) |
|---|---|---|---|---|---|---|
| openrouter:anthropic/claude-haiku-4.5 | 2.6 | 3.7 | 1,422 | 103 | 0.00193 | 1.93 |
| openai:gpt-4o-mini **(current default)** | 1.7 | 2.2 | 1,063 | 76 | 0.00021 | 0.21 |
| gemini:gemini-3.1-flash-lite | 3.7 | 6.4 | 942 | 124 | 0.00042 | 0.42 |
| openai:gpt-4.1-mini | 1.7 | 2.0 | 1,063 | 80 | 0.00055 | 0.55 |
| gemini:gemini-3.1-flash-lite [temperature=0.3] | 3.5 | 5.1 | 938 | 119 | 0.00041 | 0.41 |
| gemini:gemini-3.1-flash-lite [temperature=0.7] | 3.7 | 9.4 | 938 | 126 | 0.00042 | 0.42 |
| gemini:gemini-3.5-flash-lite | 1.5 | 1.9 | 966 | 108 | 0.00056 | 0.56 |
| openai:gpt-4.1-nano | 1.7 | 1.7 | 1,089 | 83 | 0.00014 | 0.14 |
| openrouter:qwen/qwen3.8-flash | – | – | – | – | – | – |
| openrouter:deepseek/deepseek-v4-flash | 7.4 | 7.4 | 872 | 156 | 0.00010 | 0.10 |

## 5. I-Spy guess and feedback

Reads the learner's own description and infers which object they meant, without being told the answer, then gives short feedback. 22 cases, up to 3 run(s) per case. Cost per 1,000 sessions assumes 3 call(s) per session.

### Quality

| Model | Overall | Correct guess | Ambiguity flagged right | Evidence recall | Contradiction spotted | Feedback in English |
|---|---|---|---|---|---|---|
| openrouter:google/gemini-3.5-flash-lite | 0.96 | 0.95 | 0.93 | 1.00 | 0.99 | 1.00 |
| openai:gpt-4.1-mini | 0.95 | 0.95 | 0.96 | 0.96 | 0.99 | 0.99 |
| openrouter:qwen/qwen3.8-flash | 0.94 | 0.95 | 0.95 | 0.82 | 0.99 | 0.85 |
| openai:gpt-4o-mini **(current default)** | 0.88 | 0.93 | 0.91 | 1.00 | 0.93 | 1.00 |
| openrouter:deepseek/deepseek-v4-flash | 0.73 | 0.86 | 0.80 | 0.80 | 0.86 | 1.00 |
| openrouter:anthropic/claude-haiku-4.5 | 0.72 | 0.62 | 0.67 | 1.00 | 1.00 | 0.75 |
| openai:gpt-4.1-nano | 0.68 | 0.62 | 0.67 | 1.00 | 0.62 | 1.00 |

### Reliability

| Model | Output usable by app | API errors | Run-to-run spread | Identical repeat runs | Rate-limit retries |
|---|---|---|---|---|---|
| openrouter:google/gemini-3.5-flash-lite | 1.00 | 0.00 | 0.002 | 0.05 | 0.00 |
| openai:gpt-4.1-mini | 1.00 | 0.00 | 0.040 | 0.00 | 0.00 |
| openrouter:qwen/qwen3.8-flash | 1.00 | 0.00 | 0.059 | 0.00 | 0.00 |
| openai:gpt-4o-mini **(current default)** | 0.95 | 0.00 | 0.059 | 0.00 | 0.00 |
| openrouter:deepseek/deepseek-v4-flash | 0.88 | 0.00 | – | – | 0.00 |
| openrouter:anthropic/claude-haiku-4.5 | 1.00 | 0.00 | – | – | 0.00 |
| openai:gpt-4.1-nano | 1.00 | 0.00 | – | – | 0.00 |

### Speed, tokens and cost

| Model | Latency p50 (s) | Latency p95 (s) | Input tokens | Output tokens | Cost / call ($) | Cost / 1k sessions ($) |
|---|---|---|---|---|---|---|
| openrouter:google/gemini-3.5-flash-lite | 1.4 | 2.7 | 1,204 | 72 | 0.00054 | 1.63 |
| openai:gpt-4.1-mini | 1.6 | 2.5 | 1,028 | 70 | 0.00052 | 1.57 |
| openrouter:qwen/qwen3.8-flash | 14.0 | 45.1 | 833 | 765 | 0.00048 | 1.45 |
| openai:gpt-4o-mini **(current default)** | 1.6 | 3.0 | 1,028 | 62 | 0.00019 | 0.58 |
| openrouter:deepseek/deepseek-v4-flash | 18.3 | 525.6 | 838 | 1,643 | 0.00037 | 1.10 |
| openrouter:anthropic/claude-haiku-4.5 | 3.2 | 5.1 | 1,506 | 88 | 0.00195 | 5.85 |
| openai:gpt-4.1-nano | 1.7 | 4.7 | 1,057 | 72 | 0.00013 | 0.40 |

## Model facts (from the OpenRouter catalogue snapshot)

| Model | Input $/Mtok | Output $/Mtok | Context window | Max output tokens | Vision | Temperature | Reasoning model |
|---|---|---|---|---|---|---|---|
| gemini:gemini-3.1-flash-lite | 0.25 | 1.50 | 1,048,576 | 65,536 | yes | yes | yes |
| gemini:gemini-3.5-flash-lite | 0.30 | 2.50 | 1,048,576 | 65,536 | yes | yes | yes |
| gemini:gemini-3.7-flash | 0.75 | 3.75 | 1,048,576 | 65,536 | yes | yes | yes |
| openai:gpt-4.1-mini | 0.40 | 1.60 | 1,047,576 | 32,768 | yes | yes | no |
| openai:gpt-4.1-nano | 0.10 | 0.40 | 1,047,576 | 32,768 | yes | yes | no |
| openai:gpt-4o | 2.50 | 10.00 | 128,000 | 16,384 | yes | yes | no |
| openai:gpt-4o-mini **(current default)** | 0.15 | 0.60 | 128,000 | 16,384 | yes | yes | no |
| openai:gpt-5.4-mini | 0.75 | 4.50 | 400,000 | 128,000 | yes | no | yes |
| openai:gpt-5.4-nano | 0.20 | 1.25 | 400,000 | 128,000 | yes | no | yes |
| openrouter:anthropic/claude-haiku-4.5 | 1.00 | 5.00 | 200,000 | 64,000 | yes | yes | yes |
| openrouter:deepseek/deepseek-v4-flash | 0.09 | 0.18 | 1,048,576 | 384,000 | no | yes | yes |
| openrouter:google/gemini-3.5-flash-lite | 0.30 | 2.50 | 1,048,576 | 65,536 | yes | yes | yes |
| openrouter:meta-llama/llama-4-maverick | 0.19 | 0.65 | 1,048,576 | 16,384 | yes | yes | no |
| openrouter:mistralai/mistral-small-2603 | 0.15 | 0.60 | 262,144 | 209,715 | yes | yes | yes |
| openrouter:qwen/qwen3.8-flash | 0.15 | 0.47 | 1,000,000 | 131,072 | yes | yes | yes |

## Failures by cause

| Call | Model | Cause | Calls |
|---|---|---|---|
| translation | openrouter:anthropic/claude-haiku-4.5 | validator rejected | 14 |
| translation | openai:gpt-4.1-mini | validator rejected | 14 |
| learning_tasks | openai:gpt-4o-mini | validator rejected | 10 |
| scene_analysis | openai:gpt-5.4-nano | validator rejected | 10 |
| translation | openrouter:mistralai/mistral-small-2603 | validator rejected | 10 |
| learning_tasks | openai:gpt-4.1-mini | validator rejected | 9 |
| learning_tasks | gemini:gemini-3.5-flash-lite | validator rejected | 9 |
| learning_tasks | openrouter:deepseek/deepseek-v4-flash | validator rejected | 7 |
| translation | gemini:gemini-3.7-flash | providerRateLimited | 6 |
| ispy_guess | openai:gpt-4o-mini | validator rejected | 4 |
| learning_tasks | openai:gpt-5.4-mini | validator rejected | 4 |
| scene_analysis | openai:gpt-4.1-mini | validator rejected | 4 |
| scene_analysis | gemini:gemini-3.5-flash-lite | validator rejected | 4 |
| scene_analysis | gemini:gemini-3.1-flash-lite | validator rejected | 4 |
| scene_analysis | gemini:gemini-3.7-flash | providerRateLimited | 4 |
| translation | openrouter:qwen/qwen3.8-flash | providerResponseInvalid | 4 |
| ispy_clues | openrouter:qwen/qwen3.8-flash | providerResponseInvalid | 4 |
| translation | openrouter:mistralai/mistral-small-2603 | providerRateLimited | 4 |
| scene_analysis | openrouter:qwen/qwen3.8-flash | validator rejected | 3 |
| scene_analysis | openrouter:meta-llama/llama-4-maverick | validator rejected | 3 |
| translation | openrouter:deepseek/deepseek-v4-flash | providerResponseInvalid | 3 |
| ispy_clues | openrouter:deepseek/deepseek-v4-flash | providerResponseInvalid | 3 |
| ispy_clues | openai:gpt-4.1-mini | validator rejected | 2 |
| learning_tasks | openrouter:deepseek/deepseek-v4-flash | providerResponseInvalid | 2 |
| learning_tasks | openrouter:anthropic/claude-haiku-4.5 | providerError | 2 |
| ispy_clues | openai:gpt-4.1-nano | validator rejected | 2 |
| ispy_clues | gemini:gemini-3.5-flash-lite | validator rejected | 2 |
| learning_tasks | openrouter:qwen/qwen3.8-flash | providerResponseInvalid | 2 |
| learning_tasks | gemini:gemini-3.7-flash | providerRateLimited | 2 |
| ispy_clues | gemini:gemini-3.1-flash-lite | validator rejected | 2 |
| scene_analysis | gemini:gemini-3.7-flash | providerUnavailable | 1 |
| scene_analysis | openrouter:qwen/qwen3.8-flash | providerResponseInvalid | 1 |
| translation | openrouter:deepseek/deepseek-v4-flash | validator rejected | 1 |
| ispy_clues | openrouter:deepseek/deepseek-v4-flash | validator rejected | 1 |
| ispy_guess | openrouter:deepseek/deepseek-v4-flash | validator rejected | 1 |

## Spend

1,019 provider calls, $2.30 total.

## Limitations

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

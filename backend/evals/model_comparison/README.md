# Model and provider comparison

Chooses a model for each of Linguini's five AI calls by measuring candidates
from three providers — OpenAI and Gemini directly, and third-party models
(Anthropic, Qwen, DeepSeek, Meta, Mistral) through OpenRouter — on the same
test cases, with the **production prompts, schemas and validators**.

| Call | Production adapter(s) | Cases |
|---|---|---|
| `scene_analysis` | `OpenAISceneAnalyzer`, `GeminiSceneAnalyzer` | Madrid's 14 labelled photos (`../scene_analysis`) |
| `translation` | `OpenAISceneTranslator`, `GeminiSceneTranslator` | 13 es/fr cases (`../scene_translation`) + 4 ja/ko probes (`cases/translation_cjk.json`) |
| `learning_tasks` | `OpenAILearningTaskGenerator`, `GeminiLearningTaskGenerator` | 4 es/fr scenes (`cases/scenes.json`) |
| `ispy_clues` | `OpenAIISpyClueGenerator`, `GeminiISpyClueGenerator` | 6 scenes in es, fr, ja, ko |
| `ispy_guess` | `OpenAIISpyGuessGenerator`, `GeminiISpyGuessGenerator` | 22 learner descriptions with known answers (`cases/ispy_guess.json`) |

## How a candidate is called

Each adapter already accepts `client=`. The harness injects a *recording*
client (`recording.py`) that forwards the adapter's exact request, then keeps
latency, token usage (including reasoning/thinking tokens), cost and the raw
output. OpenRouter models run through the OpenAI adapters with
`app.services.openrouter_client.OpenRouterClient`, the same client the app
uses when a call's provider is `openrouter`. `ok` in a result row means the
app would have accepted the output; quality is scored from the raw output so a
rejected answer can still be diagnosed.

## Stages

```powershell
.\.venv\Scripts\python.exe -m evals.model_comparison.run --stage screen --dry-run
.\.venv\Scripts\python.exe -m evals.model_comparison.run --stage screen
.\.venv\Scripts\python.exe -m evals.model_comparison.run --stage full --calls translation --models openai:gpt-4o-mini gemini:gemini-3.5-flash-lite
.\.venv\Scripts\python.exe -m evals.model_comparison.run --stage sweep --calls translation --models openai:gpt-4o-mini --grid temperature=0,0.7
.\.venv\Scripts\python.exe -m evals.model_comparison.rejudge results\full\*.jsonl
.\.venv\Scripts\python.exe -m evals.model_comparison.summarize --stage full
```

1. **screen** — every candidate, a hard subset of cases, one run.
2. **full** — the shortlist, every case, 2–3 runs (repeat runs measure consistency).
3. **sweep** — the winner per call against parameter settings
   (`temperature`, `max_output_tokens`, `reasoning_effort`, `thinking_budget`,
   `image_detail`, `media_resolution`). The first row is always production settings.

Every call is costed into `results/spend.json`; a job is skipped rather than
sent once spend plus its estimate would pass `--budget` (default $6.50). Only
our own account's rate limits (HTTP 429) are retried; provider overload (503)
is recorded as a failure because the app would fail the same way.

The judge for the two open-ended calls (lessons and clues) is
`anthropic/claude-sonnet-5`, which is not a candidate anywhere. It shares a
family with the `claude-haiku-4.5` candidate; the report flags that.

## Requirements

`OPENAI_API_KEY`, `GEMINI_API_KEY` and `OPENROUTER_API_KEY` in
`backend/.env.local`. Behind antivirus HTTPS inspection (for example Avast Web
Shield), `pip install truststore` so Python trusts the Windows certificate
store; the runner uses it when present. `matplotlib` is needed only to draw the
report charts.

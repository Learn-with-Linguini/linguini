# Scene translation evaluation dataset

Thirteen cases and 102 scored terms covering `scene_translation.txt`: English
scene vocabulary into French and Spanish, each object carrying a definite
article and a grammatical gender.

This prompt is unusually well suited to automated scoring. Whether *chaise* is
feminine is not a matter of taste, so almost everything here is checkable
without a judge.

## Running it

From `backend/`:

```bash
python -m evals.scene_translation.run_eval --provider openai --model gpt-4.1-mini
python -m evals.scene_translation.run_eval --provider gemini --model gemini-3.8-flash
python -m evals.scene_translation.run_eval --replay evals/scene_translation/results/raw/gpt-4.1-mini
python -m evals.scene_translation.run_eval --compare evals/scene_translation/results/*.json
```

Both adapters already exist in `app/services`, so a provider comparison needs
no new integration work. Set `OPENAI_API_KEY` or `GEMINI_API_KEY`.

## How it is scored

Reference data lives in `lexicon.py`, not in the cases, so a correction to
"shelf" is made once rather than in every case that mentions one.

Accuracy is split three ways, because the app breaks differently in each:

- **Noun accuracy** — is the word right at all?
- **Article accuracy** — the article is shown beside the noun on every card, so
  a wrong one is visible to the learner constantly.
- **Gender accuracy** — this drives the grammar tasks downstream.

Article and gender are always judged against **the reading the model chose**.
*el estante* and *la estantería* are both "shelf" and differ in gender; marking
the second wrong because the first is listed first would penalise a correct
translation. A word may have several readings and each carries its own grammar.

Two failures are counted separately from accuracy because a fluent-looking
response hides them:

- **Article glued onto the noun** — `"translation": "la tasse"` instead of
  `"translation": "tasse", "article": "la"`. It reads fine and breaks both the
  card layout and any later task needing the bare noun.
- **Structural failure** — a supplied term dropped, renamed, or given an
  article where the schema requires null. This is the production validator's
  verdict, not ours.

## The cases

Four shapes per language — a classroom scene, a grocery scene, multiword labels
and a minimal single-object case — plus three that exist to catch specific
errors:

- **`elision-fr`** — French elision in both directions. Seven words take `l'`
  before a vowel or mute h, but `bean` is **le haricot**: the h is aspirated
  and the article does not elide. A model that has generalised "vowel means
  `l'`" fails exactly one term here, which is the most common French article
  error there is.
- **`gender-trap-es`** — Spanish *agua* is feminine but takes **el** in the
  singular. Article and gender genuinely disagree, which is why the schema
  carries them as separate fields and why neither may be derived from the
  other.
- **`ambiguous-orange-fr`** — "orange" appears as both an object and an
  attribute in one payload. The fruit takes an article; the colour must come
  back with null article and null gender.

The classroom and grocery vocabulary is taken from the matching scene-analysis
cases, so both prompts are evaluated on the same words and a failure can be
traced to whichever stage introduced it.

## Adding to the lexicon

Only add entries you are confident about. A wrong gold answer is worse than a
missing one: it silently marks the correct model wrong, and nobody checks the
reference data when the numbers look plausible.

List every genuinely common translation as its own `Reading` with its own
article and gender. Keep the most ordinary beginner word first. Store bare
nouns — the tests reject a gold entry carrying its own article, since that is
the bug the eval exists to catch.

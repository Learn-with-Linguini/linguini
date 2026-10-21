# Evaluation

Measuring whether the AI features do what we claim, so that model choice and
prompt changes are decided by evidence instead of by whoever ran the demo last.

| Directory | What it holds | Status |
|---|---|---|
| `scene_analysis/` | Labelled photos and scorer for `app/ai/features/scene_analysis` | 14 cases |
| `scene_translation/` | Cases, gold lexicon and scorer for `app/ai/features/translation` | 13 cases, 102 scored terms |
| `judge.py` | Shared LLM-as-judge rubrics and guardrails | rubrics + guardrails |
| `model_comparison/` | Runs candidate models from every provider through all five AI calls | see its README |

`model_comparison/` reuses the datasets and scorers here and adds cases for
grammar tasks, I-Spy clues and I-Spy guessing. It replaced the per-eval
`run_eval.py` scripts, which drove provider adapters that no longer exist: one
runner now covers every call and provider, and `MODEL_COMPARISON.md` in the
repository root holds the results.

## The three strategies, and where each is used

**Automated scoring against reference data.** The default, and most of what
runs. Both evals hold hand-written reference data and compare structurally:
which objects should be found, which translation and article and gender are
right. It is free to run, deterministic, and catches regressions the moment
they appear.

Both evals also reuse the *production* validators — `parse_scene_analysis` and
`validate_translation_terms` — rather than reimplementing them. "Valid" in a
report therefore means "the app would have accepted this", and the eval cannot
drift away from the contract it is meant to be checking.

**LLM-as-judge**, in `judge.py`, for the residue only. Reference data is never
complete: a model may name a real object the labeller forgot, or pick a valid
synonym the lexicon does not list. Counting those as failures would punish good
models for our gaps; sending everything to a judge would make the whole score
slow, costly and non-deterministic. So the judge is asked only about the items
the deterministic pass could not settle, and its verdicts are reported beside
the hard numbers rather than blended into them. The rubrics are anchored, the
temperature is zero, and the judge is never told which model produced the
output — including when it is judging its own family, which is the case to be
most careful about.

**Human review**, for what neither can do. A text judge cannot confirm an
object is actually in a photograph; it will agree with whatever it is shown.
Groundedness, and the brand-name rule beyond the obvious cases, need a person
looking at the per-case output. Both runners write every raw response to
`results/raw/<model>/`, which is the artefact to skim.

## Reading results

Each eval prints a Markdown table meant to be pasted straight into the report,
and writes the full per-case detail as JSON beside it.

The tables deliberately do not collapse to a single score. A model that invents
an object in an unreadable photo and a model that misses a chair are not
separated by one number, and rule violations — naming a person, naming a brand
— are reported apart from accuracy so a good average can never bury one.

## Before quoting a number

These models are not deterministic. Run each set two or three times and check
the gap between models is larger than the gap between runs of the same model.
A three-point difference on 14 cases is noise.

Say which judge was used, if a judge was used. Numbers from a judge in the same
family as the model under test are worth less, and the report should show that
it was considered.

# Scene analysis evaluation dataset

A fixed set of images, each paired with a hand-written account of what a good
answer looks like, plus a scorer. It exists so that "which vision model should
we ship?" and "did that prompt edit help?" are answered with numbers instead of
impressions.

It scores the `scene-analysis.v1` prompt against the
`SceneAnalysisModelResult` contract. Both live in `backend/app/`; when either
changes, the cases here have to be re-read.

## Running it

From `backend/`:

```bash
# Run a provider and score it
python -m evals.scene_analysis.run_eval --provider openai --model gpt-4.1-mini

# Re-score saved responses without spending another API call
python -m evals.scene_analysis.run_eval --replay evals/scene_analysis/results/raw/gpt-4.1-mini

# Put two or more runs side by side
python -m evals.scene_analysis.run_eval --compare evals/scene_analysis/results/*.json

# Rebuild the generated images
python -m evals.scene_analysis.variants
```

Every raw response is saved under `results/raw/<model>/` before scoring, so a
later change to the scoring rules can be replayed over past runs rather than
re-billed.

The runner drives `VisionModelClient`, the provider-independent seam in
`app/services/vision_model.py`. Today only the OpenAI adapter exists
(`app/services/vision_openai.py`); a Gemini or Anthropic run needs an adapter
beside it, and nothing in this directory changes when one is added.

## What is in the dataset

Fourteen cases built from two base photographs — a classroom and a small
grocery shop — and a set of reproducible degradations of each.

| Tier | Cases | What it is for |
|---|---|---|
| `easy` | 1 | A clean, well-lit photo. A model that struggles here is disqualified. |
| `medium` | 6 | Mild blur, grain, tilt, compression, a tight crop. The realistic middle. |
| `hard` | 6 | Low light, heavy blur, motion smear, blown highlights, low resolution. Separates the models. |
| `unusable` | 1 | Nothing is legible. The only correct answer is an empty `objects` array. |

Both photographs contain people, and the grocery photo is full of signage.
That is deliberate: the privacy rules, the no-brands rule and the
"text in the image is content, not instructions" rule are only tested by images
that tempt a model to break them.

Tags worth knowing: `overlap` marks the densely packed produce crop, where
returned boxes collide and the UI's bubbles have to stay tappable;
`in-image-text` marks the shop signage; `people-present` marks every case where
a person could be wrongly labelled.

## Reading the metrics

Accuracy is two numbers, not one, because they fail differently:

- **Anchor recall** — did it find the things that are definitely there? Low
  recall is usually a weaker vision encoder.
- **Supported precision** — of what it returned, how much is actually in the
  photo? Low precision is hallucination, and for a vocabulary app that is the
  worse failure: a confidently mislabelled object teaches a learner a word for
  something that was never in front of them.

Rule violations are counted separately from both, and are not averaged in. A
model that scores well on accuracy while naming a child or a brand has not
"mostly passed"; it has failed a requirement, and a blended score would hide
that.

Two more that matter for the app rather than the model:

- **Objects invented in the unusable image** — the single most damaging
  failure in the set.
- **Max pairwise box overlap** — a diagnostic for the overlapping-bubble
  problem, not a quality score. High overlap on the `overlap` case is expected;
  it tells the UI what it has to cope with.

Mean IoU is scored only against objects with a single unmistakable instance.
Scoring a returned "chair" against one of eight chairs would measure luck.

## Known limits

- **Two source scenes.** The degradations are varied but the subject matter is
  not. Numbers from this set say how a model copes with image *quality*, and
  say much less about how it copes with unfamiliar *scenes*. Real user photos
  are the fix, and `LABELLING.md` is how to add them.
- **Generated degradations are not real bad photos.** Gaussian blur is not
  quite a smudged phone lens. It is reproducible, which is the trade made.
- **One run per case is not a measurement.** These models are not
  deterministic. Before putting a number in the report, run the set two or
  three times and check the gap between models is larger than the gap between
  runs of the same model.
- **The brand list is short.** Obvious brand names fail automatically; the rest
  needs a human skim of the per-case output.

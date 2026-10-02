# Adding a case

The dataset is only as good as the photos in it, and right now it has two
source scenes. Real user photos are the highest-value thing anyone can
contribute to it.

## 1. Add the image

Drop a `.jpg`, `.png` or `.webp` into `images/`. Keep the long edge around
1280px. Photograph ordinary rooms and streets rather than staged shots — the
point is to look like what a learner will actually take.

Do not add a photo of someone who has not agreed to it being committed to a
public repository. A scene with a stranger in the background is fine and useful
(it tests the privacy rule); a portrait of a friend is not.

## 2. Write the case file

Copy an existing file in `cases/` and edit it. The filename and `case_id` must
match.

```json
{
  "case_id": "kitchen-clean",
  "image": "images/kitchen-clean.jpg",
  "difficulty": "easy",
  "tags": ["indoor", "kitchen"],
  "notes": "Why this case exists and what it is meant to catch.",
  "expectation": {
    "mode": "objects",
    "scene_title_accept": ["kitchen", "home kitchen"],
    "anchors": [
      { "canonical": "kettle", "accept": ["electric kettle"] }
    ],
    "acceptable": [
      { "canonical": "mug", "accept": ["cup"] }
    ],
    "forbidden_labels": ["person", "man", "woman"],
    "min_objects": 3,
    "max_objects": 6
  }
}
```

### Choosing anchors

Anchors are objects a competent model **must** find; a miss is a real miss.

Keep the list to two or three. The prompt caps output at six objects, so a case
with five anchors punishes a model for obeying the prompt. Pick the things you
would be surprised to see missed: large, unobstructed, unmistakable.

For a badly degraded image it is fine to have **no** anchors. What is being
measured there is restraint — does it stay quiet instead of guessing — and
demanding specific objects under heavy blur measures the wrong thing.

### Choosing the acceptable pool

Everything else genuinely visible. Be generous: this is what separates "named
something really there" from "hallucinated". Anything returned that is in
neither list counts against precision, so a thin pool will unfairly punish a
model that simply noticed something you did not.

Include the dull structural things a model might reasonably return — `floor`,
`wall`, `ceiling`. They are poor vocabulary, but they are not hallucinations.

### Aliases

List the words that mean the same object for teaching purposes: `bin`,
`trash can`, `rubbish bin`. Matching is case-insensitive and handles plurals,
so do not list `chairs` alongside `chair`.

Two rules the tests enforce:

- **No alias may belong to two entries.** If `box` appears under both `crate`
  and `box`, one of them silently absorbs the other's answers.
- **No concept may appear twice.** Anchors are removed from the acceptable pool
  automatically; do not re-add them by hand.

When two concepts genuinely blur together in a photo — a plastic crate and a
cardboard box in a dim shop — make them one entry with a shared alias list
rather than two entries competing for the same words.

### Bounding boxes

Optional, and usually best left out. Add `box` **only** when the object has a
single unmistakable instance in the photo. A box on `chair` in a room with
eight chairs measures luck, not skill.

Coordinates are normalized with the top-left at `(0,0)`, and `x + width` and
`y + height` must not exceed 1.

### Relations

Add one only if it is unarguable. `subject` and `reference` are canonical
labels, not object keys — keys are assigned per response and mean nothing
across models.

### Degraded images

Set `max_confidence` so the case checks that the model's certainty drops with
the image quality. A model reporting 0.97 on a heavily blurred photo is
miscalibrated, and the app has no way to tell a good detection from a bad one.

Set `derived_from` when the image is a variant of another case's image.

For an image where nothing is legible, use `"mode": "empty"`, no anchors, and
no `scene_title_accept`. The only correct answer is an empty `objects` array.

## 3. Check it

```bash
python -m pytest tests/test_scene_analysis_evals.py -q
```

That verifies the image resolves, the aliases do not collide, the boxes are
inside the image, and the relations name objects you actually labelled.

Then look at one model's output on your case before trusting it:

```bash
python -m evals.scene_analysis.run_eval --only kitchen-clean --provider openai
```

If a sensible answer scores badly, the label is usually wrong, not the model.

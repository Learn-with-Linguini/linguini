import assert from "node:assert/strict";
import test from "node:test";

import { initiallyHiddenObjectIds, sceneReviewPanels } from "../src/lib/sceneReview.ts";

test("only mission-focused objects start in the learner review", () => {
  assert.deepEqual(initiallyHiddenObjectIds(["cup-1", "cup-2", "table"], ["cup-1", "cup-2"]), ["table"]);
  assert.deepEqual(initiallyHiddenObjectIds(["cup", "table"], []), []);
});

test("the review always exposes editable objects, adjectives and relationships", () => {
  assert.deepEqual(sceneReviewPanels(), ["objects", "attributes", "relations"]);
});

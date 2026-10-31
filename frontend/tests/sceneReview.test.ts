import assert from "node:assert/strict";
import test from "node:test";

import { initialReviewMarkers, initiallyHiddenObjectIds, sceneMarkerNumbers, sceneReviewPanels } from "../src/lib/sceneReview.ts";

test("only mission-focused objects start in the learner review", () => {
  assert.deepEqual(initiallyHiddenObjectIds(["cup-1", "cup-2", "table"], ["cup-1", "cup-2"]), ["table"]);
  assert.deepEqual(initiallyHiddenObjectIds(["cup", "table"], []), []);
});

test("the review always exposes editable objects, adjectives and relationships", () => {
  assert.deepEqual(sceneReviewPanels(), ["objects", "attributes", "relations"]);
});

test("review markers are contiguous within the visible suggestion subset", () => {
  assert.deepEqual(initialReviewMarkers(["hidden", "cup", "plate"], ["cup", "plate"]), {
    cup: 1,
    plate: 2,
  });
});

test("invalid or stale saved numbers do not take visible objects' fallback numbers", () => {
  assert.deepEqual(sceneMarkerNumbers(["cup", "plate", "table", "lamp"], {
    hidden: 1, cup: 0, plate: -1, table: 2.5, lamp: Number.NaN,
  }), { cup: 1, plate: 2, table: 3, lamp: 4 });
});

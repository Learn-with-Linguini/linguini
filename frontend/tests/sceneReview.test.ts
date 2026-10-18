import assert from "node:assert/strict";
import test from "node:test";

import { initiallyHiddenObjectIds, sceneReviewPanels } from "../src/lib/sceneReview.ts";

test("only mission-focused objects start in the learner review", () => {
  assert.deepEqual(initiallyHiddenObjectIds(["cup-1", "cup-2", "table"], ["cup-1", "cup-2"]), ["table"]);
  assert.deepEqual(initiallyHiddenObjectIds(["cup", "table"], []), []);
});

test("the review exposes only fact types required by candidate missions", () => {
  assert.deepEqual(sceneReviewPanels([{ missionId: "M03" }]), ["objects"]);
  assert.deepEqual(sceneReviewPanels([{ missionId: "M01" }, { missionId: "M02" }]), ["objects", "attributes", "relations"]);
  assert.deepEqual(sceneReviewPanels([{ missionId: "M01" }]), ["objects", "attributes"]);
  assert.deepEqual(sceneReviewPanels(undefined), ["objects", "attributes", "relations"]);
});

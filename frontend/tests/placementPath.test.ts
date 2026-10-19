import assert from "node:assert/strict";
import test from "node:test";

import { nextPlacementDifficulty } from "../src/lib/placementPath.ts";

test("the first response routes learners up or down from A1", () => {
  assert.equal(nextPlacementDifficulty(0, "A1", true), "A2");
  assert.equal(nextPlacementDifficulty(0, "A1", false), "A0");
});

test("later responses keep adapting around the learner's performance", () => {
  assert.equal(nextPlacementDifficulty(1, "A2", true), "A2");
  assert.equal(nextPlacementDifficulty(1, "A2", false), "A1");
  assert.equal(nextPlacementDifficulty(1, "A0", true), "A1");
  assert.equal(nextPlacementDifficulty(1, "A0", false), "A0");
});

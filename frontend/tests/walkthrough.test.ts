import assert from "node:assert/strict";
import test from "node:test";

import {
  FIRST_LESSON_WALKTHROUGH_VERSION,
  needsFirstLessonWalkthrough,
} from "../src/lib/walkthrough.ts";

test("the current walkthrough is shown only until its version is saved", () => {
  assert.equal(needsFirstLessonWalkthrough(undefined), true);
  assert.equal(needsFirstLessonWalkthrough(0), true);
  assert.equal(needsFirstLessonWalkthrough(FIRST_LESSON_WALKTHROUGH_VERSION), false);
  assert.equal(needsFirstLessonWalkthrough(FIRST_LESSON_WALKTHROUGH_VERSION + 1), false);
});

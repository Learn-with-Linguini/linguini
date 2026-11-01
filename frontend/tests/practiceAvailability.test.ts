import assert from "node:assert/strict";
import test from "node:test";
import { canStartNewPractice } from "../src/lib/practiceAvailability.ts";

test("a new practice remains available when only the resume lookup failed", () => {
  assert.equal(canStartNewPractice({
    hasActiveProfile: true,
    selected: false,
    starting: false,
    sessionLimitReached: false,
  }), true);
});

test("a known session limit still blocks a new practice", () => {
  assert.equal(canStartNewPractice({
    hasActiveProfile: true,
    selected: false,
    starting: false,
    sessionLimitReached: true,
  }), false);
});

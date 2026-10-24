import assert from "node:assert/strict";
import test from "node:test";
import { vocabularyRecapSteps } from "../src/lib/vocabularyRecap.ts";

test("recap mixes recognition and recall while covering every original index once", () => {
  const steps = vocabularyRecapSteps(3, 3);
  assert.deepEqual(steps.map(step => step.kind), ["quiz", "typing", "quiz", "typing", "quiz", "typing"]);
  assert.deepEqual(steps.filter(step => step.kind === "quiz").map(step => step.index), [0, 1, 2]);
  assert.deepEqual(steps.filter(step => step.kind === "typing").map(step => step.index), [1, 2, 0]);
});

test("recap preserves unmatched questions or words and supports empty or single-word sets", () => {
  assert.deepEqual(vocabularyRecapSteps(0, 0), []);
  assert.deepEqual(vocabularyRecapSteps(1, 1), [{ kind: "quiz", index: 0 }, { kind: "typing", index: 0 }]);
  for (const [questions, words] of [[3, 1], [1, 3], [0, 2], [2, 0]]) {
    const steps = vocabularyRecapSteps(questions, words);
    assert.equal(steps.length, questions + words);
    assert.equal(new Set(steps.map(step => `${step.kind}:${step.index}`)).size, steps.length);
  }
});

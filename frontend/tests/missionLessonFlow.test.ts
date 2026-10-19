import assert from "node:assert/strict";
import test from "node:test";
import type { LessonAnswerCheck } from "../src/lib/api.ts";
import { builtSentence } from "../src/lib/practiceTasks.ts";
import { mergeLessonChecks, visibleLessonQuestionIndex } from "../src/lib/missionLessonFlow.ts";

const checked = (questionId: string, answer: string): LessonAnswerCheck => ({
  questionId, answer, isCorrect: true, correctAnswer: answer,
  outcome: {
    questionId, outcome: "correct", objectiveId: null, targetIds: [],
    evidenceType: "construction", assistance: [], assistanceUsed: false, mistakes: [],
  },
});

test("lesson questions become visible one at a time in order", () => {
  const ids = ["q1", "q2", "q3"];
  assert.equal(visibleLessonQuestionIndex(ids, {}), 0);
  assert.equal(visibleLessonQuestionIndex(ids, { q1: checked("q1", "a") }), 1);
  assert.equal(visibleLessonQuestionIndex(ids, {
    q1: checked("q1", "a"), q2: checked("q2", "b"),
  }), 2);
  assert.equal(visibleLessonQuestionIndex(ids, {
    q1: checked("q1", "a"), q2: checked("q2", "b"), q3: checked("q3", "c"),
  }), 2);
});

test("restored lesson checks merge with newly locked local results", () => {
  const saved = [checked("q1", "saved"), checked("q2", "first")];
  const local = { q2: checked("q2", "locked"), q3: checked("q3", "new") };
  assert.deepEqual(mergeLessonChecks(saved, local), {
    q1: saved[0], q2: local.q2, q3: local.q3,
  });
});

test("sentence-builder chunks join punctuation and elided words", () => {
  assert.equal(
    builtSentence(["Il", "y", "a", "un", "livre", ",", "et", "c'est", "l'objet", "."]),
    "Il y a un livre, et c'est l'objet.",
  );
});

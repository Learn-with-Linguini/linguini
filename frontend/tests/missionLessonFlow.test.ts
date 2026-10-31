import assert from "node:assert/strict";
import test from "node:test";
import type { GrammarLessonQuestion, LessonAnswerCheck } from "../src/lib/api.ts";
import { builtSentence } from "../src/lib/practiceTasks.ts";
import { mergeLessonChecks, previousLessonContext, visibleLessonQuestionIndex } from "../src/lib/missionLessonFlow.ts";

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

const contextQuestions: GrammarLessonQuestion[] = [
  { questionId: "read", section: "Task 2 · Describe the scene", prompt: "Choose the matching description.",
    interactionType: "multipleChoice", tokenBank: [], options: [
      { optionId: "sentence-right", label: "Il y a une tasse rouge." },
      { optionId: "sentence-wrong", label: "Il y a une table rouge." },
    ] },
  { questionId: "build", section: "Task 2 · Describe the scene", prompt: "Describe the scene.",
    interactionType: "sentenceBuilding", options: [], tokenBank: ["La", "tasse", "est", "petite."] },
];

test("A2 sentence context resolves the checked correction and never displays an option identifier", () => {
  const wrong = { ...checked("read", "sentence-wrong"), isCorrect: false, correctAnswer: "sentence-right" };
  assert.equal(previousLessonContext(contextQuestions, 1, { read: wrong }, "A2")?.sentence, "Il y a une tasse rouge.");
  const unrecognized = { ...wrong, correctAnswer: "private-unresolved-key" };
  assert.equal(previousLessonContext(contextQuestions, 1, { read: unrecognized }, "A2")?.sentence, null);
});

test("context is limited to the finished predecessor in the same A2 construction section", () => {
  const checks = { read: checked("read", "sentence-right"), build: checked("build", "Current solution must stay hidden.") };
  assert.equal(previousLessonContext(contextQuestions, 0, checks, "A2"), null);
  assert.equal(previousLessonContext(contextQuestions, 1, {}, "A2"), null);
  assert.equal(previousLessonContext(contextQuestions, 1, checks, "A1"), null);
  assert.equal(previousLessonContext([{ ...contextQuestions[0], section: "Other activity" }, contextQuestions[1]], 1, checks, "A2"), null);
  assert.equal(previousLessonContext([{ ...contextQuestions[0], section: null }, { ...contextQuestions[1], section: null }], 1, checks, "A2"), null);
  assert.equal(previousLessonContext(contextQuestions, 1, { read: { ...checks.read, attemptsLeft: 1 } }, "A2"), null);
  assert.equal(previousLessonContext(contextQuestions, 1, checks, "A2")?.sentence, "Il y a une tasse rouge.");
});

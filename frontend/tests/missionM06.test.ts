import assert from "node:assert/strict";
import test from "node:test";
import type { GrammarLessonQuestion, LessonAnswerCheck } from "../src/lib/api";
import {
  isM06ScenarioVisible,
  lessonCheckFinished,
  nextAssistanceStep,
  retryTokens,
  unlockedRetryResumeIndex,
} from "../src/lib/missionM06.ts";
import { finishesAfterLearning } from "../src/lib/practiceTasks.ts";

test("the scenario banner only appears for an unaccepted M06 scenario", () => {
  assert.equal(isM06ScenarioVisible("M06", { accepted: false }), true);
  assert.equal(isM06ScenarioVisible("M06", { accepted: true }), false);
  assert.equal(isM06ScenarioVisible("M01", { accepted: false }), false);
});

test("retry removes only chunks identified as the wrong field", () => {
  assert.deepEqual(
    retryTokens(
      ["two", "small", "coffee", "please"],
      "quantity",
      { two: "quantity", small: "size" },
    ),
    ["small", "coffee", "please"],
  );
});

test("assistance follows the server-provided ladder order", () => {
  assert.equal(nextAssistanceStep(["phraseOnset", "chunkBank", "fullModel"], []), "phraseOnset");
  assert.equal(nextAssistanceStep(["phraseOnset", "chunkBank", "fullModel"], ["phraseOnset"]), "chunkBank");
  assert.equal(nextAssistanceStep(["phraseOnset"], ["phraseOnset"]), null);
});

test("an unlocked retry resumes on that question rather than the next one", () => {
  const questions = [{ questionId: "q1" }, { questionId: "q2" }] as unknown as GrammarLessonQuestion[];
  const checks = {
    q1: { questionId: "q1", answer: "x", isCorrect: false, correctAnswer: null, attemptsLeft: 2 },
  } as unknown as Record<string, LessonAnswerCheck>;
  assert.equal(unlockedRetryResumeIndex(questions, checks), 0);
});

test("a saved check finishes single-attempt questions when retry policy is omitted or null", () => {
  const wrong = { isCorrect: false };
  assert.equal(lessonCheckFinished(undefined), false);
  assert.equal(lessonCheckFinished(wrong), true);
  assert.equal(lessonCheckFinished(wrong, undefined), true);
  assert.equal(lessonCheckFinished(wrong, null), true);
  assert.equal(lessonCheckFinished(wrong, false), true);
});

test("explicit retries require a correct answer or exhausted server attempts", () => {
  assert.equal(lessonCheckFinished(undefined, true), false);
  assert.equal(lessonCheckFinished({ isCorrect: false, attemptsLeft: 2 }, true), false);
  assert.equal(lessonCheckFinished({ isCorrect: false, attemptsLeft: 0 }, true), true);
  assert.equal(lessonCheckFinished({ isCorrect: true, attemptsLeft: 2 }, true), true);
});

test("a correct first attempt resumes on the next question", () => {
  const questions = [{ questionId: "q1" }, { questionId: "q2" }] as unknown as GrammarLessonQuestion[];
  const checks = {
    q1: { questionId: "q1", answer: "x", isCorrect: true, correctAnswer: null, attemptsLeft: 2 },
  } as unknown as Record<string, LessonAnswerCheck>;
  assert.equal(unlockedRetryResumeIndex(questions, checks), 1);
});

test("M06 grammar tasks route to the learning summary", () => {
  const task = {
    id: "task-1",
    publicContent: { kind: "grammarLesson", missionId: "M06" },
  } as unknown as Parameters<typeof finishesAfterLearning>[0][number];
  assert.equal(finishesAfterLearning([task]), true);
});

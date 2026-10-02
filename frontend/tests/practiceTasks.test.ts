import assert from "node:assert/strict";
import test from "node:test";
import { practiceStages, taskDone, taskTitle, taskDescription } from "../src/lib/practiceTasks.ts";
import type { SessionTask, TaskContent } from "../src/lib/api.ts";

const contents: TaskContent[] = [
  { kind: "vocabularyIntroduction", title: "Learn a word", targetText: "mesa", translation: "table", partOfSpeech: "noun", exampleSentence: null },
  { kind: "grammarLesson", focus: "genderAgreement", title: "Gender", explanation: "Match the article.", questions: [{ questionId: "q1", prompt: "la ___", options: [{ optionId: "a", label: "mesa" }, { optionId: "b", label: "libro" }] }] },
  { kind: "grammarExplanation", title: "Grammar", explanation: "A noun", examples: ["mesa"] },
  { kind: "grammarPractice", prompt: "Choose", options: ["mesa", "silla"] },
  { kind: "syntaxExplanation", title: "Syntax", sentencePattern: "La mesa", explanation: "Read", examples: ["La mesa"] },
  { kind: "sentenceBuilding", prompt: "Build", sourceText: "The table", tokenBank: ["mesa", "La"] },
  { kind: "ispyRound", clue: "Find the table", options: [{ optionId: "table", label: "mesa", sceneObjectId: "object" }] },
  { kind: "reflection", prompt: "Reflect on your words" },
];
const tasks: SessionTask[] = contents.map((publicContent, orderIndex) => ({
  id: "task-" + orderIndex, kind: publicContent.kind, phase: publicContent.kind === "ispyRound" ? "ispy" : "learning",
  status: "pending", isSkippable: true, orderIndex, publicContent, vocabularyItemId: "word", sceneObjectId: "object",
}));

test("the original three screens expose all eight persisted tasks exactly once in order", () => {
  const stages = practiceStages([...tasks].reverse());
  assert.deepEqual(stages.learning.map(task => task.kind), contents.slice(0, 6).map(content => content.kind));
  assert.deepEqual(stages.clues.map(task => task.kind), ["ispyRound"]);
  assert.deepEqual(stages.reflection.map(task => task.kind), ["reflection"]);
  assert.deepEqual([...stages.learning, ...stages.clues, ...stages.reflection].map(task => task.id), tasks.map(task => task.id));
  assert.equal(stages.learning[0], tasks[0]);
});

test("skipped tasks unlock the next screen without being treated as completed tasks", () => {
  const learning = practiceStages(tasks).learning.map(task => ({ ...task, status: "skipped" as const }));
  assert.equal(learning.every(taskDone), true);
  assert.equal(learning.filter(task => task.status === "completed").length, 0);
  assert.equal([...learning, tasks[0]].every(taskDone), false);
});

test("task list copy comes from public content and all kinds have a label", () => {
  for (const task of tasks) {
    assert.ok(taskTitle(task));
    assert.ok(taskDescription(task));
  }
  assert.equal(taskDescription(tasks[0]), "mesa · table");
  assert.equal(taskTitle(tasks[2]), "Grammar");
});

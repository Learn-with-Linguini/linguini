import assert from "node:assert/strict";
import test from "node:test";
import { builtSentence, learningProgress, nextLearningStep, practiceStages, taskDone, taskTitle, taskDescription, taskXp, xpEarnedText } from "../src/lib/practiceTasks.ts";
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
  xpReward: 10, xpBonus: publicContent.kind === "ispyRound" ? 15 : 0,
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

test("home progress includes vocabulary and missions but excludes optional I-Spy and reflection", () => {
  const sessionTasks = tasks.map(task => ({ ...task }));
  sessionTasks[0].status = "skipped";
  sessionTasks[1].status = "completed";
  sessionTasks[6].status = "completed";
  sessionTasks[7].status = "completed";

  assert.deepEqual(learningProgress(sessionTasks), { completed: 2, total: 6 });
});

test("task list copy comes from public content and all kinds have a label", () => {
  for (const task of tasks) {
    assert.ok(taskTitle(task));
    assert.ok(taskDescription(task));
  }
  assert.equal(taskDescription(tasks[0]), "mesa · table");
  assert.equal(taskTitle(tasks[2]), "Grammar");
});

test("task reward metadata is presented without frontend reward constants", () => {
  assert.deepEqual(taskXp(tasks[0]), { xp: 10, bonus: 0 });
  assert.deepEqual(taskXp(tasks[6]), { xp: 10, bonus: 15 });
  assert.equal(taskXp({ ...tasks[0], xpReward: 0, xpBonus: 0 }), null);
});

test("earned Basil copy is shown only for positive action results", () => {
  assert.equal(xpEarnedText(25), "+25 Basil earned");
  assert.equal(xpEarnedText(0), null);
  assert.equal(xpEarnedText(undefined), null);
});

test("the last learning task only finishes a mission once every learning task is done", () => {
  const mission = tasks.slice(0, 3).map((task, index) => ({ ...task, publicContent: { ...task.publicContent, missionId: index ? "M01" : undefined } }) as SessionTask);
  const [vocabulary, first, last] = mission;
  assert.deepEqual(nextLearningStep(mission, first.id, false), { to: "task", taskId: last.id });
  // Missions can be opened from the list before the vocabulary task; finishing then would be rejected.
  assert.deepEqual(nextLearningStep(mission, last.id, false), { to: "tasks" });
  const learned = [{ ...vocabulary, status: "completed" }, { ...first, status: "skipped" }, last] as SessionTask[];
  assert.deepEqual(nextLearningStep(learned, last.id, false), { to: "finish" });
  assert.deepEqual(nextLearningStep(learned, last.id, true), { to: "tasks" });
  assert.deepEqual(nextLearningStep(mission, last.id, false, task => task === vocabulary || task === first), { to: "finish" });
  assert.deepEqual(nextLearningStep(tasks.map(task => ({ ...task, status: "completed" })), "task-5", false), { to: "ispy" });
  assert.deepEqual(nextLearningStep(mission, "missing", false), { to: "tasks" });
});

test("pack sentence joins preserve canonical Spanish punctuation and Unicode", () => {
  assert.equal(builtSentence(["El", "ni\u00f1o", "est\u00e1", "aqu\u00ed", "."], ["none", "space", "space", "space", "none"]), "El ni\u00f1o est\u00e1 aqu\u00ed.");
  assert.equal(builtSentence(["la", "la"], ["none", "space"]), "la la");
});

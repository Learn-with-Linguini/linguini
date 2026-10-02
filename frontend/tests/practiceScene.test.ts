import assert from "node:assert/strict";
import test from "node:test";
import { practiceScene } from "../src/lib/practiceScene.ts";
import { applyTaskResult } from "../src/lib/practiceUpdates.ts";
import type { PracticeDetail, TaskActionResult } from "../src/lib/api.ts";

const detail: PracticeDetail = {
  session: { id: "session", status: "inProgress", sceneMediaAssetId: "asset", sessionTitle: null, sessionSummary: null, failureCode: null },
  mediaAsset: { id: "asset", source: "userUpload" }, sceneId: null, title: "Uploaded photo", analysisMode: "placeholder",
  sceneObjectRelations: [],
  sceneObjects: [{ id: "object", sessionId: "session", label: "chair", attributes: null, confidenceScore: null, sourceObjectKey: null, vocabularyItemId: "word",
    boundingBox: { x: "0.15", y: "0.25", width: "0.20", height: "0.30" } }],
  vocabulary: [{ id: "word", displayText: "silla", partOfSpeech: "noun", gender: "la", exampleSentence: "La silla.", languageCode: "es" }],
  translations: [{ vocabularyItemId: "unrelated", translatedText: "wrong translation" }, { vocabularyItemId: "word", translatedText: "chair" }],
  tasks: [], nextTaskId: null, progress: { completedTaskCount: 0, skippedTaskCount: 0, totalTaskCount: 8, terminalTaskCount: 0 },
};
const imageUrl = "https://example.test/image?width=1280";

const saved: TaskActionResult = {
  task: { id: "task", kind: "reflection", phase: "learning", status: "completed", isSkippable: true,
    orderIndex: 7, publicContent: { kind: "reflection", prompt: "Reflect", suggestedVocabularyIds: [], allowSpeech: false },
    vocabularyItemId: "word", sceneObjectId: "object" },
  nextTaskId: null, sessionProgress: { ...detail.progress, completedTaskCount: 1, terminalTaskCount: 1 }, attempt: null,
};

test("a delayed task response cannot overwrite another session's progress", () => {
  const other = { ...detail, session: { ...detail.session, id: "other-session" }, nextTaskId: "other-task" };
  assert.equal(applyTaskResult(other, "session", saved), other);
  assert.equal(applyTaskResult(null, "session", saved), null);
});

test("a saved task updates its session's persisted task and progress", () => {
  const current: PracticeDetail = { ...detail, tasks: [{ ...saved.task, status: "pending" }], nextTaskId: "task" };
  const updated = applyTaskResult(current, "session", saved)!;
  assert.equal(updated.tasks[0].status, "completed");
  assert.equal(updated.nextTaskId, null);
  assert.equal(updated.progress.completedTaskCount, 1);
  assert.equal(current.tasks[0].status, "pending");
});

for (const source of ["preloaded", "camera", "userUpload"] as const) {
  test(`${source} uses the normalized scene contract and the supplied image URL`, () => {
    const scene = practiceScene({ ...detail, mediaAsset: { id: "asset", source }, sceneId: source === "preloaded" ? "bedroom" : null }, imageUrl, "Spanish");
    assert.equal(scene.sessionId, "session");
    assert.equal(scene.isUploaded, source !== "preloaded");
    assert.equal(scene.imageUrl, imageUrl);
    assert.equal(scene.items[0].word, "silla");
    assert.equal(scene.items[0].translation, "chair");
    assert.equal(scene.items[0].id, "object");
    assert.deepEqual([scene.items[0].x, scene.items[0].y], [25, 40]);
    assert.equal("rounds" in scene, false);
  });
}

test("a missing vocabulary join falls back to the object's label without inventing a translation", () => {
  const scene = practiceScene({ ...detail, vocabulary: [], translations: [] }, imageUrl, "Spanish");
  assert.equal(scene.items[0].word, "chair");
  assert.equal(scene.items[0].translation, "chair");
});


test("reviewed scenes contain confirmed objects and retain translations and marker positions", () => {
  const reviewed: PracticeDetail = { ...detail, sceneObjects: [
    { ...detail.sceneObjects[0], id: "kept" },
  ] };
  const scene = practiceScene(reviewed, imageUrl, "Spanish");
  assert.equal(scene.items.length, 1);
  assert.equal(scene.items[0].id, "kept");
  assert.equal(scene.items[0].translation, "chair");
  assert.equal(scene.items[0].word, "silla");
  assert.deepEqual([scene.items[0].x, scene.items[0].y], [25, 40]);
});


test("objects without a bounding box use a safe marker fallback", () => {
  const scene = practiceScene({ ...detail, sceneObjects: [{ ...detail.sceneObjects[0], boundingBox: null }] }, imageUrl, "Spanish");
  assert.deepEqual([scene.items[0].x, scene.items[0].y], [50, 50]);
});

import assert from "node:assert/strict";
import test from "node:test";
import { builtSentence, choiceOrder, markerChoices, optionText, questionOptions } from "../src/lib/practiceTasks.ts";
import { practiceScene } from "../src/lib/practiceScene.ts";
import type { GrammarLessonQuestion, PracticeDetail } from "../src/lib/api.ts";

const object = (id: string, label: string, x: string) => ({
  id, sessionId: "session", label, attributes: null, confidenceScore: null, sourceObjectKey: null, vocabularyItemId: null,
  boundingBox: { x, y: "0.4", width: "0.1", height: "0.1" },
});
const detail = {
  session: { id: "session", status: "inProgress", sceneMediaAssetId: "asset", sessionTitle: null, sessionSummary: null, failureCode: null },
  mediaAsset: { id: "asset", source: "userUpload" }, sceneId: null, title: "Desk", analysisMode: "placeholder",
  sceneObjectRelations: [],
  sceneObjects: [object("book", "book", "0.1"), object("table", "table", "0.4"), object("cup", "cup", "0.7")],
  vocabulary: [], translations: [], tasks: [], nextTaskId: null,
  progress: { completedTaskCount: 0, skippedTaskCount: 0, totalTaskCount: 4, terminalTaskCount: 0 },
} as unknown as PracticeDetail;
const scene = practiceScene(detail, "https://example.test/desk.jpg", "Spanish");

const findObject: GrammarLessonQuestion = {
  questionId: "find-object", prompt: "La taza está sobre la mesa.", interactionType: "multipleChoice", tokenBank: [],
  options: [{ optionId: "marker-1", label: "1" }, { optionId: "marker-2", label: "2" }, { optionId: "marker-3", label: "3" }],
  markerObjectIds: { "marker-1": "book", "marker-2": "table", "marker-3": "cup" }, keepOptionOrder: true,
};

test("marker badges show the review-screen numbers saved on the options", () => {
  const reviewed = { ...findObject, options: [{ optionId: "marker-2", label: "2" }, { optionId: "marker-5", label: "5" }],
    markerObjectIds: { "marker-2": "cup", "marker-5": "book" } };
  assert.deepEqual(markerChoices(reviewed, scene).map(({ item }) => [item.id, item.marker]), [["cup", 2], ["book", 5]]);
});

test("marker options use the reviewed photo's marker numbers", () => {
  const markers = markerChoices(findObject, scene);
  assert.deepEqual(markers.map(({ option, item }) => [option.optionId, item.id, item.marker]), [
    ["marker-1", "book", 1], ["marker-2", "table", 2], ["marker-3", "cup", 3],
  ]);
  assert.ok(markers.every(({ option, item }) => option.label === String(item.marker)));
  assert.equal(optionText(findObject, "3"), "Marker 3");
});

test("a saved marker answer restores to its object", () => {
  const saved = { "find-object": "marker-3" };
  const chosen = markerChoices(findObject, scene).find(({ option }) => option.optionId === saved["find-object"]);
  assert.equal(chosen?.item.id, "cup");
});

test("markers for objects no longer in the photo are not offered", () => {
  const stale = { ...findObject, markerObjectIds: { ...findObject.markerObjectIds, "marker-2": "removed" } };
  assert.deepEqual(markerChoices(stale, scene).map(({ option }) => option.optionId), ["marker-1", "marker-3"]);
  assert.equal(markerChoices({ ...findObject, markerObjectIds: null }, scene).length, 0);
});

test("yes/no statements keep the saved order and their full target-language answers", () => {
  const confirm: GrammarLessonQuestion = {
    questionId: "confirm-object", prompt: "¿Es un libro?", interactionType: "multipleChoice", tokenBank: [],
    options: [{ optionId: "confirm-2", label: "No, es una taza." }, { optionId: "confirm-1", label: "Sí, es un libro." }],
    keepOptionOrder: true,
  };
  assert.deepEqual(questionOptions(confirm, "task:confirm-object"), confirm.options);
  assert.equal(optionText(confirm, "Sí, es un libro."), "Sí, es un libro.");
  const shuffled = { ...confirm, keepOptionOrder: null };
  assert.deepEqual(questionOptions(shuffled, "task:confirm-object"),
    choiceOrder(confirm.options, "task:confirm-object", option => option.optionId));
});

test("word tiles build the sentence the backend grades", () => {
  assert.equal(builtSentence(["Es", "una", "taza", "roja", "."]), "Es una taza roja.");
  assert.equal(builtSentence(["C'", "est", "une", "tasse", "rouge", "."]), "C'est une tasse rouge.");
  assert.equal(builtSentence(["¿Dónde", "está", "la", "taza", "?"]), "¿Dónde está la taza?");
  assert.equal(builtSentence(["La", "tasse", "est", "à côté du", "livre", "."]), "La tasse est à côté du livre.");
  assert.equal(builtSentence([]), "");
});

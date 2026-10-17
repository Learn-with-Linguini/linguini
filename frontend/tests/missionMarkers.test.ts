import assert from "node:assert/strict";
import test from "node:test";
import type { LanguageItem } from "../src/data/types.ts";
import type { SceneObject } from "../src/lib/api.ts";
import { optionMarkerNumber, questionMarkerObjects } from "../src/lib/missionMarkers.ts";

function object(id: string): SceneObject {
  return {
    id,
    sessionId: "session",
    label: id,
    vocabularyItemId: null,
    boundingBox: null,
    anchorPoint: null,
    attributes: null,
    confidenceScore: null,
    sourceObjectKey: null,
  };
}

function item(id: string, marker: number): LanguageItem {
  return {
    id,
    word: id,
    translation: id,
    wordClass: "noun",
    gender: null,
    marker,
    x: 50,
    y: 50,
    example: id,
    exampleTranslation: id,
  };
}

test("question markers are sorted by number and include only current scene objects", () => {
  const sceneObjects = [object("cup"), object("book"), object("table"), object("chair")];
  const sceneItems = [item("table", 3), item("cup", 1), item("book", 2), item("chair", 4)];
  const result = questionMarkerObjects(
    { "marker-3": "table", "marker-1": "cup", "marker-2": "book" },
    null,
    sceneObjects,
    sceneItems,
  );
  assert.deepEqual(result.map(({ object: item, number }) => [item.id, number]), [
    ["cup", 1], ["book", 2], ["table", 3],
  ]);
});

test("a question with one scene object uses its reviewed marker", () => {
  const result = questionMarkerObjects(
    undefined,
    "cup",
    [object("cup"), object("book")],
    [item("cup", 4), item("book", 2)],
  );
  assert.deepEqual(result.map(({ object: target, number }) => [target.id, number]), [["cup", 4]]);
});

test("an answer option maps to its assigned scene marker number", () => {
  const options = { "marker-4": "cup", "marker-2": "book" };
  const sceneItems = [item("cup", 4), item("book", 2)];
  assert.equal(optionMarkerNumber("marker-4", options, sceneItems), 4);
  assert.equal(optionMarkerNumber("missing", options, sceneItems), null);
  assert.equal(optionMarkerNumber("marker-4", options, [item("cup", 0)]), null);
  assert.equal(optionMarkerNumber("marker-4", undefined, sceneItems), null);
});

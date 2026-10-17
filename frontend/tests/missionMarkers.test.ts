import assert from "node:assert/strict";
import test from "node:test";
import type { LanguageItem } from "../src/data/types.ts";
import type { SceneObject } from "../src/lib/api.ts";
import { questionMarkerObjects } from "../src/lib/missionMarkers.ts";

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

test("question markers use only its scene object and reviewed number", () => {
  const sceneObjects = [object("cup"), object("book"), object("table"), object("chair")];
  const sceneItems = [item("table", 3), item("cup", 1), item("book", 2), item("chair", 4)];
  const result = questionMarkerObjects(
    "table",
    sceneObjects,
    sceneItems,
  );
  assert.deepEqual(result.map(({ object: item, number }) => [item.id, number]), [
    ["table", 3],
  ]);
});

test("a question with one scene object uses its reviewed marker", () => {
  const result = questionMarkerObjects(
    "cup",
    [object("cup"), object("book")],
    [item("cup", 4), item("book", 2)],
  );
  assert.deepEqual(result.map(({ object: target, number }) => [target.id, number]), [["cup", 4]]);
});

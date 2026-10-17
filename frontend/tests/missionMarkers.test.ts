import assert from "node:assert/strict";
import test from "node:test";
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

test("question markers are sorted by number and include only current scene objects", () => {
  const sceneObjects = [object("cup"), object("book"), object("table")];
  const result = questionMarkerObjects(
    { table: 3, missing: 1, cup: 1, book: 2 },
    sceneObjects,
  );
  assert.deepEqual(result.map(({ object: item, number }) => [item.id, number]), [
    ["cup", 1], ["book", 2], ["table", 3],
  ]);
});

test("an answer option maps to its assigned scene marker number", () => {
  const options = { "marker-4": "cup", "marker-2": "book" };
  const markers = { cup: 4, book: 2 };
  assert.equal(optionMarkerNumber("marker-4", options, markers), 4);
  assert.equal(optionMarkerNumber("missing", options, markers), null);
  assert.equal(optionMarkerNumber("marker-4", options, { cup: 0 }), null);
  assert.equal(optionMarkerNumber("marker-4", undefined, markers), null);
});

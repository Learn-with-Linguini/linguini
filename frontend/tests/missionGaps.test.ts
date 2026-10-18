import assert from "node:assert/strict";
import test from "node:test";

import { fillMissionGap, serializeMissionChoices } from "../src/lib/missionGaps.ts";

test("gap completion preserves French elision and Korean spacing", () => {
  assert.equal(fillMissionGap("l'___ est ici.", "assiette"), "l'assiette est ici.");
  assert.equal(fillMissionGap("컵은 ___ 거예요.", "제"), "컵은 제 거예요.");
});

test("review choices serialize only selected, complete facts", () => {
  assert.equal(serializeMissionChoices({
    ownedObjectId: null, ownershipPretend: false, preferenceObjectIds: [],
    chosenObjectId: null, reaction: null,
  }), undefined);
  assert.deepEqual(serializeMissionChoices({
    ownedObjectId: "cup", ownershipPretend: true, preferenceObjectIds: ["book"],
    chosenObjectId: null, reaction: "dislike",
  }, new Set(["cup", "book"])), {
    ownership: { sceneObjectId: "cup", pretend: true },
    preference: { sceneObjectIds: ["book"], chosenObjectId: null, reaction: "dislike" },
  });
  assert.deepEqual(serializeMissionChoices({
    ownedObjectId: "removed", ownershipPretend: false, preferenceObjectIds: ["cup", "book"],
    chosenObjectId: "book", reaction: null,
  }, new Set(["cup", "book"])), {
    preference: { sceneObjectIds: ["cup", "book"], chosenObjectId: "book", reaction: "like" },
  });
});

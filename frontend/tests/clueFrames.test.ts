import assert from "node:assert/strict";
import test from "node:test";
import type { ClueFrame } from "../src/lib/api.ts";
import { applyFrame, fillSlot, mentionsTarget, savedAssistance } from "../src/lib/clueFrames.ts";

const frame = (frameId: ClueFrame["frameId"], prefix: string, chips: string[] = []): ClueFrame =>
  ({ frameId, prefix, meaning: "meaning", example: "example", chips });
const occurrences = (text: string, part: string) => text.split(part).length - 1;

test("Spanish frames build a complete clue with each prefix exactly once", () => {
  const name = frame("name", "Veo", ["una silla"]);
  const colour = frame("colour", "Es", ["roja", "azul"]);
  const location = frame("location", "Está", ["sobre la mesa"]);
  let clue = applyFrame("", name);
  assert.equal(clue, "Veo ");
  clue = fillSlot(clue, name, "una silla");
  clue = fillSlot(clue, colour, "azul");
  clue = fillSlot(clue, colour, "roja");
  clue = applyFrame(clue, colour);
  clue = fillSlot(clue, location, "sobre la mesa");
  assert.equal(clue, "Veo una silla. Es roja. Está sobre la mesa");
  assert.equal(occurrences(clue, "Es "), 1);
  assert.equal(occurrences(clue, "Está "), 1);
});

test("French frames keep apostrophe prefixes and free-typed text", () => {
  const colour = frame("colour", "C'est", ["rouge"]);
  const location = frame("location", "Elle est", ["sur la table", "à côté du livre"]);
  let clue = fillSlot("Elle est petite!", colour, "rouge");
  assert.equal(clue, "Elle est petite! C'est rouge");
  clue = fillSlot(clue, location, "sur la table");
  assert.equal(clue, "Elle est sur la table! C'est rouge");
  clue = fillSlot(`${clue}. Je vois`, location, "à côté du livre");
  assert.equal(occurrences(clue, "Elle est"), 1);
  assert.match(clue, /^Elle est à côté du livre! C'est rouge\. Je vois$/);
});

test("the target word is found whole, ignoring case and accents", () => {
  const avoid = ["taza", "tazas", "cup"];
  assert.equal(mentionsTarget("Veo una TÁZA roja", avoid), true);
  assert.equal(mentionsTarget("Son tazas.", avoid), true);
  assert.equal(mentionsTarget("a cup", avoid), true);
  assert.equal(mentionsTarget("Es un tazón", avoid), false);
  assert.equal(mentionsTarget("Veo una taza", []), false);
});

test("saved assistance is restored from the stored attempt payload", () => {
  assert.deepEqual(
    savedAssistance({ text: "Es roja", assistance: { selected_frame_ids: ["colour", "bogus"], inserted_chips: ["roja", 3] } }),
    { selectedFrameIds: ["colour"], insertedChips: ["roja"] },
  );
  assert.equal(savedAssistance({ text: "free typing" }), null);
  assert.equal(savedAssistance(undefined), null);
});

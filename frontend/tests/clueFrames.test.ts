import assert from "node:assert/strict";
import test from "node:test";
import type { ClueFrame } from "../src/lib/api.ts";
import { applyFrame, fillSlot, mentionsTarget, restoreSentences, savedAssistance, visibleFrames } from "../src/lib/clueFrames.ts";

const frame = (frameId: ClueFrame["frameId"], prefix: string, chips: string[] = []): ClueFrame =>
  ({ frameId, prefix, meaning: "meaning", example: "example", chips });
const occurrences = (text: string, part: string) => text.split(part).length - 1;

const empty = (text = "") => ({ text, sentences: {} });

test("Spanish frames build a complete clue with each prefix exactly once", () => {
  const colour = frame("colour", "Es", ["roja", "azul"]);
  const location = frame("location", "Está", ["sobre la mesa"]);
  let clue = applyFrame(empty(), colour);
  assert.equal(clue.text, "Es ");
  clue = fillSlot(clue, colour, "azul");
  clue = fillSlot(clue, colour, "roja");
  clue = applyFrame(clue, colour);
  clue = fillSlot(clue, location, "sobre la mesa");
  assert.equal(clue.text, "Es roja. Está sobre la mesa");
  assert.equal(occurrences(clue.text, "Es "), 1);
  assert.equal(occurrences(clue.text, "Está "), 1);
});

test("French Colour and Location share a prefix without overwriting each other", () => {
  const colour = frame("colour", "Elle est", ["rouge", "blanche"]);
  const location = frame("location", "Elle est", ["sur la table", "à côté du livre"]);
  let clue = fillSlot(empty(), colour, "rouge");
  assert.equal(clue.text, "Elle est rouge");
  clue = fillSlot(applyFrame(clue, location), location, "sur la table");
  assert.equal(clue.text, "Elle est rouge. Elle est sur la table");
  clue = fillSlot(clue, colour, "blanche");
  assert.equal(clue.text, "Elle est blanche. Elle est sur la table");
  clue = fillSlot(clue, location, "à côté du livre");
  assert.equal(clue.text, "Elle est blanche. Elle est à côté du livre");
});

test("editing one frame keeps the other frame, free-typed text and punctuation", () => {
  const colour = frame("colour", "Elle est", ["rouge", "blanche"]);
  const location = frame("location", "Elle est", ["sur la table"]);
  let clue = fillSlot(empty("Elle est petite!"), colour, "rouge");
  assert.equal(clue.text, "Elle est petite! Elle est rouge");
  clue = fillSlot(clue, location, "sur la table");
  clue = { ...clue, text: `${clue.text}?` };
  clue = fillSlot(clue, colour, "blanche");
  assert.equal(clue.text, "Elle est petite! Elle est blanche. Elle est sur la table?");
  // A sentence the learner rewrote is theirs; a new chip starts a fresh sentence instead.
  clue = { ...clue, text: clue.text.replace("Elle est blanche", "Elle est blanche et ronde") };
  clue = fillSlot(clue, colour, "rouge");
  assert.equal(clue.text, "Elle est petite! Elle est blanche et ronde. Elle est sur la table? Elle est rouge");
});

test("a restored clue finds each frame's sentence again", () => {
  const colour = frame("colour", "Elle est", ["rouge", "blanche"]);
  const location = frame("location", "Elle est", ["sur la table", "à côté du livre"]);
  const text = "Elle est rouge. Elle est sur la table";
  const sentences = restoreSentences(text, [colour, location], ["rouge", "sur la table"]);
  assert.deepEqual(sentences, { colour: "Elle est rouge", location: "Elle est sur la table" });
  assert.equal(fillSlot({ text, sentences }, location, "à côté du livre").text, "Elle est rouge. Elle est à côté du livre");
});

test("saved Name frames from older tasks are no longer shown", () => {
  const frames = [frame("name", "Veo", ["una mesa"]), frame("colour", "Es", ["roja"])];
  assert.deepEqual(visibleFrames(frames).map(item => item.frameId), ["colour"]);
  assert.deepEqual(visibleFrames(undefined), []);
});

test("the target word is found whole, ignoring case, accents and one-letter misspellings", () => {
  const avoid = ["taza", "tazas", "cup"];
  assert.equal(mentionsTarget("Veo una TÁZA roja", avoid), true);
  assert.equal(mentionsTarget("Son tazas.", avoid), true);
  assert.equal(mentionsTarget("a cup", avoid), true);
  assert.equal(mentionsTarget("Es un tazón", avoid), false);
  assert.equal(mentionsTarget("Está sobre la mesa", avoid), false, "other objects stay usable as references");
  assert.equal(mentionsTarget("Es una mesaa", ["mesa", "mesas"]), true);
  assert.equal(mentionsTarget("Es una mesaaa", ["mesa", "mesas"]), true);
  assert.equal(mentionsTarget("Es de este mes", ["mesa", "mesas"]), false);
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

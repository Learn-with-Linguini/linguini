import assert from "node:assert/strict";
import test from "node:test";
import type { ClueFrame } from "../src/lib/api.ts";
import { applyFrame, choicesFromSlots, fillSlot, mentionsTarget, nearTarget, restoreSentences, savedAssistance, slotSentence, slotsFromChoices, usesEnglish, visibleFrames, writeSentence } from "../src/lib/clueFrames.ts";

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
  assert.equal(mentionsTarget("Es una mesaa", ["mesa", "mesas"]), false, "similar spellings are not hard rejections");
  assert.equal(mentionsTarget("Es de la misa", ["mesa", "mesas"]), false);
  assert.equal(nearTarget("Es una mesaa", ["mesa", "mesas"]), true, "but they get a soft warning");
  assert.equal(nearTarget("Es una mesa", ["mesa", "mesas"]), false);
  assert.equal(nearTarget("Es de este mes", ["mesa", "mesas"]), false);
  assert.equal(mentionsTarget("Es de este mes", ["mesa", "mesas"]), false);
  assert.equal(mentionsTarget("Veo una taza", []), false);
});

test("English markers match whole words without blocking Spanish or French words", () => {
  assert.equal(usesEnglish("It is red"), true);
  assert.equal(usesEnglish("it's beside the object"), true);
  assert.equal(usesEnglish("Está next to la silla"), true);
  assert.equal(usesEnglish("Es roja"), false);
  assert.equal(usesEnglish("Il est sur la table"), false);
  assert.equal(usesEnglish("Está al lado de la puerta"), false);
  assert.equal(usesEnglish("on a de red color front top are rose orange marron beige violet"), false);
});

test("saved assistance is restored from the stored attempt payload", () => {
  assert.deepEqual(
    savedAssistance({ text: "Es roja", assistance: { selected_frame_ids: ["colour", "bogus"], inserted_chips: ["roja", 3] } }),
    { selectedFrameIds: ["colour"], insertedChips: ["roja"], selectedSlots: [], revealedHelpFrameIds: [] },
  );
  assert.deepEqual(
    savedAssistance({ text: "Está sobre la mesa", assistance: { selected_frame_ids: ["location"], inserted_chips: ["sobre", "la mesa"],
      selected_slots: [{ frame_id: "location", slot_id: "position", chip: "sobre" }, { frame_id: "location", slot_id: "bogus", chip: "x" }],
      revealed_help_frame_ids: ["location"] } }),
    { selectedFrameIds: ["location"], insertedChips: ["sobre", "la mesa"], selectedSlots: [{ frameId: "location", slotId: "position", chip: "sobre" }], revealedHelpFrameIds: ["location"] },
  );
  assert.equal(savedAssistance({ text: "free typing" }), null);
  assert.equal(savedAssistance(undefined), null);
});

const colourSlots: ClueFrame = { frameId: "colour", prefix: "Elle est", meaning: "m", example: "La pomme est rouge.", chips: [],
  template: "Elle est [colour]", slots: [{ slotId: "colour", label: "colour", chips: [{ text: "blanche" }, { text: "rouge" }] }], help: ["blanche"] };
const locationSlots: ClueFrame = { frameId: "location", prefix: "Elle est", meaning: "m", example: "Le livre est sur la table.", chips: [],
  template: "Elle est [position] [reference object]",
  slots: [{ slotId: "position", label: "position", chips: [{ text: "sur" }, { text: "à côté de" }] },
    { slotId: "reference", label: "reference object", chips: [{ text: "la table" }, { text: "le livre" }] }],
  phrases: { "sur|la table": "sur la table", "sur|le livre": "sur le livre", "à côté de|la table": "à côté de la table", "à côté de|le livre": "à côté du livre" },
  help: ["sur la table"] };

test("separate slots compose contractions and changing one slot keeps the other slots and sentences", () => {
  let c = applyFrame({ text: "", sentences: {} }, colourSlots);
  c = writeSentence(c, "colour", slotSentence(colourSlots, { colour: "rouge" }));
  c = applyFrame(c, locationSlots);
  c = writeSentence(c, "location", slotSentence(locationSlots, { position: "à côté de" }));
  assert.equal(c.text, "Elle est rouge. Elle est à côté de");
  c = writeSentence(c, "location", slotSentence(locationSlots, { position: "à côté de", reference: "le livre" }));
  assert.equal(c.text, "Elle est rouge. Elle est à côté du livre", "the server's composed phrase supplies the contraction");
  c = writeSentence(c, "location", slotSentence(locationSlots, { position: "sur", reference: "le livre" }));
  assert.equal(c.text, "Elle est rouge. Elle est sur le livre");
  c = writeSentence(c, "colour", slotSentence(colourSlots, { colour: "blanche" }));
  assert.equal(c.text, "Elle est blanche. Elle est sur le livre", "French Colour and Location share a prefix without overwriting");
});

test("slot picks and free edits survive a reload", () => {
  const picks = { colour: { colour: "blanche" }, location: { position: "sur", reference: "le livre" } } as const;
  const saved = slotsFromChoices(picks);
  assert.deepEqual(saved, [{ frameId: "colour", slotId: "colour", chip: "blanche" },
    { frameId: "location", slotId: "position", chip: "sur" }, { frameId: "location", slotId: "reference", chip: "le livre" }]);
  const choices = choicesFromSlots(saved);
  assert.deepEqual(choices, picks);
  assert.deepEqual(restoreSentences("Elle est blanche. Elle est sur le livre. Elle est petite.", [colourSlots, locationSlots], [], choices),
    { colour: "Elle est blanche", location: "Elle est sur le livre" });
  assert.deepEqual(restoreSentences("Elle est sur la table", [locationSlots], ["sur la table"]), { location: "Elle est sur la table" }, "revealed help phrases restore too");
  assert.deepEqual(slotsFromChoices({ location: undefined }), []);
});

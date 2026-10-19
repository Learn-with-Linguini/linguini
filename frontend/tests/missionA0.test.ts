import assert from "node:assert/strict";
import test from "node:test";
import { completeSlot, writtenPromptShown } from "../src/lib/missionA0.ts";

test("slot chunks complete with the chosen word", () => {
  assert.equal(completeSlot("___ tasse", "la"), "la tasse");
  assert.equal(completeSlot("___ arbre", "l'"), "l'arbre");
  assert.equal(completeSlot("책___", "이에요"), "책이에요");
  assert.equal(completeSlot("___ Tasse", "die"), "die Tasse");
});

test("listening prompts stay hidden until revealed, graded or audio is unavailable", () => {
  const listen = { listenFirst: true };
  assert.equal(writtenPromptShown(listen, { revealed: false, graded: false, audio: true }), false);
  assert.equal(writtenPromptShown(listen, { revealed: true, graded: false, audio: true }), true);
  assert.equal(writtenPromptShown(listen, { revealed: false, graded: true, audio: true }), true);
  assert.equal(writtenPromptShown(listen, { revealed: false, graded: false, audio: false }), true);
  assert.equal(writtenPromptShown({ listenFirst: null }, { revealed: false, graded: false, audio: true }), true);
});

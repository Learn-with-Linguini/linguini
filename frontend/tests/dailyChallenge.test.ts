import assert from "node:assert/strict";
import test from "node:test";
import { countdownText, lastResultText, scenePhotoPrompt, splitScenePhrase, timeLeft, wordShare } from "../src/lib/dailyChallenge.ts";

const words = [
  { label: "coffee", count: 50, foundByYou: true },
  { label: "cup", count: 48, foundByYou: false },
  { label: "window", count: 10, foundByYou: true },
];

test("daily challenge bars are sized against the most-found word", () => {
  assert.deepEqual(words.map(word => wordShare(word, words)), [100, 96, 20]);
});

test("the last challenge payout is described only when there is one", () => {
  assert.equal(lastResultText(null), null);
  assert.equal(
    lastResultText({ challengeDay: "2026-10-19", sceneTitle: "Café", rank: 3, participantCount: 41, basil: 20 }),
    "Café challenge: you placed #3 of 41 and earned 20 Basil.",
  );
});

test("the photo prompt names the day's scene", () => {
  assert.equal(scenePhotoPrompt("STePS"), "Snap a photo at STePS and complete the lesson.");
  assert.equal(scenePhotoPrompt("Café"), "Photograph a café and complete the lesson.");
  assert.equal(scenePhotoPrompt("Bus stop"), "Photograph a bus stop and complete the lesson.");
  assert.equal(scenePhotoPrompt("Office"), "Photograph an office and complete the lesson.");
});

test("the countdown reads in hours and minutes and turns urgent in the final hours", () => {
  const end = "2026-10-21T00:00:00Z";
  const at = (iso: string) => timeLeft(end, new Date(iso).getTime());
  assert.equal(countdownText(at("2026-10-20T05:18:00Z").remaining), "18h 42m left");
  assert.equal(countdownText(at("2026-10-20T22:55:00Z").remaining), "1h 05m left");
  assert.equal(countdownText(at("2026-10-20T23:18:00Z").remaining), "42m left");
  assert.equal(countdownText(at("2026-10-20T23:59:30Z").remaining), "Under a minute left");
  assert.equal(countdownText(at("2026-10-21T00:00:01Z").remaining), "Ended");
  assert.equal(at("2026-10-20T05:18:00Z").urgent, false);
  assert.equal(at("2026-10-20T21:00:00Z").urgent, true);
  assert.equal(at("2026-10-20T12:00:00Z").fraction, 0.5);
});

test("the scene phrase splits so only the place is emphasised", () => {
  assert.deepEqual(splitScenePhrase("at the library", "Library"), ["at the ", "library"]);
  assert.deepEqual(splitScenePhrase("at the bus stop", "Bus stop"), ["at the ", "bus stop"]);
  assert.deepEqual(splitScenePhrase("at your desk", "Desk"), ["at your ", "desk"]);
  assert.deepEqual(splitScenePhrase("somewhere", "Library"), ["somewhere", ""]);
});

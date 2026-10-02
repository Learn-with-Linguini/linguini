import assert from "node:assert/strict";
import test from "node:test";
import { queryError, queryKeys } from "../src/lib/queryKeys.ts";

test("profile-scoped keys carry the profile id and differ across profiles", () => {
  for (const key of [queryKeys.vocabulary, queryKeys.progress, queryKeys.journals, queryKeys.activeSession]) {
    assert.ok(key("profile-a").includes("profile-a"));
    assert.notDeepEqual(key("profile-a"), key("profile-b"));
  }
});

test("keys are stable and serialisable", () => {
  assert.deepEqual(queryKeys.account, ["account"]);
  assert.deepEqual(queryKeys.scenes, ["scenes"]);
  assert.deepEqual(queryKeys.journal("j1"), ["journal", "j1"]);
  assert.deepEqual(queryKeys.journalDayContext("2026-01-02"), ["journal", "day", "2026-01-02"]);
  assert.deepEqual(queryKeys.sessionScene("s1"), ["session", "s1", "scene"]);
  assert.deepEqual(queryKeys.sessionSummary("s1"), ["session", "s1", "summary"]);
  for (const key of [queryKeys.account, queryKeys.vocabulary("p"), queryKeys.activeSession("p"), queryKeys.sessionScene("s")]) {
    assert.deepEqual(JSON.parse(JSON.stringify(key)), [...key]);
  }
});

test("queryError hides technical failures behind actionable learner copy", () => {
  assert.equal(queryError(new Error("Request failed.")), "We couldn't connect just now. Check your connection and try again.");
  assert.equal(queryError({ status: 409, code: "active_session_limit_reached" }), "You can keep up to three unfinished practices open. Finish or leave one before starting another.");
  assert.equal(queryError({ status: 500 }), "Something went wrong on our side. Please try again in a moment.");
  assert.equal(queryError("oops"), "We couldn't load this right now. Please try again.");
  assert.equal(queryError(null), null);
  assert.equal(queryError(undefined), null);
});

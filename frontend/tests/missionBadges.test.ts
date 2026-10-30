import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { MISSION_BADGE_ASSETS, missionBadgeAsset } from "../src/lib/missionBadges.ts";
import { batchAccuracy, earnedBadgeLevels, type MissionBatch } from "../src/lib/gamification.ts";

test("every mission badge has a bundled image", () => {
  assert.deepEqual(Object.keys(MISSION_BADGE_ASSETS), Array.from({ length: 12 }, (_, index) => `M${String(index + 1).padStart(2, "0")}`));
  for (const asset of Object.values(MISSION_BADGE_ASSETS)) {
    assert.equal(existsSync(join(process.cwd(), "public", asset)), true, `${asset} should exist`);
  }
  assert.equal(missionBadgeAsset("M99"), null);
});

test("badge dots fill up to the earned level", () => {
  assert.equal(earnedBadgeLevels(null), 0);
  assert.equal(earnedBadgeLevels("Taster"), 1);
  assert.equal(earnedBadgeLevels("Cook"), 2);
  assert.equal(earnedBadgeLevels("Master"), 5);
});

test("batch accuracy is the share of assessed answers that were right", () => {
  const batch = (correctQuestions: number, assessedQuestions: number) => ({ correctQuestions, assessedQuestions }) as MissionBatch;
  assert.equal(batchAccuracy(batch(3, 6)), 50);
  assert.equal(batchAccuracy(batch(5, 6)), 83);
  assert.equal(batchAccuracy(batch(0, 0)), 0);
});

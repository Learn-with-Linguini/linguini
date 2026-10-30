import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { MISSION_BADGE_ASSETS, missionBadgeAsset } from "../src/lib/missionBadges.ts";

test("every mission badge has a bundled image", () => {
  assert.deepEqual(Object.keys(MISSION_BADGE_ASSETS), Array.from({ length: 12 }, (_, index) => `M${String(index + 1).padStart(2, "0")}`));
  for (const asset of Object.values(MISSION_BADGE_ASSETS)) {
    assert.equal(existsSync(join(process.cwd(), "public", asset)), true, `${asset} should exist`);
  }
  assert.equal(missionBadgeAsset("M13"), null);
});

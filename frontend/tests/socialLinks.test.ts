import assert from "node:assert/strict";
import test from "node:test";
import { SOCIAL_LINKS, SOCIAL_LINKS_LIST } from "../src/config/social.ts";

test("SOCIAL_LINKS contains all four verified platform accounts with valid URLs", () => {
  assert.equal(SOCIAL_LINKS.linkedin.url, "https://www.linkedin.com/in/learn-with-linguini");
  assert.equal(SOCIAL_LINKS.instagram.url, "https://www.instagram.com/learn_with_linguini/");
  assert.equal(SOCIAL_LINKS.x.url, "https://x.com/Linguini_App");
  assert.equal(SOCIAL_LINKS.tiktok.url, "https://www.tiktok.com/@learnwithlinguini");
});

test("SOCIAL_LINKS_LIST exposes platforms in consistent array form for rendering", () => {
  assert.equal(SOCIAL_LINKS_LIST.length, 4);
  const platforms = SOCIAL_LINKS_LIST.map(item => item.platform);
  assert.deepEqual(platforms, ["instagram", "tiktok", "x", "linkedin"]);
});

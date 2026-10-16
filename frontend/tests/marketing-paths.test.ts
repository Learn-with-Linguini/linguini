import assert from "node:assert/strict";
import test from "node:test";
import { isMarketingPath } from "../src/marketing/paths.ts";

test("recognizes marketing routes", () => {
  for (const path of ["/", "/blog", "/blog/x", "/learn/spanish", "/privacy", "/terms/", "/credits", "/share"]) {
    assert.equal(isMarketingPath(path), true, path);
  }
});

test("leaves learner and unknown routes outside the marketing app", () => {
  for (const path of ["/home", "/login", "/learn", "/practice/abc/learn", "/blog/a/b", "/contact"]) {
    assert.equal(isMarketingPath(path), false, path);
  }
});

import assert from "node:assert/strict";
import test from "node:test";

import { imageLoadingAttrs } from "../src/lib/imageLoading.ts";

test("lazy surfaces load lazily without a priority hint", () => {
  assert.deepEqual(imageLoadingAttrs(true), { loading: "lazy" });
});

test("unsized surfaces default to eager, high-priority loading", () => {
  assert.deepEqual(imageLoadingAttrs(undefined), { loading: "eager", fetchPriority: "high" });
  assert.deepEqual(imageLoadingAttrs(false), { loading: "eager", fetchPriority: "high" });
});

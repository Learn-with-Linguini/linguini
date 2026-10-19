import assert from "node:assert/strict";
import test from "node:test";

process.env.VITE_API_BASE_URL = "http://api.test";
const { mediaImageUrl, protectedMediaPath, shouldDownscale } = await import("../src/lib/api.ts");

test("mediaImageUrl builds the derivative endpoint on the configured API origin", () => {
  assert.equal(
    mediaImageUrl("asset-1", 640),
    "http://api.test/api/v1/media/asset-1/image?width=640",
  );
  assert.equal(
    mediaImageUrl("asset with space", 320),
    "http://api.test/api/v1/media/asset%20with%20space/image?width=320",
  );
  assert.equal(
    mediaImageUrl("asset-1", 1280),
    "http://api.test/api/v1/media/asset-1/image?width=1280",
  );
});

test("protectedMediaPath returns only paths on the configured API origin", () => {
  assert.equal(
    protectedMediaPath(mediaImageUrl("a", 640)),
    "/api/v1/media/a/image?width=640",
  );
  assert.equal(protectedMediaPath(null), null);
  assert.equal(protectedMediaPath("/scenes/x.jpg"), null);
  assert.equal(protectedMediaPath("https://evil.test/api/v1/media/a/image"), null);
});

test("shouldDownscale triggers on byte size or the long edge, never both needed", () => {
  assert.equal(shouldDownscale(600_001, 100, 100), true);
  assert.equal(shouldDownscale(600_000, 100, 100), false);
  assert.equal(shouldDownscale(100, 1601, 100), true);
  assert.equal(shouldDownscale(100, 1600, 1600), false);
  assert.equal(shouldDownscale(100, 100, 1601), true);
  assert.equal(shouldDownscale(0, 0, 0), false);
});

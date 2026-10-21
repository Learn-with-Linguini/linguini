import assert from "node:assert/strict";
import test from "node:test";
import { boardRows, squareCrop } from "../src/lib/practiceBoard.ts";

test("board rows fill up to ten tiles then carry the remainder", () => {
  assert.deepEqual(boardRows(12), [10, 2]);
  assert.deepEqual(boardRows(10), [10]);
  assert.deepEqual(boardRows(3), [3]);
  assert.deepEqual(boardRows(25), [10, 10, 5]);
  assert.deepEqual(boardRows(0), []);
  assert.deepEqual(boardRows(-2), []);
});

test("a square crop covers a bounding box's longer edge, centred", () => {
  const crop = squareCrop({ x: 0.2, y: 0.4, width: 0.4, height: 0.2 }, 1000, 500);
  assert.deepEqual(crop, { x: 200, y: 50, size: 400 });
});

test("a square crop is clamped inside the image", () => {
  const crop = squareCrop({ x: 0, y: 0, width: 0.4, height: 0.2 }, 1000, 500);
  assert.deepEqual(crop, { x: 0, y: 0, size: 400 });
  const edge = squareCrop({ x: 0.9, y: 0.9, width: 0.1, height: 0.1 }, 100, 100);
  assert.deepEqual(edge, { x: 90, y: 90, size: 10 });
});

test("a square crop never exceeds the image or a missing box", () => {
  assert.equal(squareCrop(null, 100, 100), null);
  assert.equal(squareCrop({ x: 0, y: 0, width: 0, height: 0.5 }, 100, 100), null);
  assert.deepEqual(squareCrop({ x: 0, y: 0, width: 2, height: 2 }, 100, 50), { x: 50, y: 0, size: 50 });
  assert.equal(squareCrop({ x: 0, y: 0, width: 0.5, height: 0.5 }, 0, 100), null);
});

import assert from "node:assert/strict";
import test from "node:test";
import { DIAGRAM_TARGETS, isDiagramPosition } from "../src/lib/positionDiagram.ts";

test("each M02 relation draws the target in its own place", () => {
  const places = Object.values(DIAGRAM_TARGETS).map(({ x, y, front }) => `${x}:${y}:${front}`);
  assert.equal(new Set(places).size, 5);
  assert.equal(DIAGRAM_TARGETS.behind.front, false);
  assert.ok(DIAGRAM_TARGETS.on.y < DIAGRAM_TARGETS.under.y);
});

test("only reviewed relation keys are drawn as diagrams", () => {
  assert.equal(isDiagramPosition("next_to"), true);
  assert.equal(isDiagramPosition("inside"), false);
  assert.equal(isDiagramPosition("phrase-1"), false);
});

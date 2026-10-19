import assert from "node:assert/strict";
import test from "node:test";
import {
  GA_MEASUREMENT_IDS,
  resolveGaMeasurementId,
  trackAction,
  trackPageView,
} from "../src/lib/analytics.ts";

test("resolveGaMeasurementId maps dev and prod hostnames accurately", () => {
  assert.equal(
    resolveGaMeasurementId("dev.learnwithlinguini.com"),
    GA_MEASUREMENT_IDS.dev,
  );
  assert.equal(
    resolveGaMeasurementId("www.learnwithlinguini.com"),
    GA_MEASUREMENT_IDS.prod,
  );
  assert.equal(
    resolveGaMeasurementId("learnwithlinguini.com"),
    GA_MEASUREMENT_IDS.prod,
  );
  assert.equal(resolveGaMeasurementId("other.domain.com"), null);
});

test("trackPageView pushes to Contentsquare _uxa queue and GA4 gtag", () => {
  // Mock window globals in test environment
  const mockUxa: unknown[][] = [];
  const mockGtagCalls: unknown[][] = [];

  (globalThis as unknown as { window: unknown }).window = globalThis;
  (globalThis as unknown as { _uxa: unknown[][] })._uxa = mockUxa;
  (globalThis as unknown as { gtag: (...args: unknown[]) => void }).gtag = (
    ...args: unknown[]
  ) => {
    mockGtagCalls.push(args);
  };

  trackPageView("/practice/sessions/123/learn", "Linguini - Practice");

  assert.equal(mockUxa.length, 1);
  assert.deepEqual(mockUxa[0], [
    "trackPageview",
    "/practice/sessions/123/learn",
  ]);

  assert.equal(mockGtagCalls.length, 1);
  assert.equal(mockGtagCalls[0][0], "event");
  assert.equal(mockGtagCalls[0][1], "page_view");
  assert.equal(
    (mockGtagCalls[0][2] as { page_path: string }).page_path,
    "/practice/sessions/123/learn",
  );
});

test("trackAction pushes custom events to Contentsquare and GA4", () => {
  const mockUxa: unknown[][] = [];
  const mockGtagCalls: unknown[][] = [];

  (globalThis as unknown as { window: unknown }).window = globalThis;
  (globalThis as unknown as { _uxa: unknown[][] })._uxa = mockUxa;
  (globalThis as unknown as { gtag: (...args: unknown[]) => void }).gtag = (
    ...args: unknown[]
  ) => {
    mockGtagCalls.push(args);
  };

  trackAction("task_answer_checked", { taskId: "task-1", isCorrect: true });

  assert.equal(mockUxa.length, 1);
  assert.deepEqual(mockUxa[0], [
    "trackCustomEvent",
    "task_answer_checked",
    { taskId: "task-1", isCorrect: true },
  ]);

  assert.equal(mockGtagCalls.length, 1);
  assert.equal(mockGtagCalls[0][0], "event");
  assert.equal(mockGtagCalls[0][1], "task_answer_checked");
  assert.deepEqual(mockGtagCalls[0][2], {
    taskId: "task-1",
    isCorrect: true,
  });
});

import assert from "node:assert/strict";
import test from "node:test";
import { keepClientProgress } from "../src/lib/practiceUpdates.ts";
import type { PracticeDetail, SessionStatus } from "../src/lib/api.ts";

function detail(status: SessionStatus, id = "s1"): PracticeDetail {
  return {
    session: { id, status, sceneMediaAssetId: "asset", sessionTitle: null, sessionSummary: null, failureCode: null },
    mediaAsset: { id: "asset", source: "preloaded" }, sceneId: null, title: "Scene", analysisMode: null,
    sceneObjects: [], sceneObjectRelations: [], vocabulary: [], translations: [],
    tasks: [], nextTaskId: null, progress: { completedTaskCount: 0, skippedTaskCount: 0, terminalTaskCount: 0, totalTaskCount: 0 },
  };
}

test("a lagging server status never regresses the client's generation progress", () => {
  for (const behind of ["created", "analyzingScene", "awaitingObjectReview"] as const) {
    const merged = keepClientProgress(detail("generatingTasks"), detail(behind));
    assert.equal(merged.session.status, "generatingTasks");
  }
});

test("statuses at or beyond the client's are written through", () => {
  for (const ahead of ["generatingTasks", "ready", "inProgress", "completed", "abandoned", "failed"] as const) {
    assert.equal(keepClientProgress(detail("generatingTasks"), detail(ahead)).session.status, ahead);
  }
  assert.equal(keepClientProgress(detail("analyzingScene"), detail("awaitingObjectReview")).session.status, "awaitingObjectReview");
  assert.equal(keepClientProgress(null, detail("awaitingObjectReview")).session.status, "awaitingObjectReview");
});

test("another session's detail is used as-is", () => {
  const incoming = detail("awaitingObjectReview", "s2");
  assert.equal(keepClientProgress(detail("generatingTasks"), incoming), incoming);
});

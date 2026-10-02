import assert from "node:assert/strict";
import test from "node:test";
import { isPreTaskStep, isSessionRouteAllowed, sessionDestination, sessionLoadingCopy } from "../src/lib/sessionRoute.ts";
import type { PracticeDetail, SessionStatus, SessionTask, TaskContent } from "../src/lib/api.ts";

const contents: Record<string, TaskContent> = {
  learn: { kind: "vocabularyIntroduction", title: "Learn a word", targetText: "mesa", translation: "table", partOfSpeech: "noun", exampleSentence: null },
  clues: { kind: "ispyRound", clue: "Find the table", options: [{ optionId: "table", label: "mesa", sceneObjectId: "object" }] },
  reflection: { kind: "reflection", prompt: "Reflect on your words" },
};

function task(kind: keyof typeof contents, status: SessionTask["status"], orderIndex: number): SessionTask {
  const publicContent = contents[kind];
  return { id: `${kind}-${orderIndex}`, kind: publicContent.kind, phase: kind === "clues" ? "ispy" : "learning",
    status, isSkippable: true, orderIndex, publicContent, vocabularyItemId: null, sceneObjectId: null };
}

function detail(status: SessionStatus, tasks: SessionTask[] = [], failureCode: PracticeDetail["session"]["failureCode"] = null): PracticeDetail {
  return {
    session: { id: "s1", status, sceneMediaAssetId: "asset", sessionTitle: null, sessionSummary: null, failureCode },
    mediaAsset: { id: "asset", source: "preloaded" }, sceneId: null, title: "Scene", analysisMode: null,
    sceneObjects: [], sceneObjectRelations: [], vocabulary: [], translations: [],
    tasks, nextTaskId: null, progress: { completedTaskCount: 0, skippedTaskCount: 0, terminalTaskCount: 0, totalTaskCount: tasks.length },
  };
}

test("every session status maps to its canonical route", () => {
  for (const status of ["created", "analyzingScene", "awaitingObjectReview", "generatingTasks"] as const) {
    assert.deepEqual(sessionDestination(detail(status)), { path: "/practice/sessions/s1/analysis", notice: null });
  }
  for (const status of ["ready"] as const) {
    assert.deepEqual(sessionDestination(detail(status)), { path: "/practice/sessions/s1/mic-test", notice: null });
  }
  assert.deepEqual(sessionDestination(detail("completed")), { path: "/practice/sessions/s1/summary", notice: null });
  assert.equal(sessionDestination(detail("abandoned")).path, "/practice");
  assert.match(sessionDestination(detail("abandoned")).notice ?? "", /discarded/);
  assert.equal(sessionDestination(detail("failed")).path, "/practice");
});

test("isPreTaskStep marks only the pre-task steps as auto-forwardable", () => {
  assert.equal(isPreTaskStep("/practice/sessions/s1/analysis"), true);
  assert.equal(isPreTaskStep("/practice/sessions/s1/mic-test"), true);
  for (const step of ["learn", "learn/learn-0", "ispy-1", "ispy-2", "summary"]) {
    assert.equal(isPreTaskStep(`/practice/sessions/s1/${step}`), false, step);
  }
  assert.equal(isPreTaskStep("/practice"), false);
});

test("generation stays on analysis until ready for the mic check", () => {
  const generating = detail("generatingTasks");
  assert.equal(isSessionRouteAllowed(generating, "/practice/sessions/s1/mic-test"), false);
  assert.equal(isSessionRouteAllowed(generating, "/practice/sessions/s1/analysis"), true);
  assert.equal(isSessionRouteAllowed(detail("ready"), "/practice/sessions/s1/analysis"), false);
  assert.equal(sessionDestination(detail("ready")).path, "/practice/sessions/s1/mic-test");
});

test("early vocabulary opens learning and never advances to I-Spy while generating", () => {
  for (const status of ["pending", "completed", "skipped"] as const) {
    const generating = detail("generatingTasks", [task("learn", status, 0)]);
    assert.equal(sessionDestination(generating).path, "/practice/sessions/s1/analysis");
    assert.equal(isSessionRouteAllowed(generating, "/practice/sessions/s1/learn/learn-0"), true);
    assert.equal(isSessionRouteAllowed(generating, "/practice/sessions/s1/ispy-1"), false);
  }
});

test("inProgress resumes at the first unfinished stage", () => {
  const pendingLearn = [task("learn", "pending", 0), task("clues", "pending", 1), task("reflection", "pending", 2)];
  assert.equal(sessionDestination(detail("inProgress", pendingLearn)).path, "/practice/sessions/s1/learn");
  const skippedLearn = [task("learn", "skipped", 0), task("learn", "completed", 1), task("clues", "pending", 2)];
  assert.equal(sessionDestination(detail("inProgress", skippedLearn)).path, "/practice/sessions/s1/ispy-1");
  const pendingReflection = [task("learn", "completed", 0), task("clues", "skipped", 1), task("reflection", "pending", 2)];
  assert.equal(sessionDestination(detail("inProgress", pendingReflection)).path, "/practice/sessions/s1/ispy-2");
  const allTerminal = [task("learn", "completed", 0), task("clues", "skipped", 1), task("reflection", "completed", 2)];
  assert.equal(sessionDestination(detail("inProgress", allTerminal)).path, "/practice/sessions/s1/ispy-2");
  assert.equal(sessionDestination(detail("inProgress", [])).path, "/practice/sessions/s1/learn");
});

test("sessions with no task rows resume at analysis", () => {
  assert.equal(sessionDestination(detail("created")).path, "/practice/sessions/s1/analysis");
  assert.equal(sessionDestination(detail("awaitingObjectReview")).path, "/practice/sessions/s1/analysis");
});

test("the route guard allows only the canonical destination", () => {
  assert.equal(isSessionRouteAllowed(detail("created"), "/practice/sessions/s1/learn"), false);
  assert.equal(isSessionRouteAllowed(detail("created"), "/practice/sessions/s1/analysis"), true);

  const pendingLearn = [task("learn", "pending", 0), task("clues", "pending", 1), task("reflection", "pending", 2)];
  assert.equal(isSessionRouteAllowed(detail("inProgress", pendingLearn), "/practice/sessions/s1/learn"), true);
  assert.equal(isSessionRouteAllowed(detail("inProgress", pendingLearn), "/practice/sessions/s1/learn/task-1"), true);
  assert.equal(isSessionRouteAllowed(detail("inProgress", pendingLearn), "/practice/sessions/s1/mic-test"), true);
  for (const step of ["summary", "ispy-1", "ispy-2", "analysis"]) {
    assert.equal(isSessionRouteAllowed(detail("inProgress", pendingLearn), `/practice/sessions/s1/${step}`), false);
  }

  const reflectionStage = [task("learn", "completed", 0), task("clues", "completed", 1), task("reflection", "pending", 2)];
  assert.equal(isSessionRouteAllowed(detail("inProgress", reflectionStage), "/practice/sessions/s1/ispy-2"), true);
  assert.equal(isSessionRouteAllowed(detail("inProgress", reflectionStage), "/practice/sessions/s1/learn"), false);
  assert.equal(isSessionRouteAllowed(detail("inProgress", reflectionStage), "/practice/sessions/s1/mic-test"), false);

  const clueStage = [task("learn", "completed", 0), task("clues", "pending", 1), task("reflection", "pending", 2)];
  assert.equal(isSessionRouteAllowed(detail("inProgress", clueStage), "/practice/sessions/s1/ispy-1"), true);
  assert.equal(isSessionRouteAllowed(detail("inProgress", clueStage), "/practice/sessions/s1/ispy-1/extra"), false);
  assert.equal(isSessionRouteAllowed(detail("inProgress", clueStage), "/practice/sessions/s1/mic-test"), false);

  assert.equal(isSessionRouteAllowed(detail("completed"), "/practice/sessions/s1/mic-test"), false);

  assert.equal(isSessionRouteAllowed(detail("ready"), "/practice/sessions/s1/mic-test"), true);
  assert.equal(isSessionRouteAllowed(detail("ready"), "/practice/sessions/s1/learn"), false);
  assert.equal(isSessionRouteAllowed(detail("ready"), "/practice/sessions/s1/ispy-1"), false);
  for (const status of ["abandoned", "failed"] as const) {
    for (const step of ["analysis", "mic-test", "learn", "ispy-1", "ispy-2", "summary"]) {
      assert.equal(isSessionRouteAllowed(detail(status), `/practice/sessions/s1/${step}`), false);
    }
  }
  assert.equal(isSessionRouteAllowed(detail("completed"), "/practice/sessions/s1/summary"), true);
  assert.equal(isSessionRouteAllowed(detail("completed"), "/practice/sessions/s1/learn"), false);
  assert.equal(isSessionRouteAllowed(detail("completed"), "/practice/sessions/s1/summary/extra"), false);
});

test("loading copy matches the destination segment", () => {
  const base = "/practice/sessions/s1";
  assert.deepEqual(sessionLoadingCopy(`${base}/analysis`), { title: "Scene analysis", heading: "Finding objects in your image...", scan: true });
  assert.deepEqual(sessionLoadingCopy(`${base}/mic-test`), { title: "Mic check", heading: "Getting your microphone ready...", scan: false });
  assert.deepEqual(sessionLoadingCopy(`${base}/learn`), { title: "Learning", heading: "Loading your words...", scan: false });
  assert.deepEqual(sessionLoadingCopy(`${base}/ispy-1`), { title: "I-Spy", heading: "Setting up your I-Spy clue...", scan: false });
  assert.deepEqual(sessionLoadingCopy(`${base}/ispy-2`), { title: "I-Spy", heading: "Setting up your turn to describe...", scan: false });
  assert.deepEqual(sessionLoadingCopy(`${base}/summary`), { title: "Practice summary", heading: "Gathering your results...", scan: false });
  assert.deepEqual(
    sessionLoadingCopy(`${base}/learn/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d`),
    { title: "Learning", heading: "Loading your words...", scan: false },
  );
  assert.deepEqual(sessionLoadingCopy(base), { title: "Practice", heading: "Loading your practice...", scan: false });
  assert.deepEqual(sessionLoadingCopy(`${base}/analysis`, "awaitingObjectReview"), { title: "Scene analysis", heading: "Finding objects in your image...", scan: true });
  assert.deepEqual(sessionLoadingCopy("/home"), { title: "Practice", heading: "Loading your practice...", scan: false });
  for (const path of [`${base}/mic-test`, `${base}/learn`, `${base}/ispy-1`, `${base}/ispy-2`, `${base}/summary`, base, "/home"]) {
    assert.equal(sessionLoadingCopy(path).scan, false);
  }
});

test("analysis loading copy switches to translating while tasks generate", () => {
  const base = "/practice/sessions/s1";
  assert.deepEqual(sessionLoadingCopy(`${base}/analysis`, "generatingTasks"), {
    title: "Scene analysis",
    heading: "Translating your scene...",
    support: "Turning your confirmed words into your learning language.",
    scan: true,
  });
  for (const step of ["mic-test", "learn", "ispy-1", "ispy-2", "summary"]) {
    assert.deepEqual(sessionLoadingCopy(`${base}/${step}`, "generatingTasks"), sessionLoadingCopy(`${base}/${step}`), step);
  }
});

test("failed sessions carry a notice per failure code", () => {
  for (const code of ["imageUploadFailed", "sceneAnalysisFailed", "imageModerationFailed", "noValidObjects", "vocabularyMappingFailed", "taskGenerationFailed"] as const) {
    const dest = sessionDestination(detail("failed", [], code));
    assert.equal(dest.path, "/practice");
    assert.ok(dest.notice?.length);
  }
  assert.ok(sessionDestination(detail("failed", [], null)).notice?.length);
});

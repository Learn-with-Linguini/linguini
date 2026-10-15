import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import test from "node:test";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { PracticeDetail, SessionTask } from "../src/lib/api.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
  pretendToBeVisual: true,
});
const globals = globalThis as Record<string, unknown>;
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (globals[key] !== undefined) continue;
  try {
    globals[key] = (dom.window as unknown as Record<string, unknown>)[key];
  } catch {
    // A few Node globals (navigator, performance) are read-only; skip them.
  }
}
Object.defineProperty(globalThis, "window", { value: dom.window, configurable: true });
Object.defineProperty(globalThis, "document", { value: dom.window.document, configurable: true });
globals.IS_REACT_ACT_ENVIRONMENT = true;

const SESSION_ID = "s1";
const BASE = `/practice/sessions/${SESSION_ID}`;

function task(kind: string, status: SessionTask["status"], orderIndex: number): SessionTask {
  const publicContent = { kind: "reflection" as const, prompt: "Reflect on your words" };
  return { id: `${kind}-${orderIndex}`, kind: publicContent.kind, phase: "ispy",
    status, isSkippable: true, orderIndex, publicContent, vocabularyItemId: null, sceneObjectId: null,
    xpReward: 0, xpBonus: 0 };
}

let fixture = detail("inProgress", [task("learn", "completed", 0), task("clues", "completed", 1), task("reflection", "completed", 2)]);

function detail(status: PracticeDetail["session"]["status"], tasks: SessionTask[] = []): PracticeDetail {
  return {
    session: { id: SESSION_ID, status, sceneMediaAssetId: "asset", sessionTitle: null, sessionSummary: null, failureCode: null },
    mediaAsset: { id: "asset", source: "preloaded" }, sceneId: null, title: "Scene", analysisMode: null,
    sceneObjects: [], sceneObjectRelations: [], vocabulary: [], translations: [],
    tasks, nextTaskId: null, progress: { completedTaskCount: 0, skippedTaskCount: 0, terminalTaskCount: 0, totalTaskCount: tasks.length },
  };
}

const apiFixtures: Record<string, unknown> = {
  "/api/v1/me": { id: "u1", createdAt: "2026-01-01", updatedAt: "2026-01-01", authProviderId: "test", displayName: "Learner", email: null, timezone: "UTC", onboardingCompleted: true, learningGoal: "practice", microphoneEnabled: true, cameraEnabled: true },
  "/api/v1/me/language-profiles": [{ id: "p1", userId: "u1", sourceLanguageCode: "en", targetLanguageCode: "es", proficiencyLevel: "A1", isActive: true, dailyGoalMinutes: 10, preferredInputMode: "both" }],
  "/api/v1/me/vocabulary": { items: [], nextCursor: null },
  "/api/v1/me/progress": { xp: 0, scenarios: [] },
  "/api/v1/preloaded-scenes": [],
  "/api/v1/journals": [],
};

let resolveComplete: ((response: Response) => void) | null = null;
const taskRequests: { path: string; body: Record<string, unknown> }[] = [];
const taskReplies: (() => Response)[] = [];
const latestReplies: (() => Response | Promise<Response>)[] = [];

globals.fetch = async (input: unknown, init?: RequestInit) => {
  const url = typeof input === "string" ? input : (input as Request).url;
  const path = url.replace(/^https?:\/\/[^/]+/, "");
  if (path.endsWith("/latest-attempt")) return latestReplies.shift()?.() ?? Response.json({ attempt: null });
  if (path.startsWith("/api/v1/tasks/")) {
    taskRequests.push({ path, body: JSON.parse(String(init?.body ?? "{}")) });
    return taskReplies.shift()?.() ?? new Response("no reply", { status: 500 });
  }
  if (path === `/api/v1/sessions/${SESSION_ID}/complete`) return new Promise<Response>(resolve => { resolveComplete = resolve; });
  if (path === `/api/v1/sessions/${SESSION_ID}`) return Response.json(fixture);
  if (path === "/api/v1/media/asset") {
    return Response.json({ id: "asset", signedUrl: "http://test.local/img.jpg", mimeType: "image/jpeg", width: 100, height: 100 });
  }
  if (path in apiFixtures) return Response.json(apiFixtures[path]);
  return new Response("not found", { status: 404 });
};

// .tsx sources can't run under node --experimental-strip-types, so the mounted
// surface is bundled once with rolldown (the vite bundler already in devDeps).
const here = dirname(fileURLToPath(import.meta.url));
const workdir = mkdtempSync(join(tmpdir(), "session-completion-"));
// The entry must live under frontend/ so bare imports resolve node_modules here.
const entryPath = join(here, ".sessionCompletion.entry.ts");
writeFileSync(entryPath, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter, Route, Routes } from "react-router-dom";',
  'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
  `export { SessionRoute } from "${pathToFileURL(join(here, "../src/components/SessionRoute")).href}";`,
  `export { ISpyPhase2 } from "${pathToFileURL(join(here, "../src/pages/ISpyPhase2")).href}";`,
  `export { AppStateProvider } from "${pathToFileURL(join(here, "../src/state/AppState")).href}";`,
  `export { useAppState } from "${pathToFileURL(join(here, "../src/state/useAppState")).href}";`,
].join("\n"));
let bundleCode: string;
try {
  const bundler = await rolldown({
    input: entryPath,
    platform: "node",
    resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{
      name: "api-base-url",
      transform: (code: string) => code.replaceAll("import.meta.env?.VITE_API_BASE_URL", '"http://test.local"'),
    }, {
      name: "stub-css",
      resolveId: (id: string) => (id.endsWith(".css") ? "\0empty-css" : null),
      load: (id: string) => (id === "\0empty-css" ? "export default {};" : null),
    }],
  });
  const { output } = await bundler.generate({ format: "esm" });
  await bundler.close();
  bundleCode = output[0].code;
} finally {
  rmSync(entryPath, { force: true });
}
const bundlePath = join(workdir, "bundle.mjs");
writeFileSync(bundlePath, bundleCode);
let bundled: unknown;
try {
  bundled = await import(pathToFileURL(bundlePath).href);
} finally {
  rmSync(workdir, { recursive: true, force: true });
}
const {
  h, act, createRoot, MemoryRouter, Route, Routes,
  QueryClient, QueryClientProvider, SessionRoute, ISpyPhase2, AppStateProvider, useAppState,
} = bundled as Record<string, never> as {
  h: typeof import("react").createElement;
  act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  Route: typeof import("react-router-dom").Route;
  Routes: typeof import("react-router-dom").Routes;
  QueryClient: typeof import("@tanstack/react-query").QueryClient;
  QueryClientProvider: typeof import("@tanstack/react-query").QueryClientProvider;
  SessionRoute: typeof import("../src/components/SessionRoute.tsx").SessionRoute;
  ISpyPhase2: typeof import("../src/pages/ISpyPhase2.tsx").ISpyPhase2;
  AppStateProvider: typeof import("../src/state/AppState.tsx").AppStateProvider;
  useAppState: typeof import("../src/state/useAppState").useAppState;
};

const controls: { completeSession: () => boolean } = {
  completeSession: () => { throw new Error("not mounted"); },
};

function Probe() {
  controls.completeSession = useAppState().completeSession;
  return null;
}

function stub(name: string) {
  return function StubPage() {
    return h("div", { "data-testid": `page-${name}` });
  };
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
const flush = () => act(async () => { await sleep(30); });
const shown = () => dom.window.document.querySelector("[data-testid]")?.getAttribute("data-testid");
let mountedRoot: ReturnType<typeof createRoot> | null = null;
const mountedClients: InstanceType<typeof QueryClient>[] = [];

test.after(async () => {
  for (const client of mountedClients) client.clear();
  dom.window.close();
  for (const handle of (process as unknown as { _getActiveHandles(): { unref?: () => void }[] })._getActiveHandles()) {
    handle.unref?.();
  }
});

test("finishing a session lands on /summary while the completion write is still in flight", async () => {
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  mountedRoot = root;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mountedClients.push(client);
  await act(async () => {
    root.render(
      h(QueryClientProvider, { client },
        h(AppStateProvider, null,
          h(MemoryRouter, { initialEntries: [`${BASE}/ispy-2`] },
            h(Probe),
            h(Routes, null,
              h(Route, { path: "/practice/sessions/:sessionId", element: h(SessionRoute) },
                h(Route, { path: "ispy-1", element: h(stub("ispy-1")) }),
                h(Route, { path: "ispy-2", element: h(ISpyPhase2) }),
                h(Route, { path: "summary", element: h(stub("summary")) }),
              ),
              h(Route, { path: "/practice", element: h(stub("practice")) }),
            ),
          ),
        ),
      ),
    );
  });
  await flush();
  const finish = [...dom.window.document.querySelectorAll("button")]
    .find(button => button.textContent?.includes("Finish session"));
  assert.ok(finish, "expected a Finish session button on the real ISpyPhase2 page");
  // The click fires completeSession() then navigate(); both run inside act so the
  // synchronous optimistic status reaches the route guard before /summary mounts.
  await act(async () => { finish.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
  await flush();
  assert.equal(shown(), "page-summary");
  await flush();
  assert.equal(shown(), "page-summary");
  // Settle the deferred write inside act so the post-mutation render is captured.
  await act(async () => { resolveComplete?.(Response.json({ id: SESSION_ID, status: "completed" })); await sleep(50); });
  await flush();
  assert.equal(shown(), "page-summary");
});

function described(attemptId: string, outcome: string, guessedObjectKey: string | null, status: SessionTask["status"] = "inProgress") {
  return () => Response.json({
    task: { ...guessTask, status }, nextTaskId: null,
    sessionProgress: { completedTaskCount: 2, skippedTaskCount: 0, terminalTaskCount: 2, totalTaskCount: 3 },
    xpEarned: 0,
    attempt: { id: attemptId, attemptNumber: 1, isCorrect: null, feedback: { message: `feedback ${attemptId}` },
      evaluationDetails: { version: "ispy-description-evaluation.v1", outcome, guessedObjectKey, ambiguous: false,
        alternativeObjectKeys: [], matchedEvidenceKeys: [], contradictedEvidenceKeys: [], targetAmongAlternatives: false } },
  });
}

const guessTask: SessionTask = { ...task("reflection", "inProgress", 2), sceneObjectId: "obj-target" };
const sceneObject = (id: string, label: string, x: number) => ({ id, sessionId: SESSION_ID, label, vocabularyItemId: null,
  boundingBox: null, anchorPoint: { x, y: 0.5 }, attributes: null, confidenceScore: null, sourceObjectKey: null });

const buttons = () => [...dom.window.document.querySelectorAll("button")];
const button = (label: string) => buttons().find(item => item.textContent?.trim() === label);
const click = (label: string) => act(async () => {
  const target = button(label);
  assert.ok(target, `expected a "${label}" button`);
  target.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await sleep(30);
});
const clue = () => dom.window.document.querySelector<HTMLInputElement>("#reflection")!;
const type = (value: string) => act(async () => {
  const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value")!.set!;
  setter.call(clue(), value);
  clue().dispatchEvent(new dom.window.Event("input", { bubbles: true }));
});

test("round two keeps the task active until the learner confirms the latest clear match", async () => {
  fixture = { ...detail("inProgress", [task("learn", "completed", 0), task("clues", "completed", 1), guessTask]),
    sceneObjects: [sceneObject("obj-target", "mesa", 0.3), sceneObject("obj-other", "silla", 0.7)] };
  const container = dom.window.document.createElement("div");
  dom.window.document.body.replaceChildren(container);
  const root = createRoot(container);
  // Zero gcTime so no garbage-collection timer keeps the test process alive.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  mountedClients.push(client);
  await act(async () => {
    root.render(h(QueryClientProvider, { client }, h(AppStateProvider, null,
      h(MemoryRouter, { initialEntries: [`${BASE}/ispy-2`] }, h(Routes, null,
        h(Route, { path: "/practice/sessions/:sessionId", element: h(SessionRoute) },
          h(Route, { path: "ispy-2", element: h(ISpyPhase2) }),
          h(Route, { path: "summary", element: h(stub("summary")) }),
        ),
      )),
    )));
  });
  await flush();
  await type("Es roja.");

  taskReplies.push(() => new Response("unavailable", { status: 503 }), described("a1", "evaluationFailed", null));
  await click("Send my response");
  await click("Send my response");
  const [lost, retried] = taskRequests.splice(0);
  assert.equal(retried.body.idempotencyKey, lost.body.idempotencyKey, "a network retry reuses its key");
  assert.equal(dom.window.document.querySelector("[data-testid=clue-frames]"), null, "tasks without frames keep free typing only");
  assert.equal(lost.body.assistance, undefined);
  assert.equal(lost.body.text, "Es roja.");
  assert.ok(button("Retry guessing"));
  assert.equal(button("That's it"), undefined);
  assert.equal(clue().value, "Es roja.");

  taskReplies.push(described("a2", "noMatch", "obj-other"));
  await click("Retry guessing");
  const [retry] = taskRequests.splice(0);
  assert.notEqual(retry.body.idempotencyKey, lost.body.idempotencyKey, "Retry guessing uses a new key");
  assert.match(dom.window.document.body.textContent ?? "", /Linguini guessed: silla/);
  assert.ok(dom.window.document.querySelector(".scene__marker--active"), "the assigned target stays marked");
  assert.ok(dom.window.document.querySelector(".scene__marker--guess"), "the guessed object is marked separately");
  assert.match(dom.window.document.querySelector("[data-testid=guess-legend]")?.textContent ?? "", /marker 1 .* marker 2/);
  assert.equal(button("That's it"), undefined);

  await click("Improve my clue");
  assert.equal(clue().disabled, false);
  await type("Es una mesa roja.");
  taskReplies.push(described("a3", "clearMatch", "obj-target"));
  await click("Send my response");
  const [revision] = taskRequests.splice(0);
  assert.notEqual(revision.body.idempotencyKey, retry.body.idempotencyKey, "a revised clue uses a new key");
  assert.equal(dom.window.document.querySelector(".scene__marker--guess"), null);
  assert.equal(button("Finish session"), undefined, "a clear match is not complete until confirmed");

  taskReplies.push(described("a3", "clearMatch", "obj-target", "completed"));
  await click("That's it");
  const [confirmation] = taskRequests.splice(0);
  assert.equal(confirmation.path, `/api/v1/tasks/${guessTask.id}/confirm-guess`);
  assert.deepEqual(confirmation.body, { attemptId: "a3" });
  assert.ok(button("Finish session"));
  root.unmount();
});

const frame = (frameId: string, prefix: string, example: string, chips: string[]) =>
  ({ frameId, prefix, meaning: `${frameId} meaning`, example, chips });
const framedTask: SessionTask = { ...guessTask, publicContent: { kind: "reflection", prompt: "Describe it",
  clueFrames: [
    frame("name", "Veo", "Veo una silla", ["una silla"]),
    frame("colour", "Es", "Es roja", ["roja"]),
    frame("location", "Está", "Está sobre la mesa", ["sobre la silla"]),
  ] as NonNullable<Extract<SessionTask["publicContent"], { kind: "reflection" }>["clueFrames"]>,
  avoidWords: ["mesa", "mesas", "table"] } };

function framedReply(attemptId: string, text: string, assistance: Record<string, unknown>) {
  return () => Response.json({
    task: framedTask, nextTaskId: null,
    sessionProgress: { completedTaskCount: 2, skippedTaskCount: 0, terminalTaskCount: 2, totalTaskCount: 3 },
    xpEarned: 0,
    attempt: { id: attemptId, attemptNumber: 1, isCorrect: null, feedback: { message: "Not quite." },
      responsePayload: { input_mode: "text", text, assistance },
      evaluationDetails: { version: "ispy-description-evaluation.v1", outcome: "noMatch", guessedObjectKey: "obj-other", ambiguous: false,
        alternativeObjectKeys: [], matchedEvidenceKeys: [], contradictedEvidenceKeys: [], targetAmongAlternatives: false } },
  });
}

test("guided frames compose an editable clue, block the target word and restore saved support", async () => {
  fixture = { ...detail("inProgress", [task("learn", "completed", 0), task("clues", "completed", 1), framedTask]),
    sceneObjects: [sceneObject("obj-target", "mesa", 0.3), sceneObject("obj-other", "silla", 0.7)] };
  const container = dom.window.document.createElement("div");
  dom.window.document.body.replaceChildren(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  mountedClients.push(client);
  await act(async () => {
    root.render(h(QueryClientProvider, { client }, h(AppStateProvider, null,
      h(MemoryRouter, { initialEntries: [`${BASE}/ispy-2`] }, h(Routes, null,
        h(Route, { path: "/practice/sessions/:sessionId", element: h(SessionRoute) },
          h(Route, { path: "ispy-2", element: h(ISpyPhase2) }),
        ),
      )),
    )));
  });
  await flush();
  const body = () => dom.window.document.body.textContent ?? "";
  const send = () => button("Send my response")!;

  await type("Es una Mesa roja");
  assert.ok(dom.window.document.querySelector("[data-testid=clue-warning]"), "the target word triggers a warning");
  assert.equal(send().disabled, true);
  await type("");
  assert.equal(dom.window.document.querySelector("[data-testid=clue-warning]"), null);

  assert.equal(button("Name"), undefined, "saved Name frames from older tasks are hidden");
  await click("Colour");
  assert.match(dom.window.document.querySelector("[data-testid=clue-frame]")?.textContent ?? "", /colour meaning.*Example: Es roja/);
  assert.equal(button("sobre la silla"), undefined, "chips belong to the selected frame");
  await click("roja");
  await click("Location");
  await click("sobre la silla");
  assert.equal(clue().value, "Es roja. Está sobre la silla");
  await type(`${clue().value} grande.`);

  taskReplies.push(framedReply("f1", "Es roja. Está sobre la silla grande.", { selected_frame_ids: ["colour"], inserted_chips: ["roja"] }));
  await click("Send my response");
  const [first] = taskRequests.splice(0);
  assert.equal(first.body.text, "Es roja. Está sobre la silla grande.", "the evaluator gets the displayed clue");
  assert.deepEqual(first.body.assistance, { version: "ispy-clue-assistance.v1", practiceMode: "guided", targetWordShown: true,
    offeredFrameIds: ["colour", "location"], selectedFrameIds: ["colour", "location"], insertedChips: ["roja", "sobre la silla"],
    selectedSlots: [], revealedHelpFrameIds: [] });
  assert.match(body(), /Linguini guessed: silla/);

  await click("Improve my clue");
  assert.equal(button("Colour")?.getAttribute("aria-pressed"), "true", "the saved frame is restored");
  assert.ok(button("roja")?.className.includes("chip--selected"));
  await type("Es roja y pequeña.");
  taskReplies.push(framedReply("f2", "Es roja y pequeña.", { selected_frame_ids: ["colour"], inserted_chips: ["roja"] }));
  await click("Send my response");
  const [revision] = taskRequests.splice(0);
  assert.notEqual(revision.body.idempotencyKey, first.body.idempotencyKey);
  assert.equal(revision.body.text, "Es roja y pequeña.");
  assert.deepEqual((revision.body.assistance as { selectedFrameIds: string[] }).selectedFrameIds, ["colour"]);
  root.unmount();
});

const evaluation = (outcome: string, guessed: string | null) => ({ version: "ispy-description-evaluation.v1", outcome, guessedObjectKey: guessed,
  ambiguous: false, alternativeObjectKeys: [], matchedEvidenceKeys: [], contradictedEvidenceKeys: [], targetAmongAlternatives: false });
const savedClue = (id: string, outcome: string | null, guessed: string | null, text = "Es roja. Está sobre la silla") => ({ attempt: {
  id, attemptNumber: 2, text, feedback: "Saved feedback.",
  evaluationDetails: outcome ? evaluation(outcome, guessed) : null,
  assistance: outcome ? { version: "ispy-clue-assistance.v1", practiceMode: "guided", targetWordShown: true,
    offeredFrameIds: ["colour", "location"], selectedFrameIds: ["colour", "location"], insertedChips: ["roja", "sobre la silla"] } : null,
} });

async function mountTask(status: SessionTask["status"]) {
  const restoredTask = { ...framedTask, status };
  fixture = { ...detail("inProgress", [task("learn", "completed", 0), task("clues", "completed", 1), restoredTask]),
    sceneObjects: [sceneObject("obj-target", "mesa", 0.3), sceneObject("obj-other", "silla", 0.7)] };
  const container = dom.window.document.createElement("div");
  dom.window.document.body.replaceChildren(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  mountedClients.push(client);
  await act(async () => {
    root.render(h(QueryClientProvider, { client }, h(AppStateProvider, null,
      h(MemoryRouter, { initialEntries: [`${BASE}/ispy-2`] }, h(Routes, null,
        h(Route, { path: "/practice/sessions/:sessionId", element: h(SessionRoute) },
          h(Route, { path: "ispy-2", element: h(ISpyPhase2) }),
          h(Route, { path: "summary", element: h(stub("summary")) }),
        ),
      )),
    )));
  });
  await flush();
  return { root, client, body: () => dom.window.document.body.textContent ?? "" };
}

test("a reload restores a pending clear match and confirms its saved attempt", async () => {
  let release: (response: Response) => void = () => {};
  latestReplies.push(() => new Promise<Response>(resolve => { release = resolve; }));
  const { root, body } = await mountTask("inProgress");
  assert.ok(dom.window.document.querySelector("[data-testid=restoring]"), "a loading state shows while the attempt loads");
  assert.equal(button("Send my response"), undefined);
  assert.equal(clue().disabled, true);

  await act(async () => { release(Response.json(savedClue("r1", "clearMatch", "obj-target"))); await sleep(30); });
  assert.equal(dom.window.document.querySelector("[data-testid=restoring]"), null);
  assert.equal(clue().value, "Es roja. Está sobre la silla");
  assert.match(body(), /Linguini guessed: mesa/);
  assert.equal(button("Location")?.getAttribute("aria-pressed"), "true", "the last saved frame is reopened");
  assert.ok(button("sobre la silla")?.className.includes("chip--selected"), "saved assistance is restored");

  taskReplies.push(described("r1", "clearMatch", "obj-target", "completed"));
  await click("That's it");
  const [confirmation] = taskRequests.splice(0);
  assert.deepEqual(confirmation.body, { attemptId: "r1" });
  assert.ok(button("Finish session"));
  root.unmount();
});

test("a reload restores unresolved and failed guesses with their controls, keeping unsent edits", async () => {
  latestReplies.push(() => Response.json(savedClue("r2", "noMatch", "obj-other")));
  const unresolved = await mountTask("inProgress");
  assert.match(unresolved.body(), /Linguini guessed: silla/);
  assert.equal(button("That's it"), undefined);
  await click("Improve my clue");
  await type("Es roja y grande.");
  latestReplies.push(() => Response.json(savedClue("r2", "noMatch", "obj-other", "Server copy")));
  await act(async () => { await unresolved.client.invalidateQueries(); await sleep(30); });
  assert.equal(clue().value, "Es roja y grande.", "a background refresh keeps unsent edits");
  unresolved.root.unmount();

  latestReplies.push(() => Response.json(savedClue("r3", "evaluationFailed", null)));
  const failed = await mountTask("inProgress");
  assert.ok(button("Retry guessing"));
  assert.equal(clue().value, "Es roja. Está sobre la silla");
  taskReplies.push(described("r4", "noMatch", "obj-other"));
  await click("Retry guessing");
  const [retry] = taskRequests.splice(0);
  assert.equal(retry.body.text, "Es roja. Está sobre la silla");
  failed.root.unmount();
});

test("a reload restores completed, skipped and legacy tasks without a fresh form", async () => {
  latestReplies.push(() => Response.json(savedClue("r5", "clearMatch", "obj-target")));
  const completed = await mountTask("completed");
  assert.match(completed.body(), /Linguini found your object!/);
  assert.ok(button("Finish session"));
  assert.equal(button("Send my response"), undefined);
  completed.root.unmount();

  latestReplies.push(() => Response.json(savedClue("r6", "noMatch", "obj-other")));
  const skipped = await mountTask("skipped");
  assert.match(skipped.body(), /Skipped — no XP earned\./);
  assert.equal(button("Send my response"), undefined);
  skipped.root.unmount();

  latestReplies.push(() => Response.json(savedClue("r7", null, null, "Old reflection")));
  const legacy = await mountTask("completed");
  assert.equal(clue().value, "Old reflection");
  assert.match(legacy.body(), /Saved feedback\./);
  assert.doesNotMatch(legacy.body(), /Linguini found your object/);
  legacy.root.unmount();
});

test("a failed restore never looks like a fresh unanswered task", async () => {
  latestReplies.push(() => new Response("down", { status: 500 }));
  const { root } = await mountTask("inProgress");
  assert.ok(dom.window.document.querySelector("[data-testid=restore-error]"));
  assert.equal(button("Send my response"), undefined);
  assert.equal(button("Skip task"), undefined);
  latestReplies.push(() => Response.json(savedClue("r8", "needsClarification", "obj-other")));
  await click("Try again");
  await flush();
  assert.equal(dom.window.document.querySelector("[data-testid=restore-error]"), null);
  assert.ok(button("Improve my clue"));
  root.unmount();
});

test("a photo without description support explains why there is no describing round", async () => {
  fixture = detail("inProgress", [{ ...task("learn", "completed", 0), kind: "vocabularyIntroduction" } as SessionTask,
    { ...task("clues", "completed", 1), kind: "ispyRound" } as SessionTask]);
  const container = dom.window.document.createElement("div");
  dom.window.document.body.replaceChildren(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  mountedClients.push(client);
  await act(async () => {
    root.render(h(QueryClientProvider, { client }, h(AppStateProvider, null,
      h(MemoryRouter, { initialEntries: [`${BASE}/ispy-2`] }, h(Routes, null,
        h(Route, { path: "/practice/sessions/:sessionId", element: h(SessionRoute) },
          h(Route, { path: "ispy-2", element: h(ISpyPhase2) }),
        ),
      )),
    )));
  });
  await flush();
  assert.ok(dom.window.document.querySelector("[data-testid=no-description-round]"));
  assert.ok(button("Finish session"));
  root.unmount();
});

const slotFrames = [
  { frameId: "colour", prefix: "Es", meaning: "colour meaning", example: "La manzana es roja.", chips: [], template: "Es [colour]",
    slots: [{ slotId: "colour", label: "colour", chips: [{ text: "azul", meaning: "blue" }, { text: "roja", meaning: "red" }] }], help: ["roja"] },
  { frameId: "location", prefix: "Está", meaning: "location meaning", example: "El libro está sobre la mesa.", chips: [],
    template: "Está [position] [reference object]",
    slots: [
      { slotId: "position", label: "position", chips: [{ text: "sobre", meaning: "on", example: "El libro está sobre la mesa." },
        { text: "debajo de", meaning: "under", example: "El gato está debajo de la silla." }, { text: "al lado de", meaning: "next to", example: "La silla está al lado de la puerta." }] },
      { slotId: "reference", label: "reference object", chips: [{ text: "el libro" }, { text: "la mesa" }, { text: "la silla" }] },
    ],
    phrases: Object.fromEntries(["sobre", "debajo de", "al lado de"].flatMap(position => ["el libro", "la mesa", "la silla"].map(reference =>
      [`${position}|${reference}`, position.endsWith(" de") && reference.startsWith("el ") ? `${position.slice(0, -3)} del ${reference.slice(3)}` : `${position} ${reference}`]))),
    help: ["sobre la mesa"] },
] as NonNullable<Extract<SessionTask["publicContent"], { kind: "reflection" }>["clueFrames"]>;
const slotTask = (status: SessionTask["status"]): SessionTask => ({ ...guessTask, status,
  publicContent: { kind: "reflection", prompt: "Describe it", clueFrames: slotFrames, avoidWords: ["taza", "tazas", "cup"] } });

async function mountSlots(status: SessionTask["status"]) {
  fixture = { ...detail("inProgress", [task("learn", "completed", 0), task("clues", "completed", 1), slotTask(status)]),
    sceneObjects: [sceneObject("obj-target", "taza", 0.3), sceneObject("obj-other", "mesa", 0.7)] };
  const container = dom.window.document.createElement("div");
  dom.window.document.body.replaceChildren(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  mountedClients.push(client);
  await act(async () => {
    root.render(h(QueryClientProvider, { client }, h(AppStateProvider, null,
      h(MemoryRouter, { initialEntries: [`${BASE}/ispy-2`] }, h(Routes, null,
        h(Route, { path: "/practice/sessions/:sessionId", element: h(SessionRoute) },
          h(Route, { path: "ispy-2", element: h(ISpyPhase2) }),
        ),
      )),
    )));
  });
  await flush();
  return root;
}

const slotReply = (attemptId: string, text: string, assistance: Record<string, unknown>) => () => Response.json({
  task: slotTask("inProgress"), nextTaskId: null,
  sessionProgress: { completedTaskCount: 2, skippedTaskCount: 0, terminalTaskCount: 2, totalTaskCount: 3 },
  xpEarned: 0,
  attempt: { id: attemptId, attemptNumber: 1, isCorrect: null, feedback: { message: "Not quite." },
    responsePayload: { input_mode: "text", text, assistance }, evaluationDetails: evaluation("noMatch", "obj-other") },
});

test("learners build a Location clue from separate position and reference chips, with optional help", async () => {
  const root = await mountSlots("pending");
  const text = () => dom.window.document.body.textContent ?? "";
  await click("Location");
  assert.match(text(), /Está \[position\] \[reference object\]/);
  assert.match(dom.window.document.querySelector("[data-testid=position-meanings]")?.textContent ?? "", /sobre — on · El libro está sobre la mesa\./);
  assert.equal(button("la taza"), undefined, "the target is never a chip");
  assert.equal(button("sobre la mesa"), undefined, "the correct phrase stays behind Help me");
  await click("sobre");
  assert.equal(clue().value, "Está sobre");
  await click("la mesa");
  assert.equal(clue().value, "Está sobre la mesa");
  await click("debajo de");
  assert.equal(clue().value, "Está debajo de la mesa", "changing the position keeps the reference");
  await click("al lado de");
  await click("el libro");
  assert.equal(clue().value, "Está al lado del libro");
  await click("Colour");
  await click("azul");
  assert.equal(clue().value, "Está al lado del libro. Es azul", "other sentences are preserved");
  await click("Help me");
  assert.ok(button("roja"), "help reveals the suggested phrase");
  await type(`${clue().value} y pequeña.`);

  taskReplies.push(slotReply("s1", "Está al lado del libro. Es azul y pequeña.", { selected_frame_ids: ["location", "colour"],
    inserted_chips: ["al lado de", "el libro"], revealed_help_frame_ids: ["colour"],
    selected_slots: [{ frame_id: "location", slot_id: "position", chip: "al lado de" }, { frame_id: "location", slot_id: "reference", chip: "el libro" },
      { frame_id: "colour", slot_id: "colour", chip: "azul" }] }));
  await click("Send my response");
  const [sent] = taskRequests.splice(0);
  assert.equal(sent.body.text, "Está al lado del libro. Es azul y pequeña.", "an incorrect combination still reaches the evaluator");
  const assistance = sent.body.assistance as Record<string, unknown>;
  assert.deepEqual(assistance.selectedSlots, [{ frameId: "location", slotId: "position", chip: "al lado de" },
    { frameId: "location", slotId: "reference", chip: "el libro" }, { frameId: "colour", slotId: "colour", chip: "azul" }]);
  assert.deepEqual(assistance.revealedHelpFrameIds, ["colour"], "opening help is recorded as assistance");
  assert.equal(assistance.practiceMode, "guided");
  await click("Improve my clue");
  await click("Location");
  assert.equal(button("al lado de")?.getAttribute("aria-pressed"), "true", "revision keeps the selected slots");
  assert.equal(clue().value, "Está al lado del libro. Es azul y pequeña.");
  root.unmount();
});

test("selected slots, revealed help and free edits survive a reload", async () => {
  latestReplies.push(() => Response.json({ attempt: { id: "s2", attemptNumber: 2, text: "Está sobre la mesa. Es pequeña.", feedback: "Saved feedback.",
    evaluationDetails: evaluation("noMatch", "obj-other"),
    assistance: { version: "ispy-clue-assistance.v1", practiceMode: "guided", targetWordShown: true, offeredFrameIds: ["colour", "location"],
      selectedFrameIds: ["location"], insertedChips: ["sobre", "la mesa"], revealedHelpFrameIds: ["location"],
      selectedSlots: [{ frameId: "location", slotId: "position", chip: "sobre" }, { frameId: "location", slotId: "reference", chip: "la mesa" }] } } }));
  const root = await mountSlots("inProgress");
  assert.equal(clue().value, "Está sobre la mesa. Es pequeña.");
  await click("Improve my clue");
  assert.equal(button("sobre")?.getAttribute("aria-pressed"), "true");
  assert.equal(button("la mesa")?.getAttribute("aria-pressed"), "true");
  assert.ok(button("sobre la mesa"), "revealed help stays revealed");
  await click("debajo de");
  assert.equal(clue().value, "Está debajo de la mesa. Es pequeña.", "the restored sentence is edited in place");
  root.unmount();
});

import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { PracticeDetail, SessionMode, SessionTask } from "../src/lib/api.ts";
import { learningFeedback } from "../src/lib/learningFeedback.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/", pretendToBeVisual: true });
const globals = globalThis as Record<string, unknown>;
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (globals[key] !== undefined) continue;
  try { globals[key] = (dom.window as unknown as Record<string, unknown>)[key]; } catch { /* Read-only Node globals stay intact. */ }
}
Object.defineProperty(globalThis, "window", { value: dom.window, configurable: true });
Object.defineProperty(globalThis, "document", { value: dom.window.document, configurable: true });
globals.IS_REACT_ACT_ENVIRONMENT = true;

const here = dirname(fileURLToPath(import.meta.url));
const workdir = mkdtempSync(join(tmpdir(), "ispy-answer-restore-"));
const entry = join(here, `.ispyAnswerRestore-${crypto.randomUUID()}.entry.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter, Route, Routes } from "react-router-dom";',
  'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
  'export { AppStateProvider } from "../src/state/AppState";',
  'export { SessionRoute } from "../src/components/SessionRoute";',
  'export { ISpyPhase1 } from "../src/pages/ISpyPhase1";',
].join("\n"));

async function bundle() {
  try {
    const bundler = await rolldown({
      input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
      plugins: [{ name: "test-api", transform: code => code.replaceAll("import.meta.env?.VITE_API_BASE_URL", '"http://api.test"') },
        { name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
          load: id => id === "\0empty-css" ? "export default {};" : null }],
    });
    try {
      const { output } = await bundler.generate({ format: "esm" });
      const path = join(workdir, "bundle.mjs");
      writeFileSync(path, output[0].code);
      return await import(pathToFileURL(path).href);
    } finally { await bundler.close(); }
  } finally { rmSync(entry, { force: true }); rmSync(workdir, { recursive: true, force: true }); }
}

const source = await bundle() as {
  h: typeof import("react").createElement; act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  Route: typeof import("react-router-dom").Route; Routes: typeof import("react-router-dom").Routes;
  QueryClient: typeof import("@tanstack/react-query").QueryClient;
  QueryClientProvider: typeof import("@tanstack/react-query").QueryClientProvider;
  AppStateProvider: typeof import("../src/state/AppState.tsx").AppStateProvider;
  SessionRoute: typeof import("../src/components/SessionRoute.tsx").SessionRoute;
  ISpyPhase1: typeof import("../src/pages/ISpyPhase1.tsx").ISpyPhase1;
};
const { h, act, createRoot, MemoryRouter, Route, Routes, QueryClient, QueryClientProvider, AppStateProvider, SessionRoute, ISpyPhase1 } = source;

const clue: SessionTask = {
  id: "clue1", kind: "ispyRound", phase: "ispy", status: "pending", orderIndex: 0,
  isSkippable: true, sceneObjectId: "object-a", vocabularyItemId: null,
  xpReward: 0, xpBonus: 0,
  publicContent: { kind: "ispyRound", clue: "es roja", options: [
    { optionId: "a", label: "taza", sceneObjectId: "object-a" },
    { optionId: "b", label: "mesa", sceneObjectId: "object-b" },
  ] },
};

function detail(mode: SessionMode): PracticeDetail {
  return {
    session: { id: "s1", mode, sourceSessionId: mode === "ispy" ? "lesson1" : null, status: "inProgress",
      sceneMediaAssetId: "asset", sessionTitle: "Table", sessionSummary: null, failureCode: null },
    mediaAsset: { id: "asset", source: "preloaded" }, sceneId: null, title: "Table", analysisMode: null, analysisRetryable: false,
    reviewMarkers: { "object-a": 1, "object-b": 2 },
    sceneObjects: ["object-a", "object-b"].map((id, index) => ({
      id, sessionId: "s1", label: index ? "table" : "cup", vocabularyItemId: null,
      boundingBox: null, anchorPoint: { x: index ? 0.7 : 0.2, y: 0.5 },
      attributes: {}, confidenceScore: null, sourceObjectKey: id,
    })), sceneObjectRelations: [], vocabulary: [], translations: [],
    tasks: [structuredClone(clue), { ...structuredClone(clue), id: "clue2", orderIndex: 1 }], nextTaskId: "clue1",
    progress: { completedTaskCount: 0, skippedTaskCount: 0, terminalTaskCount: 0, totalTaskCount: 2 },
  };
}

let fixture = detail("ispy");
let sessionReads = 0;
let latestReply: (() => Response | Promise<Response>) | null = null;
const requests: Record<string, unknown>[] = [];
const taskReplies: (() => Response | Promise<Response>)[] = [];
const originalFetch = globals.fetch;
globals.fetch = async (input: unknown, init?: RequestInit) => {
  const path = new URL(typeof input === "string" ? input : (input as Request).url).pathname;
  if (path === "/api/v1/me") return Response.json({ id: "u1", displayName: "Learner", timezone: "UTC" });
  if (path === "/api/v1/me/language-profiles") return Response.json([
    { id: "p1", userId: "u1", sourceLanguageCode: "en", targetLanguageCode: "es", proficiencyLevel: "A1", isActive: true },
  ]);
  if (path === "/api/v1/me/progress") return Response.json({ xp: 0, scenarios: [] });
  if (path === "/api/v1/sessions/s1") { sessionReads += 1; return Response.json(fixture); }
  if (path === "/api/v1/tasks/clue1/latest-attempt") return latestReply?.() ?? Response.json({ attempt: null });
  if (path === "/api/v1/tasks/clue1/attempts") {
    requests.push(JSON.parse(String(init?.body ?? "{}")));
    return taskReplies.shift()?.() ?? new Response("Unexpected attempt", { status: 500 });
  }
  return new Response("Unexpected request", { status: 404 });
};

const cleanups = new Set<() => Promise<void>>();
test.afterEach(async () => { for (const cleanup of cleanups) await cleanup(); });
test.after(() => {
  globals.fetch = originalFetch;
  dom.window.close();
  // The bundled browser scheduler's MessagePorts outlive its unmounted roots.
  for (const handle of (process as unknown as { _getActiveHandles(): { constructor: { name: string }; unref?: () => void }[] })._getActiveHandles()) {
    if (handle.constructor.name === "MessagePort") handle.unref?.();
  }
});

async function until(predicate: () => boolean, message: string) {
  const deadline = Date.now() + 2_000;
  while (!predicate() && Date.now() < deadline) await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
  assert.ok(predicate(), `${message}: ${dom.window.document.body.textContent}`);
}

const marker = (number: number) => dom.window.document.querySelector<HTMLButtonElement>(
  `button.scene__marker[aria-label="Marker ${number}"]`,
);
const next = () => [...dom.window.document.querySelectorAll<HTMLButtonElement>("button")]
  .find(button => button.textContent?.includes("Next clue"));
const click = (button: HTMLButtonElement | undefined) => act(async () => {
  assert.ok(button, "expected the answer control");
  assert.equal(button.disabled, false, "expected the answer to be enabled");
  button.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
});

async function mount(mode: SessionMode, patch: Partial<PracticeDetail> = {}, restoredOption?: string) {
  fixture = detail(mode); sessionReads = 0; requests.length = 0; taskReplies.length = 0; latestReply = null;
  fixture = { ...fixture, ...patch };
  if (restoredOption) latestReply = () => Response.json({ attempt: {
    id: "answer1", attemptNumber: 1, text: "", optionId: restoredOption,
    isCorrect: true, feedback: "Saved answer feedback.", evaluationDetails: null, assistance: null,
  } });
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0, refetchOnWindowFocus: false }, mutations: { gcTime: 0 } } });
  const cleanup = async () => {
    cleanups.delete(cleanup);
    try { await act(async () => { root.unmount(); }); } finally { client.clear(); container.remove(); }
  };
  cleanups.add(cleanup);
  const base = mode === "ispy" ? "/ispy/games/s1" : "/practice/sessions/s1";
  const route = mode === "ispy" ? "/ispy/games/:sessionId" : "/practice/sessions/:sessionId";
  const step = mode === "ispy" ? "clues" : "ispy-1";
  await act(async () => {
    root.render(h(QueryClientProvider, { client }, h(AppStateProvider, null,
      h(MemoryRouter, { initialEntries: [`${base}/${step}`] }, h(Routes, null,
        h(Route, { path: route, element: h(SessionRoute) }, h(Route, { path: step, element: h(ISpyPhase1) })),
      )),
    )));
  });
  await until(() => Boolean(dom.window.document.querySelector("button.scene__marker")),
    "the real clue round should load its photo markers");
}

function commit(isCorrect: boolean) {
  fixture = { ...fixture, tasks: [{ ...fixture.tasks[0], status: "completed" }, fixture.tasks[1]],
    progress: { ...fixture.progress, completedTaskCount: 1, terminalTaskCount: 1 }, nextTaskId: "clue2" };
  return { task: fixture.tasks[0], sessionProgress: fixture.progress, nextTaskId: "clue2",
    xpEarned: isCorrect ? 25 : 10, basilEarned: 1,
    attempt: { id: "answer1", attemptNumber: 1, isCorrect, responsePayload: { optionId: "a" }, feedback: { message: "Saved answer feedback." } } };
}

for (const mode of ["ispy", "lesson"] as const) {
  test(`${mode}: a lost answer and conflicting second tap restore the accepted option and grade`, async () => {
    await mount(mode);
    let releaseLatest: ((response: Response) => void) | undefined;
    latestReply = () => new Promise<Response>(resolve => { releaseLatest = resolve; });
    taskReplies.push(() => { commit(false); throw new Error("Lost response after the write"); });
    taskReplies.push(() => Response.json({ detail: { code: "task_conflict", message: "This task is already completed." } }, { status: 409 }));
    await click(marker(1) ?? undefined);
    await until(() => Boolean(marker(2) && !marker(2)!.disabled), "a network failure should allow recovery");
    assert.equal(requests.length, 1);
    await click(marker(2) ?? undefined);
    await until(() => Boolean(releaseLatest), "the conflict should reload the saved task and request its answer");
    assert.ok(sessionReads >= 2, "a task conflict must refresh the session without reloading the page");
    await act(async () => { releaseLatest!(Response.json({ attempt: {
      id: "answer1", attemptNumber: 1, text: "", optionId: "a", isCorrect: false,
      feedback: "Saved answer feedback.", evaluationDetails: null, assistance: null,
    } })); });
    await until(() => dom.window.document.querySelector(".scene__marker--guess")?.textContent === "1",
      "the stored incorrect grade belongs to the stored marker");
    assert.notEqual(dom.window.document.querySelector(".scene__marker--guess")?.textContent, "2");
    assert.match(dom.window.document.body.textContent ?? "", /Saved answer feedback\./);
    assert.ok(dom.window.document.body.textContent?.includes(learningFeedback("incorrect", clue.id)));
    assert.ok(!dom.window.document.body.textContent?.includes(learningFeedback("correct", clue.id)));
    assert.doesNotMatch(dom.window.document.body.textContent ?? "", /\+\d+ Basil earned/);
    assert.equal(next()?.disabled, false, "the recovered round can advance");
    assert.equal(requests.length, 2, "recovery must not submit another answer");
  });
}

test("retrying an unanswered response reuses its command key and displays the accepted result", async () => {
  await mount("ispy");
  taskReplies.push(() => { throw new Error("Reply interrupted"); });
  taskReplies.push(() => Response.json(commit(true)));
  await click(marker(1) ?? undefined);
  await until(() => Boolean(marker(1) && !marker(1)!.disabled), "the interrupted answer should be retryable");
  assert.ok(!dom.window.document.body.textContent?.includes(learningFeedback("correct", clue.id)));
  await click(marker(1) ?? undefined);
  await until(() => dom.window.document.querySelector(".scene__marker--active")?.textContent === "1",
    "the accepted answer should highlight its saved marker");
  assert.match(dom.window.document.body.textContent ?? "", /\+1 Basil earned/);
  assert.ok(dom.window.document.body.textContent?.includes(learningFeedback("correct", clue.id)));
  assert.match(dom.window.document.body.textContent ?? "", /Saved answer feedback\./);
  assert.equal(requests.length, 2);
  assert.equal(requests[0].idempotencyKey, requests[1].idempotencyKey);
  assert.equal(typeof requests[0].idempotencyKey, "string");
  assert.equal(next()?.disabled, false);
});

function repeatedObjects(label: string): Partial<PracticeDetail> {
  const round = structuredClone(clue);
  if (round.publicContent.kind !== "ispyRound") throw new Error("Expected clue round");
  round.publicContent.options = [
    { optionId: "b", label, sceneObjectId: "object-b" },
    { optionId: "a", label, sceneObjectId: "object-a" },
  ];
  return {
    tasks: [round, { ...structuredClone(round), id: "clue2", orderIndex: 1 }],
    reviewMarkers: { "object-a": 2, "object-b": 7 },
    sceneObjects: ["object-a", "object-b"].map((id, index) => ({
      id, sessionId: "s1", label: "car", vocabularyItemId: null,
      boundingBox: null, anchorPoint: { x: index ? 0.7 : 0.2, y: 0.5 },
      attributes: {}, confidenceScore: null, sourceObjectKey: id,
    })),
  };
}

for (const mode of ["ispy", "lesson"] as const) {
  for (const label of ["coche", "voiture", "Auto", "자동차", "கார்"]) {
    test(`${mode}: repeated ${label} choices retain photo marker identities after shuffling`, async () => {
      await mount(mode, repeatedObjects(label));
      assert.equal(dom.window.document.querySelectorAll(".choice").length, 0,
        "Linguini's clue uses only markers, without duplicate answer choices");
      const markers = [...dom.window.document.querySelectorAll<HTMLButtonElement>("button.scene__marker")];
      assert.deepEqual(markers.map(marker => marker.getAttribute("aria-label")), ["Marker 2", "Marker 7"]);
      let release: ((response: Response) => void) | undefined;
      taskReplies.push(() => new Promise<Response>(resolve => { release = resolve; }));
      await click(markers[1]);
      await until(() => Boolean(release), "marker submits the matching option");
      assert.equal(requests[0].optionId, "b");
      assert.equal(dom.window.document.querySelector("button.scene__marker"), null,
        "photo submissions are blocked while checking");
      await act(async () => {
        const result = commit(true);
        result.attempt.responsePayload.optionId = "b";
        release!(Response.json(result));
      });
      await until(() => dom.window.document.querySelector(".scene__marker--active")?.textContent === "7",
        "the selected instance gets the saved grade");
      assert.equal(requests.length, 1);
      assert.equal(dom.window.document.querySelector(".scene__marker--active")?.textContent, "7");
    });
  }
}

test("a restored repeated-object answer highlights its original marker without resubmission", async () => {
  const patch = repeatedObjects("voiture");
  await mount("ispy", patch, "b");
  taskReplies.push(() => { commit(true); throw new Error("Lost response after the write"); });
  taskReplies.push(() => Response.json({ detail: {
    code: "task_conflict", message: "This task is already completed.",
  } }, { status: 409 }));
  await click(marker(7) ?? undefined);
  await until(() => Boolean(marker(7) && !marker(7)!.disabled),
    "the interrupted answer can recover");
  await click(marker(7) ?? undefined);
  await until(() => dom.window.document.querySelector(".scene__marker--active")?.textContent === "7",
    "restore keeps the saved instance");
  assert.equal(dom.window.document.querySelector(".scene__marker--active")?.textContent, "7");
  assert.equal(requests.length, 2, "restoring the accepted answer never submits another answer");
});

function levelled(content: Partial<Extract<SessionTask["publicContent"], { kind: "ispyRound" }>>): Partial<PracticeDetail> {
  const task = { ...structuredClone(clue), publicContent: { ...structuredClone(clue.publicContent), clueTranslation: "is red", ...content } } as SessionTask;
  return { tasks: [task, { ...structuredClone(task), id: "clue2", orderIndex: 1 }] };
}
const body = () => dom.window.document.body.textContent ?? "";

test("A0 rounds show the translation, a word bank and the cheatsheet", async () => {
  await mount("ispy", levelled({
    learnerLevel: "A0", translationShown: true,
    wordBank: [{ text: "taza", translation: "cup" }, { text: "mesa", translation: "table" }],
    cheatSheet: { missionId: "M02", practiceLevel: "A0", contentVersion: 2 },
  }));
  assert.match(body(), /es roja/);
  assert.match(body(), /is red/, "the translation is open from the start");
  const words = [...dom.window.document.querySelectorAll(".ispy-help__words li")].map(item => item.textContent);
  assert.deepEqual(words, ["tazacup", "mesatable"]);
  assert.ok(dom.window.document.querySelector('button[aria-label="Open cheatsheet"]'));
});

test("A1 rounds keep the translation and word bank behind their toggles", async () => {
  await mount("ispy", levelled({ learnerLevel: "A1",
    wordBank: [{ text: "taza", translation: "cup" }, { text: "mesa", translation: "table" }] }));
  assert.match(body(), /es roja/);
  assert.doesNotMatch(body(), /is red/);
  assert.equal(dom.window.document.querySelector(".ispy-help__words"), null);
  const showWords = [...dom.window.document.querySelectorAll<HTMLButtonElement>("button")]
    .find(button => button.textContent?.includes("Show word bank"));
  await click(showWords);
  assert.deepEqual([...dom.window.document.querySelectorAll(".ispy-help__words strong")]
    .map(item => item.textContent), ["taza", "mesa"]);
});

test("A2 rounds play the clue before showing its text", async () => {
  await mount("ispy", levelled({ learnerLevel: "A2", listenFirst: true }));
  assert.ok(dom.window.document.querySelector('[data-testid="listen-first"]'));
  assert.doesNotMatch(body(), /es roja/, "the clue text waits until it is heard");
  const play = [...dom.window.document.querySelectorAll<HTMLButtonElement>("button")]
    .find(button => button.textContent?.includes("Play the clue"));
  await click(play);
  assert.match(body(), /es roja/);
  assert.equal(dom.window.document.querySelector('[data-testid="listen-first"]'), null);
});

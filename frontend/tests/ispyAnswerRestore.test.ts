import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { PracticeDetail, SessionMode, SessionTask } from "../src/lib/api.ts";

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
    sceneObjects: [], sceneObjectRelations: [], vocabulary: [], translations: [],
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

const choice = (label: string) => [...dom.window.document.querySelectorAll<HTMLButtonElement>(".choice")]
  .find(button => button.textContent?.trim() === label);
const next = () => [...dom.window.document.querySelectorAll<HTMLButtonElement>("button")]
  .find(button => button.textContent?.includes("Next clue"));
const click = (button: HTMLButtonElement | undefined) => act(async () => {
  assert.ok(button, "expected the answer control");
  assert.equal(button.disabled, false, "expected the answer to be enabled");
  button.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
});

async function mount(mode: SessionMode) {
  fixture = detail(mode); sessionReads = 0; requests.length = 0; taskReplies.length = 0; latestReply = null;
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
  await until(() => Boolean(choice("taza")), "the real clue round should load");
}

function commit(isCorrect: boolean) {
  fixture = { ...fixture, tasks: [{ ...fixture.tasks[0], status: "completed" }, fixture.tasks[1]],
    progress: { ...fixture.progress, completedTaskCount: 1, terminalTaskCount: 1 }, nextTaskId: "clue2" };
  return { task: fixture.tasks[0], sessionProgress: fixture.progress, nextTaskId: "clue2",
    xpEarned: isCorrect ? 25 : 10,
    attempt: { id: "answer1", attemptNumber: 1, isCorrect, responsePayload: { optionId: "a" }, feedback: { message: "Saved answer feedback." } } };
}

for (const mode of ["ispy", "lesson"] as const) {
  test(`${mode}: a lost answer and conflicting second tap restore the accepted option and grade`, async () => {
    await mount(mode);
    let releaseLatest: ((response: Response) => void) | undefined;
    latestReply = () => new Promise<Response>(resolve => { releaseLatest = resolve; });
    taskReplies.push(() => { commit(false); throw new Error("Lost response after the write"); });
    taskReplies.push(() => Response.json({ detail: { code: "task_conflict", message: "This task is already completed." } }, { status: 409 }));
    await click(choice("taza"));
    await until(() => Boolean(choice("mesa") && !choice("mesa")!.disabled), "a network failure should allow recovery");
    assert.equal(requests.length, 1);
    await click(choice("mesa"));
    await until(() => Boolean(releaseLatest), "the conflict should reload the saved task and request its answer");
    assert.ok(sessionReads >= 2, "a task conflict must refresh the session without reloading the page");
    assert.equal(choice("mesa")?.getAttribute("aria-pressed"), "false", "the rejected tap must not stand in for a saved answer");
    await act(async () => { releaseLatest!(Response.json({ attempt: {
      id: "answer1", attemptNumber: 1, text: "", optionId: "a", isCorrect: false,
      feedback: "Saved answer feedback.", evaluationDetails: null, assistance: null,
    } })); });
    await until(() => Boolean(choice("taza")?.classList.contains("choice--incorrect")), "the stored incorrect grade belongs to the stored option");
    assert.equal(choice("taza")?.getAttribute("aria-pressed"), "true");
    assert.equal(choice("mesa")?.classList.contains("choice--incorrect"), false);
    assert.match(dom.window.document.body.textContent ?? "", /Saved answer feedback\./);
    assert.doesNotMatch(dom.window.document.body.textContent ?? "", /\+\d+ Basil earned/);
    assert.equal(next()?.disabled, false, "the recovered round can advance");
    assert.equal(requests.length, 2, "recovery must not submit another answer");
  });
}

test("retrying an unanswered response reuses its command key and displays the accepted result", async () => {
  await mount("ispy");
  taskReplies.push(() => { throw new Error("Reply interrupted"); });
  taskReplies.push(() => Response.json(commit(true)));
  await click(choice("taza"));
  await until(() => Boolean(choice("taza") && !choice("taza")!.disabled), "the interrupted answer should be retryable");
  await click(choice("taza"));
  await until(() => Boolean(choice("taza")?.classList.contains("choice--correct")), "the accepted answer should show its saved grade");
  assert.match(dom.window.document.body.textContent ?? "", /\+25 Basil earned/);
  assert.equal(requests.length, 2);
  assert.equal(requests[0].idempotencyKey, requests[1].idempotencyKey);
  assert.equal(typeof requests[0].idempotencyKey, "string");
  assert.equal(next()?.disabled, false);
});

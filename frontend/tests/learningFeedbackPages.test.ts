import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { PracticeDetail } from "../src/lib/api.ts";
import type { AppState } from "../src/state/context.ts";
import type { Scene } from "../src/data/types.ts";
import { learningFeedback } from "../src/lib/learningFeedback.ts";
import { queryKeys } from "../src/lib/queryKeys.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
for (const key of ["window", "document", "localStorage", "HTMLElement"] as const) {
  Object.defineProperty(globalThis, key, { value: key === "window" ? dom.window : dom.window[key], configurable: true });
}
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
const NativeMessageChannel = globalThis.MessageChannel;
const channels: MessageChannel[] = [];
globalThis.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); channels.push(this); }
};
const here = dirname(fileURLToPath(import.meta.url));
const folder = mkdtempSync(join(tmpdir(), "learning-feedback-pages-"));
const entry = join(here, `.learningFeedbackPages-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter, Route, Routes, Outlet } from "react-router-dom";',
  'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
  'export { AuthProvider } from "../src/state/Auth";',
  'export { AppStateContext } from "../src/state/context";',
  'export { Learn } from "../src/pages/Learn";',
  'export { SessionSummary } from "../src/pages/SessionSummary";',
  'export { ISpyResults } from "../src/pages/ISpyResults";',
].join("\n"));
let bundled: unknown;
try {
  const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{ name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
      load: id => id === "\0empty-css" ? "export default {};" : null }],
  });
  try {
    const { output } = await bundler.generate({ format: "esm" });
    const path = join(folder, "bundle.mjs");
    writeFileSync(path, output[0].code);
    bundled = await import(pathToFileURL(path).href);
  } finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
const source = bundled as {
  h: typeof import("react").createElement; act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  Route: typeof import("react-router-dom").Route; Routes: typeof import("react-router-dom").Routes;
  Outlet: typeof import("react-router-dom").Outlet;
  QueryClient: typeof import("@tanstack/react-query").QueryClient;
  QueryClientProvider: typeof import("@tanstack/react-query").QueryClientProvider;
  AuthProvider: typeof import("../src/state/Auth.tsx").AuthProvider;
  AppStateContext: typeof import("../src/state/context.ts").AppStateContext;
  Learn: typeof import("../src/pages/Learn.tsx").Learn;
  SessionSummary: typeof import("../src/pages/SessionSummary.tsx").SessionSummary;
  ISpyResults: typeof import("../src/pages/ISpyResults.tsx").ISpyResults;
};
const { h, act, createRoot, MemoryRouter, Route, Routes, Outlet, QueryClient, QueryClientProvider, AuthProvider, AppStateContext } = source;
const scene: Scene = { id: "scene", sessionId: "session", mediaAssetId: "asset", imageUrl: "/photo.jpg",
  languageCode: "es", language: "Spanish", title: "Kitchen", blurb: "", items: [] };
const summary = { progress: { completedTaskCount: 2, skippedTaskCount: 1, terminalTaskCount: 3, totalTaskCount: 3 },
  learnedVocabularyIds: ["word"], xpEarned: 12, ispyCorrectCount: 1, ispyAttemptCount: 2, completedLessonsCount: 2 };
function state(patch: Partial<AppState> = {}): AppState {
  return { session: { session: { id: "session", mode: "lesson", status: "completed" }, sceneObjects: [], tasks: [] } as unknown as PracticeDetail,
    activeProfile: { id: "profile" }, completionPending: false, completionError: null,
    retryCompletion: () => {}, practiceError: null, practiceSaving: false, ...patch } as AppState;
}
const cleanups = new Set<() => Promise<void>>();
async function mount(Page: typeof source.Learn, initial: AppState, hasSummary = true) {
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, gcTime: 0 } } });
  client.setQueryData(queryKeys.vocabulary("profile"), []);
  if (hasSummary) client.setQueryData(queryKeys.sessionSummary("session"), summary);
  const render = (value: AppState) => act(async () => {
    root.render(h(QueryClientProvider, { client }, h(AuthProvider, null,
      h(AppStateContext.Provider, { value }, h(MemoryRouter, null, h(Routes, null,
        h(Route, { element: h(Outlet, { context: scene }) }, h(Route, { path: "/", element: h(Page) }))))))));
  });
  const cleanup = async () => {
    await act(async () => { root.unmount(); });
    client.clear(); container.remove(); cleanups.delete(cleanup);
  };
  cleanups.add(cleanup);
  await render(initial);
  return { render, container, client };
}
test.afterEach(async () => { for (const cleanup of [...cleanups]) await cleanup(); });
test.after(() => {
  dom.window.close();
  for (const channel of channels) { channel.port1.close(); channel.port2.close(); }
  globalThis.MessageChannel = NativeMessageChannel;
});

for (const Page of [source.SessionSummary, source.ISpyResults]) {
  test(`${Page.name} waits for accepted completion and keeps result details`, async () => {
    const view = await mount(Page, state({ completionPending: true }));
    const heading = () => view.container.querySelector("h1")?.textContent;
    assert.notEqual(heading(), learningFeedback("completed", "session"));
    assert.match(view.container.textContent ?? "", /12|1\/2/);
    await view.render(state({ completionError: "Your session could not be saved." }));
    assert.notEqual(heading(), learningFeedback("completed", "session"));
    assert.match(view.container.textContent ?? "", /Your session could not be saved\./);
    assert.ok([...view.container.querySelectorAll("button")].some(button => button.textContent?.startsWith("Retry saving")));
    await view.render(state());
    assert.equal(heading(), learningFeedback("completed", "session"));
    assert.match(view.container.textContent ?? "", /That’s a lesson well cooked\.|You played I-Spy with kitchen\./);
  });
}

test("lesson summary stays neutral when its result details are unavailable", async () => {
  const view = await mount(source.SessionSummary, state(), false);
  assert.equal(view.container.querySelector("h1")?.textContent, "Your session");
});

test("lesson preparation keeps its factual task status beside the branded copy", async () => {
  const current = state();
  current.session!.session.status = "generatingTasks";
  const view = await mount(source.Learn, current);
  assert.ok(view.container.textContent?.includes(learningFeedback("start", "session")));
  const status = view.container.querySelector('[role="status"]');
  assert.ok(status?.textContent?.includes(learningFeedback("preparing", "session")));
  assert.match(status?.textContent ?? "", /Preparing the remaining tasks\.\.\./);
  assert.match(status?.textContent ?? "", /You can learn and practise your words now\./);
});

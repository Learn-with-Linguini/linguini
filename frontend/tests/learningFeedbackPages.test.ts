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
import { gamificationKeys } from "../src/lib/gamification.ts";

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
  'export { Home } from "../src/pages/Home";',
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
  Home: typeof import("../src/pages/Home.tsx").Home;
};
const { h, act, createRoot, MemoryRouter, Route, Routes, Outlet, QueryClient, QueryClientProvider, AuthProvider, AppStateContext } = source;
const scene: Scene = { id: "scene", sessionId: "session", mediaAssetId: "asset", imageUrl: "/photo.jpg",
  languageCode: "es", language: "Spanish", title: "Kitchen", blurb: "", items: [] };
const summary = { progress: { completedTaskCount: 2, skippedTaskCount: 1, terminalTaskCount: 3, totalTaskCount: 3 },
  learnedVocabularyIds: ["word"], xpEarned: 120, basilEarned: 12, ispyCorrectCount: 1, ispyAttemptCount: 2, completedLessonsCount: 2 };
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
        h(Route, { element: h(Outlet, { context: scene }) },
          h(Route, { path: "/", element: h(Page) }),
          h(Route, { path: "/practice/sessions/:sessionId/learn/:taskId", element: h("div", { "data-testid": "vocabulary-review" }) }))))))));
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

test("lesson preparation keeps its factual task status on the mission path", async () => {
  const current = state();
  current.session!.session.status = "generatingTasks";
  const view = await mount(source.Learn, current);
  const status = [...view.container.querySelectorAll('[role="status"]')]
    .find(item => item.textContent?.includes(learningFeedback("preparing", "session")));
  assert.match(status?.textContent ?? "", /Preparing the remaining tasks\.\.\./);
  assert.match(status?.textContent ?? "", /You can learn and practise your words now\./);
});

const pathTasks = (statuses: [string, string, string]) => [
  { id: "words", kind: "vocabularyIntroduction", status: statuses[0], orderIndex: 0, sceneObjectId: null, xpReward: 10, xpBonus: 0,
    publicContent: { kind: "vocabularyIntroduction", title: "Photo words", allowTypingPractice: true,
      words: [{ learningKey: "cup", termType: "object", vocabularyItemId: "word", sceneObjectId: null,
        targetText: "taza", translation: "cup", partOfSpeech: "noun", gender: null, pluralForm: null,
        phoneticText: null, pronunciationAudioAssetId: null, exampleSentence: null }], questions: [] } },
  { id: "identify", kind: "grammarLesson", status: statuses[1], orderIndex: 1, sceneObjectId: null, xpReward: 10, xpBonus: 0,
    publicContent: { kind: "grammarLesson", title: "Name and identify", missionId: "M01", practiceLevel: "A0",
      contentVersion: "M01-A0.v1", focus: "a0M01", explanation: "Spot them in your photo.", prepChunks: [], questions: [], checkEachQuestion: true } },
  { id: "prefer", kind: "grammarLesson", status: statuses[2], orderIndex: 2, sceneObjectId: null, xpReward: 10, xpBonus: 0,
    publicContent: { kind: "grammarLesson", title: "Pick what you like", missionId: "M05", practiceLevel: "A0",
      contentVersion: "M05-A0.v1", focus: "a0M05", explanation: "Choose your favourites.", prepChunks: [], questions: [], checkEachQuestion: true } },
] as unknown as PracticeDetail["tasks"];

function pathState(statuses: [string, string, string], patch: Partial<AppState> = {}) {
  const current = state(patch);
  current.session!.session.status = "inProgress";
  current.session!.translationPreview = null;
  current.session!.tasks = pathTasks(statuses);
  return current;
}

const missionButton = (view: { container: HTMLElement }, name: string) =>
  [...view.container.querySelectorAll<HTMLButtonElement>(".mission-step__button")]
    .find(button => button.getAttribute("aria-label")?.startsWith(name));
const primary = (view: { container: HTMLElement }) => view.container.querySelector<HTMLButtonElement>(".mission-path__cta button");

test("mission path recommends the word review first and lets learners skip ahead", async () => {
  const view = await mount(source.Learn, pathState(["ready", "ready", "ready"]));
  assert.deepEqual([...view.container.querySelectorAll(".mission-step__text strong")].map(item => item.textContent),
    ["Learn the words", "Name and identify", "Pick what you like"]);
  assert.match(view.container.textContent ?? "", /1 new word for this scene/);
  assert.equal(missionButton(view, "Learn the words")?.getAttribute("aria-label"), "Learn the words, next mission");
  assert.equal(missionButton(view, "Name and identify")?.getAttribute("aria-label"), "Name and identify, not started");
  assert.equal(missionButton(view, "Name and identify")?.disabled, false);
  assert.equal(view.container.querySelectorAll(".mission-step--current").length, 1);
  assert.match(view.container.querySelector(".mission-path__leaves")?.textContent ?? "", /0 \/ 30/);
  assert.match(primary(view)?.textContent ?? "", /Start/);
  assert.doesNotMatch(view.container.textContent ?? "", /Next missions|Start here|\b[123]\./);
  await act(async () => primary(view)?.click());
  assert.ok(view.container.querySelector('[data-testid="vocabulary-review"]'), "Start opens the word review");
});

test("a later mission opens directly without finishing the earlier ones", async () => {
  const view = await mount(source.Learn, pathState(["ready", "ready", "ready"]));
  await act(async () => missionButton(view, "Pick what you like")?.click());
  assert.ok(view.container.querySelector('[data-testid="vocabulary-review"]'));
});

test("after the word review the next mission is current and finished ones can be redone", async () => {
  const view = await mount(source.Learn, pathState(["completed", "ready", "ready"]));
  assert.equal(missionButton(view, "Learn the words")?.getAttribute("aria-label"), "Learn the words, done");
  assert.equal(missionButton(view, "Name and identify")?.getAttribute("aria-label"), "Name and identify, next mission");
  assert.match(view.container.textContent ?? "", /Done · Tap to redo/);
  assert.match(view.container.querySelector(".mission-path__leaves")?.textContent ?? "", /10 \/ 30/);
  assert.match(primary(view)?.textContent ?? "", /Continue/);
  await act(async () => missionButton(view, "Learn the words")?.click());
  assert.ok(view.container.querySelector('[data-testid="vocabulary-review"]'), "a finished mission replays");
});

test("a skipped-ahead mission shows as done while the earlier one stays next", async () => {
  const view = await mount(source.Learn, pathState(["completed", "ready", "completed"]));
  assert.equal(missionButton(view, "Name and identify")?.getAttribute("aria-label"), "Name and identify, next mission");
  assert.equal(missionButton(view, "Pick what you like")?.getAttribute("aria-label"), "Pick what you like, done");
  assert.match(primary(view)?.textContent ?? "", /Continue/);
});

test("when every mission is done the path finishes the lesson", async () => {
  let finished = 0;
  const view = await mount(source.Learn, pathState(["completed", "completed", "completed"], {
    completeSession: () => { finished += 1; return false; },
  } as Partial<AppState>));
  assert.equal(view.container.querySelectorAll(".mission-step--done").length, 3);
  assert.equal(view.container.querySelectorAll(".mission-step--current").length, 0);
  assert.match(view.container.querySelector(".mission-path__leaves")?.textContent ?? "", /30 \/ 30/);
  assert.match(primary(view)?.textContent ?? "", /Done/);
  await act(async () => primary(view)?.click());
  assert.equal(finished, 1);
});

test("Home announces Basil loading and unavailable states without inventing a zero total", async () => {
  const current = state({ user: null, learner: { name: "Learner" } as AppState["learner"],
    progress: null, progressLoading: true, progressError: null });
  const view = await mount(source.Home, current);
  const total = () => view.container.querySelector(".home-points")!;
  assert.equal(total().getAttribute("aria-label"), "Loading your Basil total");
  assert.match(total().textContent ?? "", /— Basil/);
  const key = gamificationKeys.summary("owner", "profile");
  view.client.setQueryData(key, { basil: { lifetime: 67 }, missions: [] });
  await view.render({ ...current, user: { id: "owner" } as AppState["user"] });
  assert.equal(total().getAttribute("aria-label"), "67 total Basil");
  await act(async () => {
    await view.client.invalidateQueries({ queryKey: key });
    await new Promise(resolve => setTimeout(resolve, 10));
  });
  assert.equal(total().getAttribute("aria-label"), "Basil total unavailable");
  assert.match(total().textContent ?? "", /— Basil/);
});

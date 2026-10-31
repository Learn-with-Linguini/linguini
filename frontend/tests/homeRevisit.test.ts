import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { AppState } from "../src/state/context.ts";
import type { ScenarioProgress, VocabRecord } from "../src/data/types.ts";
import { homeRevisitPhotos } from "../src/lib/homeRevisit.ts";
import { gamificationKeys } from "../src/lib/gamification.ts";
import { queryKeys } from "../src/lib/queryKeys.ts";

const scenario = (asset: string, sessionId = `session-${asset}`, status: ScenarioProgress["status"] = "completed"): ScenarioProgress => ({
  mediaAssetId: asset, sessionId, title: `Photo ${asset}`, sceneId: `scene-${asset}`, status,
  completedTaskCount: 1, totalTaskCount: 1, level: "Starter",
});
const word = (id: string, assets: string[]): VocabRecord => ({
  id, word: id, translation: id, wordClass: "noun", gender: null, status: "learning",
  firstLearnedAt: null, topic: "", sceneId: "", example: "",
  scenes: assets.map(asset => ({ mediaAssetId: asset, title: `Photo ${asset}`, sceneId: `scene-${asset}` })),
});
const vocabulary = [word("shared", ["a", "b", "b"]), word("cup", ["a"]), word("table", ["a"]),
  word("chair", ["b"]), word("plant", ["c"]), word("tree", ["d"]), word("pending", ["unfinished"])];
const scenarios = [scenario("a", "older-a"), scenario("b"), scenario("c"), scenario("d"),
  scenario("unfinished", "pending-session", "in-progress"), scenario("a", "latest-a")];

test("Home ranks three distinct completed photos by unique learned words and keeps each photo's saved session", () => {
  assert.deepEqual(homeRevisitPhotos(scenarios, vocabulary), [
    { mediaAssetId: "a", sessionId: "latest-a", title: "Photo a", wordCount: 3 },
    { mediaAssetId: "b", sessionId: "session-b", title: "Photo b", wordCount: 2 },
    { mediaAssetId: "c", sessionId: "session-c", title: "Photo c", wordCount: 1 },
  ]);
});

test("Home excludes missing and unfinished sessions while retaining older words with scene provenance", () => {
  const legacy = { ...word("legacy", []), sceneId: "scene-old" };
  assert.deepEqual(homeRevisitPhotos([
    scenario("old", "saved-old", "mastered"), scenario("missing-session", ""),
    scenario("pending", "pending", "in-progress"), scenario("no-words"),
  ], [legacy, word("unreviewable", ["missing-session", "pending", "unknown"])]), [
    { mediaAssetId: "old", sessionId: "saved-old", title: "Photo old", wordCount: 1 },
  ]);
});

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://app.test/" });
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
const folder = mkdtempSync(join(tmpdir(), "home-revisit-"));
const entry = join(here, `.homeRevisit-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter, useLocation } from "react-router-dom";',
  'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
  'export { AppStateContext } from "../src/state/context";',
  'export { Home } from "../src/pages/Home";',
].join("\n"));
let bundled: unknown;
try {
  const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{ name: "test-api", transform: code => code.replaceAll("import.meta.env?.VITE_API_BASE_URL", '"http://api.test"') },
      { name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
        load: id => id === "\0empty-css" ? "export default {};" : null }],
  });
  try {
    const { output } = await bundler.generate({ format: "esm" });
    const path = join(folder, "bundle.mjs"); writeFileSync(path, output[0].code);
    bundled = await import(pathToFileURL(path).href);
  } finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
const { h, act, createRoot, MemoryRouter, useLocation, QueryClient, QueryClientProvider, AppStateContext, Home } = bundled as {
  h: typeof import("react").createElement; act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter; useLocation: typeof import("react-router-dom").useLocation;
  QueryClient: typeof import("@tanstack/react-query").QueryClient; QueryClientProvider: typeof import("@tanstack/react-query").QueryClientProvider;
  AppStateContext: typeof import("../src/state/context.ts").AppStateContext; Home: typeof import("../src/pages/Home.tsx").Home;
};
const originalFetch = globalThis.fetch;
const reads: string[] = [];
let failPhotos = false;
globalThis.fetch = async (input, init) => {
  assert.notEqual(init?.method, "POST", "reopening vocabulary must not create or charge for a new lesson");
  const path = new URL(String(input)).pathname; reads.push(path);
  if (path.startsWith("/api/v1/media/")) return failPhotos ? new Response("Unavailable", { status: 404 }) : new Response(new Blob(["photo"]));
  if (path === "/api/v1/me/vocabulary") return Response.json([]);
  throw new Error(`Unexpected request: ${path}`);
};
const cleanups = new Set<() => Promise<void>>();
test.beforeEach(() => { reads.length = 0; failPhotos = false; window._uxa = []; });
test.afterEach(async () => { for (const cleanup of [...cleanups]) await cleanup(); });
test.after(() => {
  globalThis.fetch = originalFetch; dom.window.close();
  for (const channel of channels) { channel.port1.close(); channel.port2.close(); }
  globalThis.MessageChannel = NativeMessageChannel;
});
function CurrentRoute() { return h("output", { "aria-label": "Current route" }, useLocation().pathname); }
const state = (overrides: Partial<AppState> = {}) => ({
  user: { id: "learner", onboardingCompleted: false }, activeProfile: { id: "profile" }, learner: { name: "Learner" },
  progressLoading: false, progressError: null, progress: { streak: { days: [] }, scenarios, leaderboard: [] },
  ...overrides,
}) as unknown as AppState;

async function mount(initial = state(), words = vocabulary) {
  const container = dom.window.document.createElement("div"); dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, gcTime: Infinity } } });
  function seed(next: AppState, records: VocabRecord[]) {
    const profileId = next.activeProfile?.id ?? ""; const owner = next.user?.id ?? "";
    client.setQueryData(queryKeys.vocabulary(profileId), records);
    client.setQueryData(queryKeys.activeSession(profileId), null);
    client.setQueryData(gamificationKeys.summary(owner, profileId), { basil: { lifetime: 0 }, missions: [] });
    client.setQueryData(gamificationKeys.chefs(owner), { currentRank: null });
  }
  const render = async (next: AppState, records: VocabRecord[]) => {
    seed(next, records);
    await act(async () => root.render(h(QueryClientProvider, { client }, h(AppStateContext.Provider, { value: next },
      h(MemoryRouter, null, h(Home), h(CurrentRoute))))));
  };
  await render(initial, words);
  const cleanup = async () => { await act(async () => root.unmount()); client.clear(); container.remove(); cleanups.delete(cleanup); };
  cleanups.add(cleanup);
  return { container, client, render };
}
async function waitFor(assertion: () => void) {
  const deadline = Date.now() + 2_000; let failure: unknown;
  do {
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
    try { assertion(); return; } catch (error) { failure = error; }
  } while (Date.now() < deadline);
  throw failure;
}
const photoCards = (container: HTMLElement) => [...container.querySelectorAll<HTMLButtonElement>(".home-explore-card--revisit")];

test("each Home thumbnail opens that completed lesson's read-only vocabulary review", async () => {
  const view = await mount();
  const cards = photoCards(view.container);
  assert.equal(cards.length, 3);
  assert.deepEqual(cards.map(card => card.getAttribute("aria-label")), ["Revisit words from Photo a", "Revisit words from Photo b", "Revisit words from Photo c"]);
  await waitFor(() => assert.equal(reads.filter(path => path.startsWith("/api/v1/media/")).length, 3));
  for (const [index, sessionId] of ["latest-a", "session-b", "session-c"].entries()) {
    await act(async () => cards[index].click());
    assert.equal(view.container.querySelector("output")?.textContent, `/practice/sessions/${sessionId}/review`);
  }
  assert.deepEqual(window._uxa, [1, 2, 3].map(position => ["trackCustomEvent", "home_explore_vocabulary_clicked", { source: "photo", position }]));
});

test("no completed photo offers the vocabulary fallback without presenting a stock photo as learner history", async () => {
  const view = await mount(state({ progress: { scenarios: [], streak: { days: [] }, leaderboard: [], xp: 0 } }), []);
  assert.equal(photoCards(view.container).length, 0);
  const fallback = [...view.container.querySelectorAll<HTMLButtonElement>(".home-explore-card")].find(card => card.textContent?.includes("Your vocabulary"));
  assert.ok(fallback); assert.equal(fallback.querySelector("img"), null);
  await act(async () => fallback.click()); assert.equal(view.container.querySelector("output")?.textContent, "/vocabulary");
});

test("loading or failed progress does not leave stale review links active and a failure can retry", async () => {
  const view = await mount(state({ progressLoading: true }));
  assert.equal(photoCards(view.container).length, 0);
  assert.match(view.container.querySelector(".home-revisit-state")?.textContent ?? "", /Loading revisit photos/);
  await view.render(state({ progressError: "Unavailable" }), vocabulary);
  assert.equal(photoCards(view.container).length, 0);
  const retry = [...view.container.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === "Retry revisit photos");
  assert.ok(retry);
  await act(async () => retry.click());
  await waitFor(() => assert.ok(reads.includes("/api/v1/me/vocabulary")));
  assert.deepEqual(window._uxa, [["trackCustomEvent", "home_revisit_retried", {}]]);
});

test("switching accounts and language profiles replaces all previous photo destinations", async () => {
  const view = await mount(); assert.equal(photoCards(view.container).length, 3);
  const next = state({ user: { id: "other" } as AppState["user"], activeProfile: { id: "french-profile" } as AppState["activeProfile"],
    progress: { scenarios: [scenario("french", "french-session")], streak: { days: [] }, leaderboard: [], xp: 0 } });
  await view.render(next, [word("livre", ["french"])]);
  const cards = photoCards(view.container); assert.equal(cards.length, 1); assert.match(cards[0].textContent ?? "", /Photo french/);
  assert.doesNotMatch(view.container.querySelector(".home-explore__rail")?.textContent ?? "", /Photo a|Photo b|Photo c/);
  await act(async () => cards[0].click()); assert.equal(view.container.querySelector("output")?.textContent, "/practice/sessions/french-session/review");
});

test("an unavailable protected thumbnail keeps an accessible placeholder and its saved review destination", async () => {
  failPhotos = true;
  const view = await mount(state({ progress: { scenarios: [scenario("a")], streak: { days: [] }, leaderboard: [], xp: 0 } }), [word("cup", ["a"])]);
  await waitFor(() => assert.ok(view.container.querySelector('[aria-label="Image unavailable: Photo a"]')));
  await act(async () => photoCards(view.container)[0].click()); assert.equal(view.container.querySelector("output")?.textContent, "/practice/sessions/session-a/review");
});

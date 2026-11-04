import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { AppState } from "../src/state/context.ts";
import type { ChefStandings } from "../src/lib/gamification.ts";
import { gamificationKeys } from "../src/lib/gamification.ts";
import { queryKeys } from "../src/lib/queryKeys.ts";

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
const folder = mkdtempSync(join(tmpdir(), "home-standings-"));
const entry = join(here, `.homeStandings-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter, useLocation } from "react-router-dom";',
  'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
  'export { AppStateContext } from "../src/state/context";',
  'export { Home } from "../src/pages/Home";',
  'export { ChefOfTheDay } from "../src/components/ChefOfTheDay";',
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
    const path = join(folder, "bundle.mjs");
    writeFileSync(path, output[0].code);
    bundled = await import(pathToFileURL(path).href);
  } finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
const { h, act, createRoot, MemoryRouter, useLocation, QueryClient, QueryClientProvider, AppStateContext, Home, ChefOfTheDay } = bundled as {
  h: typeof import("react").createElement; act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  useLocation: typeof import("react-router-dom").useLocation;
  QueryClient: typeof import("@tanstack/react-query").QueryClient;
  QueryClientProvider: typeof import("@tanstack/react-query").QueryClientProvider;
  AppStateContext: typeof import("../src/state/context.ts").AppStateContext;
  Home: typeof import("../src/pages/Home.tsx").Home;
  ChefOfTheDay: typeof import("../src/components/ChefOfTheDay.tsx").ChefOfTheDay;
};
const originalFetch = globalThis.fetch;
let calls = 0;
let respond: () => Promise<Response>;
const standings = (currentRank: number | null): ChefStandings => ({
  competitionDay: "2026-10-21", dayEndsAt: "2026-10-22T00:00:00Z", todayBasil: 20,
  personalBest: 50, currentRank, basilToNextRank: 5, top: [],
});
globalThis.fetch = async input => {
  if (new URL(String(input)).pathname === "/api/v1/ispy/photos") return Response.json({ photos: [], nextCursor: null });
  if (new URL(String(input)).pathname === "/api/v1/ispy/games/active") return Response.json(null);
  assert.equal(new URL(String(input)).pathname, "/api/v1/me/chef-of-the-day");
  calls += 1;
  return respond();
};
test.beforeEach(() => { calls = 0; respond = async () => Response.json(standings(7)); window._uxa = []; });
const cleanups = new Set<() => Promise<void>>();
test.afterEach(async () => { for (const cleanup of [...cleanups]) await cleanup(); });
test.after(() => {
  globalThis.fetch = originalFetch;
  dom.window.close();
  for (const channel of channels) { channel.port1.close(); channel.port2.close(); }
  globalThis.MessageChannel = NativeMessageChannel;
});

function CurrentRoute() {
  return h("output", { "aria-label": "Current route" }, useLocation().pathname);
}

async function mount() {
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, gcTime: Infinity } } });
  client.setQueryData(queryKeys.vocabulary("profile"), []);
  client.setQueryData(queryKeys.activeSession("profile"), null);
  client.setQueryData(gamificationKeys.summary("learner", "profile"), { basil: { lifetime: 100 }, missions: [] });
  const state = { user: { id: "learner", onboardingCompleted: false }, activeProfile: { id: "profile" },
    learner: { name: "Learner" }, progressLoading: false, progressError: null,
    progress: { streak: { days: [] }, scenarios: [], leaderboard: [{ rank: 42, isYou: true }] },
  } as unknown as AppState;
  await act(async () => root.render(h(QueryClientProvider, { client }, h(AppStateContext.Provider, { value: state },
    h(MemoryRouter, null, h(Home), h(ChefOfTheDay), h(CurrentRoute))))));
  const cleanup = async () => {
    await act(async () => root.unmount());
    client.clear(); container.remove(); cleanups.delete(cleanup);
  };
  cleanups.add(cleanup);
  return { container, client };
}
async function waitFor(assertion: () => void) {
  const deadline = Date.now() + 2_000;
  let failure: unknown;
  do {
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
    try { assertion(); return; } catch (error) { failure = error; }
  } while (Date.now() < deadline);
  throw failure;
}
const homeStanding = (container: HTMLElement) => container.querySelector(".home-league small")?.textContent;
const playStanding = (container: HTMLElement) => container.querySelector('[aria-label="Your leaderboard position"] strong')?.textContent;

test("Home and I-Spy show today's Basil rank instead of the weekly XP rank", async () => {
  const view = await mount();
  await waitFor(() => assert.equal(playStanding(view.container), "#7"));
  assert.equal(homeStanding(view.container), "Your current standing: #7");
  assert.equal(calls, 1, "both surfaces share the account standings request");
});

test("pending standings never fall back to the weekly XP rank", async () => {
  let resolve!: (response: Response) => void;
  respond = () => new Promise(done => { resolve = done; });
  const view = await mount();
  assert.equal(homeStanding(view.container), "Loading your standing");
  assert.equal(view.container.querySelector(".home-league")?.getAttribute("aria-busy"), "true");
  await act(async () => resolve(Response.json(standings(3))));
  await waitFor(() => assert.equal(homeStanding(view.container), "Your current standing: #3"));
});

test("a failed standings request shows an unavailable state without an XP rank", async () => {
  respond = async () => Response.json({ detail: { message: "Unavailable" } }, { status: 503 });
  const view = await mount();
  await waitFor(() => assert.equal(homeStanding(view.container), "Your standing is unavailable."));
  assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /load today’s leaderboard/);
  assert.doesNotMatch(view.container.querySelector(".home-league")?.textContent ?? "", /#42/);
});

test("a learner without Basil today sees an unranked state rather than an XP rank", async () => {
  respond = async () => Response.json(standings(null));
  const view = await mount();
  await waitFor(() => assert.equal(playStanding(view.container), "#—"));
  assert.equal(homeStanding(view.container), "Earn Basil to join today’s board.");
});

test("Basil invalidation refreshes both surfaces through their shared account query", async () => {
  const view = await mount();
  await waitFor(() => assert.equal(playStanding(view.container), "#7"));
  respond = async () => Response.json(standings(2));
  await act(async () => { await view.client.invalidateQueries({ queryKey: gamificationKeys.account("learner") }); });
  await waitFor(() => assert.equal(homeStanding(view.container), "Your current standing: #2"));
  assert.equal(playStanding(view.container), "#2");
  assert.equal(calls, 2);
});

test("the Home standings card opens Play and records the navigation", async () => {
  const view = await mount();
  await waitFor(() => assert.equal(homeStanding(view.container), "Your current standing: #7"));
  const link = view.container.querySelector<HTMLButtonElement>(".home-league");
  assert.ok(link);
  await act(async () => link.click());
  assert.equal(view.container.querySelector('[aria-label="Current route"]')?.textContent, "/ispy");
  assert.deepEqual(window._uxa, [["trackCustomEvent", "home_chef_standings_clicked", {}]]);
});

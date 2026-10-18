import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import test from "node:test";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { PracticeDetail } from "../src/lib/api.ts";

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
const generationReady: PracticeDetail = {
  session: {
    id: SESSION_ID,
    mode: "lesson",
    sourceSessionId: null,
    status: "generatingTasks",
    sceneMediaAssetId: "asset",
    sessionTitle: null,
    sessionSummary: null,
    failureCode: null,
  },
  mediaAsset: { id: "asset", source: "preloaded" },
  sceneId: null,
  title: "Scene",
  analysisMode: null,
  analysisRetryable: false,
  generationRetryable: false,
  sceneObjects: [],
  sceneObjectRelations: [],
  sceneActionSuggestions: [],
  scenePriceSuggestions: [],
  vocabulary: [],
  translations: [],
  translationPreview: { objects: [], attributes: [], relationships: [] },
  tasks: [],
  nextTaskId: null,
  progress: { completedTaskCount: 0, skippedTaskCount: 0, terminalTaskCount: 0, totalTaskCount: 0 },
};

function detail(options: {
  analysisRetryable?: boolean;
  generationRetryable?: boolean;
  failureCode?: PracticeDetail["session"]["failureCode"];
} = {}): PracticeDetail {
  return {
    ...generationReady,
    session: {
      ...generationReady.session,
      status: "failed",
      failureCode: options.failureCode ?? "taskGenerationFailed",
    },
    analysisRetryable: options.analysisRetryable ?? false,
    generationRetryable: options.generationRetryable ?? false,
    translationPreview: null,
  };
}

let fixture = detail({ generationRetryable: true });
const requests: { path: string; method: string }[] = [];
const apiFixtures: Record<string, unknown> = {
  "/api/v1/me": {
    id: "u1", createdAt: "2026-01-01", updatedAt: "2026-01-01", authProviderId: "test",
    displayName: "Learner", email: null, timezone: "UTC", onboardingCompleted: true,
    learningGoal: "practice", microphoneEnabled: true, cameraEnabled: true,
  },
  "/api/v1/me/language-profiles": [{
    id: "p1", userId: "u1", sourceLanguageCode: "en", targetLanguageCode: "es",
    proficiencyLevel: "A1", isActive: true, dailyGoalMinutes: 10, preferredInputMode: "both",
  }],
  "/api/v1/me/vocabulary": { items: [], nextCursor: null },
  "/api/v1/me/progress": { xp: 0, scenarios: [] },
  "/api/v1/preloaded-scenes": [],
  "/api/v1/journals": [],
};

globals.fetch = async (input: unknown, init?: RequestInit) => {
  const url = typeof input === "string" ? input : (input as Request).url;
  const path = url.replace(/^https?:\/\/[^/]+/, "");
  const method = init?.method ?? "GET";
  requests.push({ path, method });
  if (path === `/api/v1/sessions/${SESSION_ID}/retry-analysis`) {
    fixture = generationReady;
    return Response.json(generationReady);
  }
  if (path === `/api/v1/sessions/${SESSION_ID}`) return Response.json(fixture);
  if (path.startsWith("/api/v1/media/")) return new Response(new Blob(["image"], { type: "image/jpeg" }));
  if (path in apiFixtures) return Response.json(apiFixtures[path]);
  return new Response("not found", { status: 404 });
};

const here = dirname(fileURLToPath(import.meta.url));
const workdir = mkdtempSync(join(tmpdir(), "practice-analysis-recovery-"));
const entryPath = join(here, ".practiceAnalysisRecovery.entry.ts");
writeFileSync(entryPath, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";',
  'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
  `export { SessionRoute } from "${pathToFileURL(join(here, "../src/components/SessionRoute")).href}";`,
  `export { PracticeAnalysis } from "${pathToFileURL(join(here, "../src/pages/PracticeAnalysis")).href}";`,
  `export { AppStateProvider } from "${pathToFileURL(join(here, "../src/state/AppState")).href}";`,
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
  h, act, createRoot, MemoryRouter, Route, Routes, useLocation,
  QueryClient, QueryClientProvider, SessionRoute, PracticeAnalysis, AppStateProvider,
} = bundled as Record<string, never> as {
  h: typeof import("react").createElement;
  act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  Route: typeof import("react-router-dom").Route;
  Routes: typeof import("react-router-dom").Routes;
  useLocation: typeof import("react-router-dom").useLocation;
  QueryClient: typeof import("@tanstack/react-query").QueryClient;
  QueryClientProvider: typeof import("@tanstack/react-query").QueryClientProvider;
  SessionRoute: typeof import("../src/components/SessionRoute.tsx").SessionRoute;
  PracticeAnalysis: typeof import("../src/pages/PracticeAnalysis.tsx").PracticeAnalysis;
  AppStateProvider: typeof import("../src/state/AppState.tsx").AppStateProvider;
};

let mountedRoot: ReturnType<typeof createRoot> | null = null;
const mountedClients: InstanceType<typeof QueryClient>[] = [];

function PracticeStub() {
  const location = useLocation();
  return h("pre", { "data-testid": "practice-state" }, JSON.stringify({
    pathname: location.pathname,
    state: location.state,
  }));
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
const flush = () => act(async () => { await sleep(30); });
const body = () => dom.window.document.body.textContent ?? "";
const button = (label: string) => [...dom.window.document.querySelectorAll("button")]
  .find(item => item.textContent?.trim() === label);

test.after(async () => {
  if (mountedRoot) await act(async () => { mountedRoot!.unmount(); });
  for (const client of mountedClients) client.clear();
  dom.window.close();
  for (const handle of (process as unknown as { _getActiveHandles(): { unref?: () => void }[] })._getActiveHandles()) {
    handle.unref?.();
  }
});

async function mount(path = `${BASE}/analysis`) {
  if (mountedRoot) await act(async () => { mountedRoot!.unmount(); });
  dom.window.document.body.innerHTML = "";
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  mountedRoot = root;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  mountedClients.push(client);
  await act(async () => root.render(
    h(QueryClientProvider, { client },
      h(AppStateProvider, null,
        h(MemoryRouter, { initialEntries: [path] },
          h(Routes, null,
            h(Route, { path: "/practice/sessions/:sessionId", element: h(SessionRoute) },
              h(Route, { path: "analysis", element: h(PracticeAnalysis) }),
            ),
            h(Route, { path: "/practice", element: h(PracticeStub) }),
          ),
        ),
      ),
    ),
  ));
  await flush();
  return root;
}

test("retryable task generation can be retried into the generating UI", async () => {
  fixture = detail({ generationRetryable: true });
  requests.length = 0;
  const root = await mount();
  assert.match(body(), /We couldn't build your lesson/);
  const retry = button("Try again");
  assert.ok(retry);
  await act(async () => {
    retry.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    await sleep(50);
  });
  await flush();
  assert.ok(requests.some(request => request.path === `/api/v1/sessions/${SESSION_ID}/retry-analysis` && request.method === "POST"));
  assert.match(body(), /Preparing your first task/);
  await act(async () => root.unmount());
});

test("Back to Practice preserves the retry session without abandoning or deleting it", async () => {
  fixture = detail({ generationRetryable: true });
  requests.length = 0;
  const root = await mount();
  const back = button("Back to Practice");
  assert.ok(back);
  await act(async () => back.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })));
  await flush();
  const state = dom.window.document.querySelector("[data-testid=practice-state]")?.textContent;
  assert.ok(state);
  assert.deepEqual(JSON.parse(state), {
    pathname: "/practice",
    state: {
      practiceNotice: "Your photo and your review are still saved. You can try building the lesson again or choose another photo.",
      retrySessionId: SESSION_ID,
    },
  });
  assert.equal(requests.some(request => request.path.includes("/abandon") || request.method === "DELETE"), false);
  await act(async () => root.unmount());
});

test("exhausted task-generation failures return to practice with a notice", async () => {
  fixture = detail({ generationRetryable: false });
  requests.length = 0;
  const root = await mount();
  assert.equal(button("Try again"), undefined);
  assert.match(body(), /couldn't build your lesson/);
  assert.ok(dom.window.document.querySelector("[data-testid=practice-state]"));
  await act(async () => root.unmount());
});

test("retryable scene-analysis failures keep their existing copy and action", async () => {
  fixture = detail({ failureCode: "sceneAnalysisFailed", analysisRetryable: true });
  requests.length = 0;
  const root = await mount();
  assert.match(body(), /We couldn't analyse that photo/);
  assert.ok(button("Try again"));
  assert.ok(button("Choose another photo"));
  assert.equal(button("Back to Practice"), undefined);
  await act(async () => root.unmount());
});

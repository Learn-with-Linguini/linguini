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
    status, isSkippable: true, orderIndex, publicContent, vocabularyItemId: null, sceneObjectId: null };
}

const fixture = detail("inProgress", [task("learn", "completed", 0), task("clues", "completed", 1), task("reflection", "completed", 2)]);

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

globals.fetch = async (input: unknown) => {
  const url = typeof input === "string" ? input : (input as Request).url;
  const path = url.replace(/^https?:\/\/[^/]+/, "");
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
  `export { SessionRoute } from "${join(here, "../src/components/SessionRoute")}";`,
  `export { ISpyPhase2 } from "${join(here, "../src/pages/ISpyPhase2")}";`,
  `export { AppStateProvider } from "${join(here, "../src/state/AppState")}";`,
  `export { useAppState } from "${join(here, "../src/state/useAppState")}";`,
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

import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import test from "node:test";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { LanguageProfile } from "../src/lib/api.ts";

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
Object.defineProperty(globalThis, "localStorage", { value: dom.window.localStorage, configurable: true });
globals.IS_REACT_ACT_ENVIRONMENT = true;
// Profile's polling queries (refetchInterval) can leave a timer behind after unmount; don't let it keep node alive.
const setIntervalRef = globalThis.setInterval;
globalThis.setInterval = ((...args: Parameters<typeof setInterval>) => {
  const timer = setIntervalRef(...args);
  timer.unref?.();
  return timer;
}) as typeof setInterval;

const user = { id: "u1", createdAt: "2026-01-01", updatedAt: "2026-01-01", authProviderId: "test", displayName: "Learner", email: null, timezone: "UTC", onboardingCompleted: true, learningGoal: "Travel confidently", microphoneEnabled: false, cameraEnabled: false };
let profiles: LanguageProfile[] = [];
let basilState: "ready" | "loading" | "error" = "ready";
let profilePatches: { id: string; body: Record<string, unknown> }[] = [];

function profile(id: string, targetLanguageCode: string, isActive: boolean): LanguageProfile {
  return { id, userId: "u1", sourceLanguageCode: "en", targetLanguageCode, proficiencyLevel: "A2", isActive, dailyGoalMinutes: 20, preferredInputMode: "both" } as LanguageProfile;
}

globals.fetch = async (input: unknown, init?: RequestInit) => {
  const url = typeof input === "string" ? input : (input as Request).url;
  const path = url.replace(/^https?:\/\/[^/]+/, "");
  const method = init?.method ?? "GET";
  if (path === "/api/v1/me") return Response.json(user);
  // Practice languages come only from pack discovery.
  if (path === "/api/v1/me/practice-languages") return Response.json(["es", "fr", "de", "ko"].map(code => ({ code, levels: ["A0", "A1", "A2"], experimental: true })));
  if (path === "/api/v1/me/language-profiles") return Response.json(profiles);
  if (path === "/api/v1/me/progress") return Response.json({ xp: 2, leaderboard: [{ isYou: true, xp: 300 }] });
  if (path.startsWith("/api/v1/me/gamification?")) {
    if (basilState === "loading") return new Promise<Response>(() => {});
    if (basilState === "error") return new Response("unavailable", { status: 503 });
    return Response.json({ basil: { today: 10, weekly: 25, lifetime: 75, balance: 55 }, missions: [] });
  }
  const patch = path.match(/^\/api\/v1\/me\/language-profiles\/([^/]+)$/);
  if (patch && method === "PATCH") {
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    profilePatches.push({ id: patch[1], body });
    if (body.isActive) profiles = profiles.map(row => ({ ...row, isActive: row.id === patch[1] }));
    return Response.json(profiles.find(row => row.id === patch[1]));
  }
  return new Response("not found", { status: 404 });
};

// .tsx sources can't run under node --experimental-strip-types, so the mounted
// surface is bundled once with rolldown (the vite bundler already in devDeps).
const here = dirname(fileURLToPath(import.meta.url));
const workdir = mkdtempSync(join(tmpdir(), "profile-language-"));
// The entry must live under frontend/ so bare imports resolve node_modules here.
const entryPath = join(here, ".profileLanguageSwitch.entry.ts");
writeFileSync(entryPath, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter, Route, Routes } from "react-router-dom";',
  'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
  `export { Profile } from "${pathToFileURL(join(here, "../src/pages/Profile")).href}";`,
  `export { AppStateProvider } from "${pathToFileURL(join(here, "../src/state/AppState")).href}";`,
  `export { AuthProvider } from "${pathToFileURL(join(here, "../src/state/Auth")).href}";`,
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
const { h, act, createRoot, MemoryRouter, Route, Routes, QueryClient, QueryClientProvider, Profile, AppStateProvider, AuthProvider } = bundled as Record<string, never> as {
  h: typeof import("react").createElement;
  act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  Route: typeof import("react-router-dom").Route;
  Routes: typeof import("react-router-dom").Routes;
  QueryClient: typeof import("@tanstack/react-query").QueryClient;
  QueryClientProvider: typeof import("@tanstack/react-query").QueryClientProvider;
  Profile: typeof import("../src/pages/Profile.tsx").Profile;
  AppStateProvider: typeof import("../src/state/AppState.tsx").AppStateProvider;
  AuthProvider: typeof import("../src/state/Auth.tsx").AuthProvider;
};

const flush = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 30)); });
// Basil loads only after the account does; wait for it rather than one fixed tick, so a
// slower runner sees the same screen. On timeout the assertion reports what is shown.
const waitFor = async (ready: () => boolean, timeoutMs = 2000) => {
  const started = Date.now();
  while (!ready() && Date.now() - started < timeoutMs) await flush();
};
const page = () => dom.window.document.querySelector("[data-testid]")?.getAttribute("data-testid") ?? "profile";
const languageSelect = () => {
  const select = [...dom.window.document.querySelectorAll("select")].find(element => element.textContent?.includes("Spanish"));
  assert.ok(select, "the target language picker is on screen");
  return select;
};
const chooseLanguage = async (code: string) => {
  const select = languageSelect();
  await act(async () => {
    select.value = code;
    select.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  });
  await flush();
};
const click = async (label: string) => {
  const button = [...dom.window.document.querySelectorAll("button")].find(element => element.textContent?.trim() === label);
  assert.ok(button, `button "${label}" is on screen`);
  await act(async () => { button.click(); });
  await flush();
};

test.after(() => {
  dom.window.close();
  for (const handle of (process as unknown as { _getActiveHandles(): { unref?: () => void }[] })._getActiveHandles()) {
    handle.unref?.();
  }
});

async function withProfilePage(run: () => Promise<void>) {
  dom.window.document.body.innerHTML = "";
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  // Cache GC timers outlive the test and keep node alive, so never schedule them.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { gcTime: Infinity } } });
  try {
    await act(async () => {
      root.render(
        h(QueryClientProvider, { client },
          h(AuthProvider, null,
            h(MemoryRouter, { initialEntries: ["/profile"] },
              h(Routes, null,
                h(Route, { path: "/profile", element: h(AppStateProvider, null, h(Profile)) }),
                h(Route, { path: "/onboarding", element: h("div", { "data-testid": "onboarding" }) }),
              ),
            ),
          ),
        ),
      );
    });
    await flush();
    await run();
  } finally {
    await act(async () => { root.unmount(); });
    client.clear();
  }
}

test("switching back to an already set-up language activates it without onboarding", async () => {
  profiles = [profile("p1", "es", false), profile("p2", "fr", true)];
  profilePatches = [];
  await withProfilePage(async () => {
    assert.equal(languageSelect().value, "fr");
    await chooseLanguage("es");
    await click("Switch to Spanish");

    assert.equal(page(), "profile");
    assert.deepEqual(profilePatches, [{ id: "p1", body: { isActive: true } }]);
    assert.equal(languageSelect().value, "es");
  });
});

test("choosing a language that has never been set up still starts onboarding", async () => {
  profiles = [profile("p1", "es", false), profile("p2", "fr", true)];
  profilePatches = [];
  await withProfilePage(async () => {
    await chooseLanguage("de");
    await click("Set up German");

    assert.equal(page(), "onboarding");
    assert.deepEqual(profilePatches, []);
  });
});

test("profile shows earned Basil from one ledger instead of legacy XP or spendable balance", async () => {
  profiles = [profile("p1", "es", true), profile("p2", "fr", false)];
  basilState = "ready";
  await withProfilePage(async () => {
    const totals = () => [...dom.window.document.querySelectorAll(".profile-basil__grid strong")].map(node => node.textContent);
    await waitFor(() => totals().length === 2);
    assert.deepEqual(totals(), ["25", "75"]);
    await chooseLanguage("fr");
    await click("Switch to French");
    await waitFor(() => totals().length === 2);
    assert.deepEqual(totals(), ["25", "75"]);
  });
});

for (const pending of ["loading", "error"] as const) {
  test(`profile does not substitute XP or zero when Basil is ${pending}`, async () => {
    profiles = [profile("p1", "es", true)];
    basilState = pending;
    try {
      await withProfilePage(async () => {
        const section = dom.window.document.querySelector(".profile-basil");
        assert.ok(section);
        if (pending === "error") await waitFor(() => /couldn’t load your Basil/.test(section.textContent ?? ""));
        assert.equal(section.querySelectorAll("strong").length, 0);
        assert.match(section.textContent ?? "", pending === "loading" ? /Loading your Basil/ : /couldn’t load your Basil/);
      });
    } finally { basilState = "ready"; }
  });
}

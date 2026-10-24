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
// Node ships its own localStorage global; the onboarding draft must land in the DOM's.
Object.defineProperty(globalThis, "localStorage", { value: dom.window.localStorage, configurable: true });
globals.IS_REACT_ACT_ENVIRONMENT = true;

const user = { id: "u1", createdAt: "2026-01-01", updatedAt: "2026-01-01", authProviderId: "test", displayName: "Learner", email: null, timezone: "UTC", onboardingCompleted: true, learningGoal: "Travel confidently", microphoneEnabled: false, cameraEnabled: false };
let profiles: LanguageProfile[] = [];

function profile(id: string, targetLanguageCode: string, isActive: boolean): LanguageProfile {
  return { id, userId: "u1", sourceLanguageCode: "en", targetLanguageCode, proficiencyLevel: "A1", isActive, dailyGoalMinutes: 10, preferredInputMode: "both" } as LanguageProfile;
}

globals.fetch = async (input: unknown, init?: RequestInit) => {
  const url = typeof input === "string" ? input : (input as Request).url;
  const path = url.replace(/^https?:\/\/[^/]+/, "");
  const method = init?.method ?? "GET";
  if (path === "/api/v1/me") return Response.json(user);
  // Practice languages come only from pack discovery.
  if (path === "/api/v1/me/practice-languages") return Response.json(["es", "fr", "de", "ko"].map(code => ({ code, levels: ["A0", "A1", "A2"], experimental: true })));
  if (path === "/api/v1/onboarding/placement" && method === "POST") return Response.json({ proficiencyLevel: "A0", message: "ok" });
  if (path === "/api/v1/me/language-profiles" && method === "POST") {
    // The server activates a newly created profile, which changes the active profile id.
    const body = JSON.parse(String(init?.body)) as { targetLanguageCode: string };
    const created = profile(`p${profiles.length + 1}`, body.targetLanguageCode, true);
    profiles = [...profiles.map(row => ({ ...row, isActive: false })), created];
    return Response.json(created);
  }
  if (path === "/api/v1/me/language-profiles") return Response.json(profiles);
  if (path === "/api/v1/me/progress") return Response.json({ xp: 0, scenarios: [] });
  return new Response("not found", { status: 404 });
};

// .tsx sources can't run under node --experimental-strip-types, so the mounted
// surface is bundled once with rolldown (the vite bundler already in devDeps).
const here = dirname(fileURLToPath(import.meta.url));
const workdir = mkdtempSync(join(tmpdir(), "onboarding-language-"));
// The entry must live under frontend/ so bare imports resolve node_modules here.
const entryPath = join(here, ".onboardingLanguageChange.entry.ts");
writeFileSync(entryPath, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter, Route, Routes } from "react-router-dom";',
  'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
  `export { OnboardingPage } from "${pathToFileURL(join(here, "../src/pages/Onboarding")).href}";`,
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
const { h, act, createRoot, MemoryRouter, Route, Routes, QueryClient, QueryClientProvider, OnboardingPage } = bundled as Record<string, never> as {
  h: typeof import("react").createElement;
  act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  Route: typeof import("react-router-dom").Route;
  Routes: typeof import("react-router-dom").Routes;
  QueryClient: typeof import("@tanstack/react-query").QueryClient;
  QueryClientProvider: typeof import("@tanstack/react-query").QueryClientProvider;
  OnboardingPage: typeof import("../src/pages/Onboarding.tsx").OnboardingPage;
};

const flush = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 30)); });
const heading = () => dom.window.document.querySelector("h1")?.textContent ?? "";
const click = async (label: string) => {
  const button = [...dom.window.document.querySelectorAll("button")].find(element => element.textContent?.includes(label));
  assert.ok(button, `button "${label}" is on screen (showing "${heading()}")`);
  await act(async () => { button.click(); });
  await flush();
};

test.after(() => {
  dom.window.close();
  for (const handle of (process as unknown as { _getActiveHandles(): { unref?: () => void }[] })._getActiveHandles()) {
    handle.unref?.();
  }
});

test("finishing a language change shows the success screen instead of restarting onboarding", async () => {
  profiles = [profile("p1", "es", true)];
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  // Cache GC timers outlive the test and keep node alive, so never schedule them.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { gcTime: Infinity } } });
  try {
    await act(async () => {
      root.render(
        h(QueryClientProvider, { client },
          h(MemoryRouter, { initialEntries: [{ pathname: "/onboarding", state: { from: "/profile", languageChangeCode: "fr" } }] },
            h(Routes, null,
              h(Route, { path: "/onboarding", element: h(OnboardingPage) }),
              h(Route, { path: "/profile", element: h("h1", null, "Profile page") }),
            ),
          ),
        ),
      );
    });
    await flush();

    assert.equal(heading(), "How much French do you know?");
    await click("I’m a complete beginner");
    assert.equal(heading(), "What are you practising for?");
    await click("Chat with neighbours");
    await click("Continue");
    assert.equal(heading(), "One last thing");
    await click("Finish setup");

    // Saving activates the new French profile; the onboarding flow must survive that switch.
    assert.equal(profiles.find(row => row.isActive)?.targetLanguageCode, "fr");
    assert.equal(heading(), "You’re all set!");
    assert.equal(dom.window.localStorage.getItem("linguini-onboarding-draft-u1"), null);

    await click("Go to home");
    assert.equal(heading(), "Profile page");
  } finally {
    await act(async () => { root.unmount(); });
    client.clear();
  }
});

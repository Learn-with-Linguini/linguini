import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import test from "node:test";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { SceneShortfall, ShortfallKind } from "../src/lib/api.ts";
import { closestMissions, parseShortfall, shortfallFromError } from "../src/lib/sceneShortfall.ts";

const detail = {
  code: "insufficient_scene",
  message: "This photo doesn't have enough for Linguini to check a lesson yet.",
  missing: ["counts", "attributes", "bogus"],
  missions: [
    { missionId: "M03", title: "Count objects", missing: ["counts"], reasons: ["Count a group of 2 to 3 matching objects."] },
    { missionId: "M01", title: "Identify and describe an object", missing: ["attributes"], reasons: ["Confirm a colour of at least one object."] },
    { missionId: "M02", title: "Say where things are", missing: ["attributes", "relations"], reasons: ["Confirm where one object is."] },
  ],
};

test("a rejected review's detail becomes a validated shortfall", () => {
  const shortfall = shortfallFromError({ status: 422, code: "insufficient_scene", detail });
  assert.deepEqual(shortfall?.missing, ["counts", "attributes"]);
  assert.equal(shortfall?.missions.length, 3);
  // Only the missions that need nothing beyond what the learner is asked to add.
  assert.deepEqual(closestMissions(shortfall!).map(mission => mission.missionId), ["M03", "M01"]);
});

test("other errors and malformed details are not shortfalls", () => {
  assert.equal(shortfallFromError({ status: 409, code: "practice_conflict", detail }), null);
  assert.equal(shortfallFromError(new Error("offline")), null);
  assert.equal(parseShortfall({ missing: [] }), null);
  assert.equal(parseShortfall({ missing: ["colours"] }), null);
  assert.deepEqual(parseShortfall({ missing: ["relations"], missions: [{ title: "No id" }] }), { missing: ["relations"], missions: [] });
});

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/", pretendToBeVisual: true });
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

// .tsx sources can't run under node --experimental-strip-types, so the notice is bundled once.
const here = dirname(fileURLToPath(import.meta.url));
const workdir = mkdtempSync(join(tmpdir(), "scene-shortfall-"));
const entryPath = join(here, ".sceneShortfall.entry.ts");
writeFileSync(entryPath, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter } from "react-router-dom";',
  `export { SceneShortfallNotice } from "${pathToFileURL(join(here, "../src/components/SceneShortfallNotice")).href}";`,
].join("\n"));
let bundleCode: string;
try {
  const bundler = await rolldown({
    input: entryPath,
    platform: "node",
    resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{
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
const { h, act, createRoot, MemoryRouter, SceneShortfallNotice } = bundled as Record<string, never> as {
  h: typeof import("react").createElement;
  act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  SceneShortfallNotice: typeof import("../src/components/SceneShortfallNotice.tsx").SceneShortfallNotice;
};

test.after(() => {
  dom.window.close();
  for (const handle of (process as unknown as { _getActiveHandles(): { unref?: () => void }[] })._getActiveHandles()) {
    handle.unref?.();
  }
});

async function render(shortfall: SceneShortfall, calls: { added: ShortfallKind[]; newPhoto: number }, busy = false) {
  dom.window.document.body.innerHTML = "";
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(h(MemoryRouter, null, h(SceneShortfallNotice, {
      shortfall, busy,
      onAdd: (kind: ShortfallKind) => { calls.added.push(kind); },
      onTryAnotherPhoto: () => { calls.newPhoto += 1; },
    })));
  });
  return root;
}

const button = (label: string) => [...dom.window.document.querySelectorAll("button")]
  .find(item => item.textContent === label) as HTMLButtonElement | undefined;

test("the notice names what is short and offers a way to add each one", async () => {
  const calls = { added: [] as ShortfallKind[], newPhoto: 0 };
  const root = await render(shortfallFromError({ code: "insufficient_scene", detail })!, calls);
  const notice = dom.window.document.querySelector("[role=alert]");
  assert.match(notice?.textContent ?? "", /Add a little more to this photo/);
  assert.match(notice?.textContent ?? "", /any of these/);
  assert.deepEqual([...dom.window.document.querySelectorAll(".scene-shortfall__list strong")].map(item => item.textContent), ["A count", "Adjectives"]);
  assert.equal(button("Add a connection"), undefined);
  await act(async () => { button("Add to a count")!.click(); });
  await act(async () => { button("Add adjectives")!.click(); });
  await act(async () => { button("Try another photo")!.click(); });
  assert.deepEqual(calls.added, ["counts", "attributes"]);
  assert.equal(calls.newPhoto, 1);
  const tips = dom.window.document.querySelector(".scene-shortfall__missions")?.textContent ?? "";
  assert.match(tips, /Count objects: Count a group of 2 to 3 matching objects\./);
  assert.doesNotMatch(tips, /Say where things are/);
  await act(async () => { root.unmount(); });
});

test("a generation-time shortfall with no mission detail still offers every kind", async () => {
  const calls = { added: [] as ShortfallKind[], newPhoto: 0 };
  const root = await render({ missing: ["objects", "counts", "attributes", "relations"], missions: [] }, calls, true);
  assert.deepEqual([...dom.window.document.querySelectorAll(".scene-shortfall__list strong")].map(item => item.textContent),
    ["More objects", "A count", "Adjectives", "Connections"]);
  assert.equal(dom.window.document.querySelector(".scene-shortfall__missions"), null);
  // While a review is saving, the notice's actions wait.
  assert.ok([...dom.window.document.querySelectorAll("button")].every(item => item.disabled));
  await act(async () => { root.unmount(); });
});

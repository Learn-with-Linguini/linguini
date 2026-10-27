import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { PracticeDetail, PracticeReview } from "../src/lib/api.ts";
import type { Scene } from "../src/data/types.ts";
import type { AppState } from "../src/state/context.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
Object.defineProperty(globalThis, "window", { value: dom.window, configurable: true });
Object.defineProperty(globalThis, "document", { value: dom.window.document, configurable: true });
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
dom.window.HTMLElement.prototype.scrollIntoView = () => {};
Object.defineProperty(dom.window, "matchMedia", { value: () => ({ matches: true }) });
const NativeMessageChannel = globalThis.MessageChannel;
const messageChannels: MessageChannel[] = [];
globalThis.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); messageChannels.push(this); }
};

// Bundle the real page once, as node's type stripping does not support TSX.
const here = dirname(fileURLToPath(import.meta.url));
const workdir = mkdtempSync(join(tmpdir(), "practice-analysis-"));
const entry = join(here, ".practiceAnalysis.entry.ts");
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter, Route, Routes, Outlet } from "react-router-dom";',
  `export { PracticeAnalysis } from "${pathToFileURL(join(here, "../src/pages/PracticeAnalysis")).href}";`,
  `export { AppStateContext } from "${pathToFileURL(join(here, "../src/state/context")).href}";`,
].join("\n"));
let bundled: unknown;
try {
  const bundler = await rolldown({
    input: entry,
    platform: "node",
    resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{
      name: "stub-css",
      resolveId: (id: string) => id.endsWith(".css") ? "\0empty-css" : null,
      load: (id: string) => id === "\0empty-css" ? "export default {};" : null,
    }],
  });
  const { output } = await bundler.generate({ format: "esm" });
  await bundler.close();
  const bundlePath = join(workdir, "bundle.mjs");
  writeFileSync(bundlePath, output[0].code);
  bundled = await import(pathToFileURL(bundlePath).href);
} finally {
  rmSync(entry, { force: true });
  rmSync(workdir, { recursive: true, force: true });
}
const { h, act, createRoot, MemoryRouter, Route, Routes, Outlet, PracticeAnalysis, AppStateContext } = bundled as {
  h: typeof import("react").createElement;
  act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  Route: typeof import("react-router-dom").Route;
  Routes: typeof import("react-router-dom").Routes;
  Outlet: typeof import("react-router-dom").Outlet;
  PracticeAnalysis: typeof import("../src/pages/PracticeAnalysis.tsx").PracticeAnalysis;
  AppStateContext: typeof import("../src/state/context.ts").AppStateContext;
};

const scene: Scene = {
  id: "scene", sessionId: "session", mediaAssetId: "photo", imageUrl: "/photo.jpg",
  languageCode: "es", language: "Spanish", title: "Kitchen", blurb: "",
  items: ["table", "cup", "cup"].map((word, index) => ({
    id: `object-${index}`, word, translation: word, marker: index + 1, x: 20 + index * 20, y: 40,
    wordClass: "noun", gender: null, example: "", exampleTranslation: "",
  })),
};
const relation = {
  id: "relation", subjectSceneObjectId: "object-1", referenceSceneObjectId: "object-2",
  relation: "nextTo", sourceRelationKey: "original-relation",
};
function detail(): PracticeDetail {
  return {
    session: { id: "session", mode: "lesson", sourceSessionId: null, status: "awaitingObjectReview",
      sceneMediaAssetId: "photo", sessionTitle: null, sessionSummary: null, failureCode: null },
    mediaAsset: { id: "photo", source: "userUpload" }, sceneId: null, title: "Kitchen",
    analysisMode: null, analysisRetryable: false, sceneObjectRelations: [relation],
    sceneActionSuggestions: [], scenePriceSuggestions: [],
    sceneObjects: scene.items.map(item => ({ id: item.id, sessionId: "session", label: item.translation,
      vocabularyItemId: null, boundingBox: null, anchorPoint: { x: item.x / 100, y: item.y / 100 },
      attributes: item.translation === "cup" ? { quantity: "two", color: "white" } : {},
      confidenceScore: null, sourceObjectKey: item.id })),
    vocabulary: [], translations: [], translationPreview: null, tasks: [], nextTaskId: null,
    progress: { completedTaskCount: 0, skippedTaskCount: 0, terminalTaskCount: 0, totalTaskCount: 0 },
  };
}

let root: ReturnType<typeof createRoot> | null = null;
let reviews: PracticeReview[] = [];
async function mount(session = detail()) {
  reviews = [];
  const state = { session, practiceSaving: false, practiceError: null, practiceStalled: false,
    saveReview: async (review: PracticeReview) => { reviews.push(review); },
  } as unknown as AppState;
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root!.render(h(MemoryRouter, { initialEntries: ["/analysis"] },
      h(AppStateContext.Provider, { value: state },
        h(Routes, null, h(Route, { element: h(Outlet, { context: scene }) },
          h(Route, { path: "/analysis", element: h(PracticeAnalysis) }))))));
  });
}
async function click(element: Element | null) {
  assert.ok(element, "the requested control is present");
  await act(async () => { (element as HTMLElement).click(); });
}
function button(text: string) {
  return [...dom.window.document.querySelectorAll("button")].find(element => element.textContent?.trim() === text) ?? null;
}
async function input(id: string, value: string) {
  const element = dom.window.document.getElementById(id) as HTMLInputElement | null;
  assert.ok(element, `${id} is present`);
  await act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value")!.set!.call(element, value);
    element.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
}
function numbers(selector: string) {
  return [...dom.window.document.querySelectorAll(selector)].map(element => Number(element.textContent));
}
function assertMarkers(expected: number[]) {
  assert.deepEqual(numbers(".analysis-word-row__marker"), expected);
  assert.deepEqual(numbers(".scene__marker-label"), expected);
}
function counts() {
  return Object.fromEntries([...dom.window.document.querySelectorAll(".analysis-object-counts dl > div")]
    .map(group => [group.querySelector("dt")!.textContent, Number(group.querySelector("dd")!.textContent)]));
}
async function addWord(word: string) {
  await input("analysis-new-word", word);
  await click(button("Select location"));
  const photo = dom.window.document.querySelector(".scene[role=button]");
  assert.ok(photo);
  await act(async () => {
    photo.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  });
}

test.afterEach(async () => {
  await act(async () => { root?.unmount(); });
  root = null;
  dom.window.document.body.replaceChildren();
});
test.after(() => {
  dom.window.close();
  for (const channel of messageChannels) { channel.port1.close(); channel.port2.close(); }
  globalThis.MessageChannel = NativeMessageChannel;
});

test("removing and restoring objects keeps their review marker numbers stable", async () => {
  await mount();
  assertMarkers([1, 2, 3]);
  await click(dom.window.document.querySelector('[aria-label="Remove marker 1, table"]'));
  assertMarkers([2, 3]);
  await addWord("window");
  await addWord("door");
  assertMarkers([2, 3, 4, 5]);
  await click(dom.window.document.querySelector('[aria-label="Remove marker 4, window"]'));
  assertMarkers([2, 3, 5]);
  await click(button("Restore removed objects"));
  assertMarkers([1, 2, 3, 5]);
  await click(dom.window.document.querySelector('[aria-label="Remove marker 1, table"]'));
  await click(button("Confirm lesson facts"));
  assert.equal(reviews.length, 1);
  assert.deepEqual(reviews[0].acceptedObjectIds, ["object-1", "object-2"]);
  assert.deepEqual(reviews[0].relations, [relation]);
  assert.equal(reviews[0].addedObjects.length, 1);
  assert.equal(reviews[0].addedObjects[0].label, "door");
  assert.deepEqual({ x: reviews[0].addedObjects[0].x, y: reviews[0].addedObjects[0].y }, { x: 0.5, y: 0.5 });
  assert.ok(reviews[0].addedObjects[0].id);
  assert.deepEqual(reviews[0].objectCounts, { "object-1": 2, [reviews[0].addedObjects[0].id]: 1 });
  assert.deepEqual(scene.items.map(item => item.marker), [1, 2, 3]);
});

test("counts live in Objects and follow visible instances after switching details, removing and adding an object", async () => {
  await mount();
  const tabs = [...dom.window.document.querySelectorAll('[role="tab"]')];
  assert.deepEqual(tabs.map(tab => tab.textContent?.replace(/\d/g, "")), ["Objects", "Adjectives", "Relations"]);
  const objects = dom.window.document.querySelector('[aria-labelledby="analysis-found-title"]');
  assert.ok(objects?.querySelector('[aria-labelledby="analysis-object-counts-title"]'));
  assert.deepEqual(counts(), { table: 1, cup: 2 });
  await click(tabs[1]);
  assert.equal(dom.window.document.querySelector(".analysis-object-counts"), null);
  await click(tabs[0]);
  assert.deepEqual(counts(), { table: 1, cup: 2 });
  await click(dom.window.document.querySelector('[aria-label="Remove marker 2, cup"]'));
  assertMarkers([1, 3]);
  assert.deepEqual(counts(), { table: 1, cup: 1 });
  await addWord("cup");
  assertMarkers([1, 3, 4]);
  assert.deepEqual(counts(), { table: 1, cup: 2 });
  await click(button("Confirm lesson facts"));
  assert.deepEqual(reviews[0].acceptedObjectIds, ["object-0", "object-2"]);
  assert.deepEqual(reviews[0].objectCounts, { "object-0": 1, "object-2": 2 });
  assert.deepEqual(reviews[0].relations, []);
});

test("restoring removed objects keeps mission-hidden suggestions excluded from markers and counts", async () => {
  await mount({ ...detail(), suggestedSceneObjectIds: ["object-1", "object-2"],
    provisionalMissionPlan: [{ missionId: "M03", practiceLevel: "A1" }] });
  assert.deepEqual([...dom.window.document.querySelectorAll('[role="tab"]')].map(tab => tab.textContent), ["Objects2", "Adjectives2", "Relations1"]);
  assertMarkers([1, 2]);
  assert.deepEqual(counts(), { cup: 2 });
  await click(dom.window.document.querySelector('[aria-label="Remove marker 1, cup"]'));
  assertMarkers([2]);
  assert.deepEqual(counts(), { cup: 1 });
  await click(button("Restore removed objects"));
  assertMarkers([1, 2]);
  assert.deepEqual(counts(), { cup: 2 });
  await click(button("Confirm lesson facts"));
  assert.deepEqual(reviews[0].acceptedObjectIds, ["object-1", "object-2"]);
  assert.deepEqual(reviews[0].objectCounts, { "object-1": 2 });
  assert.deepEqual(reviews[0].relations, [relation]);
});

test("a learner-added object follows the visible suggestion numbers", async () => {
  await mount({ ...detail(), suggestedSceneObjectIds: ["object-1", "object-2"] });
  assertMarkers([1, 2]);

  await addWord("window");

  assertMarkers([1, 2, 3]);
});

const preferencePlan = [{ missionId: "M05", practiceLevel: "A0" }] as const;

test("personal preference can select either matching object by its stable photo marker", async () => {
  await mount({ ...detail(), provisionalMissionPlan: [...preferencePlan] });
  await click(dom.window.document.getElementById("preference-object"));
  const options = [...dom.window.document.querySelectorAll("#preference-object-options [role=option]")];
  assert.deepEqual(options.map(option => option.textContent), ["1table", "2cup", "3cup"]);
  await click(options[2]);
  await click(button("I don't like it"));
  await click(button("Confirm lesson facts"));
  assert.deepEqual(reviews[0].missionChoices?.preference, {
    sceneObjectIds: ["object-2"], chosenObjectId: null, reaction: "dislike",
  });
});

test("a removed preference object is not sent as the learner's choice", async () => {
  await mount({ ...detail(), provisionalMissionPlan: [...preferencePlan],
    missionChoices: { preference: { sceneObjectIds: ["object-2"], chosenObjectId: null, reaction: "like" } } });
  assert.match(dom.window.document.getElementById("preference-object")!.textContent!, /3cup/);
  await click(dom.window.document.querySelector('[aria-label="Remove marker 3, cup"]'));
  await click(button("Confirm lesson facts"));
  assert.equal(reviews[0].missionChoices, undefined);
});

test("leaving preference empty or clearing a restored choice requests a pretend scenario", async () => {
  await mount({ ...detail(), provisionalMissionPlan: [...preferencePlan] });
  await click(button("Confirm lesson facts"));
  assert.equal(reviews[0].missionChoices, undefined);
  await act(async () => { root?.unmount(); });
  root = null;
  dom.window.document.body.replaceChildren();
  await mount({ ...detail(), provisionalMissionPlan: [...preferencePlan],
    missionChoices: { preference: { sceneObjectIds: ["object-1"], chosenObjectId: null, reaction: "like" } } });
  await click(button("Use a pretend preference"));
  await click(button("Confirm lesson facts"));
  assert.equal(reviews[0].missionChoices, undefined);
});

test("preference picker is only shown for the beginner preference mission", async () => {
  await mount({ ...detail(), provisionalMissionPlan: [{ missionId: "M05", practiceLevel: "A1" }] });
  assert.equal(dom.window.document.getElementById("preference-object"), null);
});

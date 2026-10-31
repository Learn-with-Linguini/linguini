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
import { practiceScene } from "../src/lib/practiceScene.ts";

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
async function mount(session = detail(), stalled = false, currentScene = scene) {
  reviews = [];
  const state = { session, practiceSaving: false, practiceError: null, practiceStalled: stalled,
    saveReview: async (review: PracticeReview) => { reviews.push(review); },
  } as unknown as AppState;
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root!.render(h(MemoryRouter, { initialEntries: ["/analysis"] },
      h(AppStateContext.Provider, { value: state },
        h(Routes, null, h(Route, { element: h(Outlet, { context: currentScene }) },
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

test("removing, adding and restoring objects keeps photo and list numbers contiguous by identity", async () => {
  await mount();
  assertMarkers([1, 2, 3]);
  await click(dom.window.document.querySelector('[aria-label="Remove marker 1, table"]'));
  assertMarkers([1, 2]);
  await addWord("window");
  await addWord("door");
  assertMarkers([1, 2, 3, 4]);
  await click(dom.window.document.querySelector('[aria-label="Remove marker 3, window"]'));
  assertMarkers([1, 2, 3]);
  await click(button("Restore removed objects"));
  assertMarkers([1, 2, 3, 4]);
  await click(dom.window.document.querySelector('[aria-label="Remove marker 1, table"]'));
  assertMarkers([1, 2, 3]);
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
  assertMarkers([1, 2]);
  assert.deepEqual(counts(), { table: 1, cup: 1 });
  await addWord("cup");
  assertMarkers([1, 2, 3]);
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
  assertMarkers([1]);
  assert.deepEqual(counts(), { cup: 1 });
  await click(button("Restore removed objects"));
  assertMarkers([1, 2]);
  assert.deepEqual(counts(), { cup: 2 });
  await click(button("Confirm lesson facts"));
  assert.deepEqual(reviews[0].acceptedObjectIds, ["object-1", "object-2"]);
  assert.deepEqual(reviews[0].objectCounts, { "object-1": 2 });
  assert.deepEqual(reviews[0].relations, [relation]);
});

test("a revisit marks words practised in an earlier lesson on the photo", async () => {
  await mount({ ...detail(), practisedSceneObjectIds: ["object-0"] });
  const practised = [...dom.window.document.querySelectorAll(".analysis-word-row__practised")];
  assert.deepEqual(practised.map(element => element.closest(".analysis-word-row")?.querySelector(".analysis-word-row__marker")?.textContent), ["1"]);
  assert.match(dom.window.document.body.textContent ?? "", /New words from this photo come first/);
});

test("a revisit with every word practised says so instead of promising new words", async () => {
  await mount({ ...detail(), practisedSceneObjectIds: ["object-0", "object-1", "object-2"] });
  assert.equal(dom.window.document.querySelectorAll(".analysis-word-row__practised").length, 3);
  assert.match(dom.window.document.body.textContent ?? "", /practised every word here/);
});

test("a first lesson on a photo shows no practised marks", async () => {
  await mount();
  assert.equal(dom.window.document.querySelectorAll(".analysis-word-row__practised").length, 0);
  assert.doesNotMatch(dom.window.document.body.textContent ?? "", /New words from this photo/);
});

test("a learner-added object follows the visible suggestion numbers", async () => {
  await mount({ ...detail(), suggestedSceneObjectIds: ["object-1", "object-2"] });
  assertMarkers([1, 2]);

  await addWord("window");

  assertMarkers([1, 2, 3]);
});

test("relation endpoints keep the same object while its displayed marker changes", async () => {
  await mount();
  await click(dom.window.document.querySelector('[aria-label="Remove marker 1, table"]'));
  await click([...dom.window.document.querySelectorAll('[role="tab"]')][2]);
  assert.deepEqual(numbers(".analysis-relation-row .analysis-word-row__marker"), [1]);
  assert.deepEqual(numbers(".analysis-relation-row .combobox__marker"), [2]);
  await click(button("Confirm lesson facts"));
  assert.deepEqual(reviews[0].relations, [relation]);
});

test("reloading a saved review keeps custom objects and persisted marker identities", async () => {
  const session = detail();
  session.session.status = "inProgress";
  session.sceneObjects = [session.sceneObjects[1], session.sceneObjects[2], {
    ...session.sceneObjects[0], id: "manual-door", label: "door", sourceObjectKey: null,
  }];
  session.reviewMarkers = { "object-1": 1, "object-2": 2, "manual-door": 3 };
  session.suggestedSceneObjectIds = ["object-1", "object-2"];
  await mount(session, false, practiceScene(session, "/photo.jpg", "Spanish"));
  assertMarkers([1, 2, 3]);
  assert.deepEqual([...dom.window.document.querySelectorAll(".analysis-word-row__remove")]
    .map(element => element.getAttribute("aria-label")), [
      "Remove marker 1, cup", "Remove marker 2, cup", "Remove marker 3, door",
    ]);
});

test("moving an object's marker does not renumber or reidentify it", async () => {
  await mount();
  await click(dom.window.document.querySelector('[aria-label="Change location of marker 2, cup"]'));
  const photo = dom.window.document.querySelector(".scene[role=button]")!;
  await act(async () => {
    photo.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  });
  assertMarkers([1, 2, 3]);
  await click(button("Confirm lesson facts"));
  assert.deepEqual(reviews[0].repositionedObjects, [{ id: "object-1", anchorPoint: { x: .5, y: .5 } }]);
});

test("older saved marker gaps stay authoritative without colliding with a newly added object", async () => {
  const session = detail();
  session.session.status = "inProgress";
  session.reviewMarkers = { "object-0": 1, "object-1": 3, "object-2": 4 };
  await mount(session, false, practiceScene(session, "/photo.jpg", "Spanish"));
  assertMarkers([1, 3, 4]);
  await addWord("door");
  assertMarkers([1, 3, 4, 5]);
});

test("added markers stay contiguous after removing an added object and are not saved", async () => {
  await mount();
  await addWord("window");
  await addWord("door");
  assertMarkers([1, 2, 3, 4, 5]);

  await click(dom.window.document.querySelector('[aria-label="Remove marker 4, window"]'));

  assertMarkers([1, 2, 3, 4]);
  await click(button("Confirm lesson facts"));
  assert.equal(reviews.length, 1);
  assert.equal(reviews[0].addedObjects.length, 1);
  assert.equal(reviews[0].addedObjects[0].label, "door");
  assert.deepEqual(Object.keys(reviews[0].addedObjects[0]).sort(), ["id", "label", "x", "y"]);
});

test("the beginner preference mission uses an AI scenario instead of asking for a preference", async () => {
  await mount({ ...detail(), provisionalMissionPlan: [{ missionId: "M05", practiceLevel: "A0" }],
    missionChoices: { preference: { sceneObjectIds: ["object-1"], chosenObjectId: null, reaction: "like" } } });
  assert.equal(dom.window.document.getElementById("preference-object"), null);
  assert.doesNotMatch(dom.window.document.body.textContent ?? "", /Your preference|pretend preference/);
  await click(button("Confirm lesson facts"));
  assert.equal(reviews[0].missionChoices, undefined);
});

for (const [stage, completed] of [["loadingImage", 0], ["findingObjects", 1], ["checkingResults", 2], ["savingResults", 3]] as const) {
  test(`analysis progress reports ${completed} completed stages while ${stage} is active`, async () => {
    const session = detail();
    session.session.status = "analyzingScene";
    session.sceneAnalysisProgress = { stage, startedAt: new Date(Date.now() - 5000).toISOString() };
    await mount(session);
    const progress = dom.window.document.querySelector('[role="progressbar"]');
    assert.ok(progress);
    assert.equal(progress.getAttribute("aria-valuenow"), String(completed));
    assert.equal(progress.getAttribute("aria-valuemax"), "4");
    assert.equal(dom.window.document.querySelectorAll(".scene-processing-progress__segment.is-complete").length, completed);
    assert.equal(dom.window.document.querySelectorAll(".scene-processing-progress__segment.is-active").length, 1);
    assert.match(dom.window.document.body.textContent ?? "", /Elapsed 0:0/);
    assert.doesNotMatch(dom.window.document.body.textContent ?? "", /only take a moment/);
  });
}

test("legacy analysis uses indeterminate progress and review readiness completes all stages", async () => {
  const session = detail();
  session.session.status = "analyzingScene";
  await mount(session);
  assert.equal(dom.window.document.querySelector('[role="progressbar"]')?.hasAttribute("aria-valuenow"), false);
  await act(async () => { root?.unmount(); });
  root = null;
  dom.window.document.body.replaceChildren();
  await mount(detail());
  assert.equal(dom.window.document.querySelector('[role="progressbar"]')?.getAttribute("aria-valuenow"), "4");
  assert.equal(dom.window.document.querySelectorAll(".scene-processing-progress__segment.is-active").length, 0);
});

test("paused polling retains completed milestones and stops the active pulse", async () => {
  const session = detail();
  session.session.status = "analyzingScene";
  session.sceneAnalysisProgress = { stage: "checkingResults", startedAt: null };
  await mount(session, true);
  assert.equal(dom.window.document.querySelector('[role="progressbar"]')?.getAttribute("aria-valuenow"), "2");
  assert.equal(dom.window.document.querySelectorAll(".scene-processing-progress__segment.is-active").length, 0);
  assert.match(dom.window.document.body.textContent ?? "", /Updates paused/);
});

test("lesson progress advances only when translations and the first task are committed", async () => {
  const session = detail();
  session.session.status = "generatingTasks";
  session.translationPreview = { objects: [], attributes: [], relationships: [] };
  await mount(session);
  const progress = dom.window.document.querySelector('[role="progressbar"]');
  assert.equal(progress?.getAttribute("aria-valuemax"), "2");
  assert.equal(progress?.getAttribute("aria-valuenow"), "1");
  assert.match(dom.window.document.body.textContent ?? "", /Preparing your first task/);
});

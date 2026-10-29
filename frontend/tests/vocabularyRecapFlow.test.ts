import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { SessionTask, VocabularyLearningWord } from "../src/lib/api.ts";
import type { LanguageItem } from "../src/data/types.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://app.test/", pretendToBeVisual: true });
const globals = globalThis as Record<string, unknown>;
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (globals[key] !== undefined) continue;
  try { globals[key] = (dom.window as unknown as Record<string, unknown>)[key]; } catch { /* Node owns a few read-only globals. */ }
}
Object.defineProperty(globalThis, "window", { value: dom.window, configurable: true });
Object.defineProperty(globalThis, "document", { value: dom.window.document, configurable: true });
globals.IS_REACT_ACT_ENVIRONMENT = true;
const here = dirname(fileURLToPath(import.meta.url));
async function bundle() {
  const folder = mkdtempSync(join(tmpdir(), "vocabulary-recap-"));
  const entry = join(here, `.vocabularyRecap-${crypto.randomUUID()}.ts`);
  writeFileSync(entry, [
    'export { createElement as h, act } from "react";', 'export { createRoot } from "react-dom/client";',
    'export { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";',
    'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
    'export { AppStateContext } from "../src/state/context";',
    'export { VocabularySceneReview } from "../src/pages/LearningTaskPage";',
  ].join("\n"));
  try {
    const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
      plugins: [{ name: "test-api", transform: code => code.replaceAll("import.meta.env?.VITE_API_BASE_URL", '"http://api.test"') },
        { name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null, load: id => id === "\0empty-css" ? "export default {};" : null }],
    });
    try {
      const { output } = await bundler.generate({ format: "esm" });
      const path = join(folder, "bundle.mjs");
      writeFileSync(path, output[0].code);
      return await import(pathToFileURL(path).href);
    } finally { await bundler.close(); }
  } finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
}
const surface = await bundle();
const originalFetch = globals.fetch;
const requests: { path: string; body: Record<string, unknown> }[] = [];
let failNext = false;
const text = () => dom.window.document.body.textContent ?? "";
const button = (label: string) => [...dom.window.document.querySelectorAll("button")].find(item => item.textContent?.trim() === label);
globals.fetch = async (input: unknown, init?: RequestInit) => {
  const path = new URL(String(input)).pathname;
  const body = JSON.parse(String(init?.body ?? "{}"));
  requests.push({ path, body });
  if (failNext) { failNext = false; throw new Error("Reply lost"); }
  if (path.endsWith("/check-vocabulary-answer")) return Response.json({
    questionId: body.questionId, acceptedOptionId: body.optionId, isCorrect: true,
    correctOptionId: body.optionId, basilEarned: 0,
  });
  if (path.endsWith("/check-vocabulary-typing")) return Response.json({
    learningKey: body.learningKey, isCorrect: true, correctAnswer: body.answer, revealed: false,
  });
  throw new Error(`Unexpected request: ${path}`);
};
const cleanups = new Set<() => Promise<void>>();
test.beforeEach(() => { requests.length = 0; failNext = false; });
test.afterEach(async () => { for (const close of [...cleanups]) await close(); });
test.after(() => {
  globals.fetch = originalFetch;
  dom.window.close();
  for (const handle of (process as unknown as { _getActiveHandles(): { constructor: { name: string }; unref?: () => void }[] })._getActiveHandles()) {
    if (handle.constructor.name === "MessagePort") handle.unref?.();
  }
});
async function click(label: string) {
  await surface.act(async () => {
    const element = button(label);
    assert.ok(element, `expected ${label}`);
    assert.equal(element.disabled, false, `${label} must be enabled`);
    element.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  });
}
async function type(value: string) {
  const input = dom.window.document.querySelector("input");
  assert.ok(input);
  await surface.act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
}
async function mount(options: { words?: VocabularyLearningWord[]; items?: LanguageItem[]; stayInReview?: boolean } = {}) {
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = surface.createRoot(container);
  const client = new surface.QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const task: SessionTask = {
    id: "t1", kind: "vocabularyIntroduction", phase: "learning", status: "completed", orderIndex: 0,
    isSkippable: true, vocabularyItemId: null, sceneObjectId: null, xpReward: 0, xpBonus: 0,
    publicContent: { kind: "vocabularyIntroduction", title: "Photo words", allowTypingPractice: true,
      words: options.words ?? [["cup", "taza"], ["table", "mesa"]].map(([translation, targetText]) => ({
        learningKey: translation, termType: "object", vocabularyItemId: null, sceneObjectId: null,
        targetText, translation, partOfSpeech: "noun", gender: null, pluralForm: null,
        phoneticText: null, pronunciationAudioAssetId: null, exampleSentence: null,
      })),
      questions: [
        { questionId: "q-cup", prompt: "What is taza?", options: [{ optionId: "option-cup", label: "cup" }, { optionId: "wrong-cup", label: "plate" }] },
        { questionId: "q-table", prompt: "What is mesa?", options: [{ optionId: "option-table", label: "table" }, { optionId: "wrong-table", label: "chair" }] },
      ],
    },
  };
  const close = async () => { await surface.act(async () => root.unmount()); client.clear(); container.remove(); cleanups.delete(close); };
  cleanups.add(close);
  const scene = { id: "scene1", sessionId: "s1", imageUrl: null, items: options.items ?? [], languageCode: "es" };
  await surface.act(async () => root.render(surface.h(surface.QueryClientProvider, { client },
    surface.h(surface.AppStateContext.Provider, { value: {
      session: { session: { id: "s1", status: "completed" }, tasks: [task], sceneObjects: [] }, practiceSaving: false,
      actOnTask: () => { throw new Error("Review must not submit the completed task"); },
    } }, surface.h(surface.MemoryRouter, { initialEntries: ["/review"] }, surface.h(surface.Routes, null,
      surface.h(surface.Route, { element: surface.h(surface.Outlet, { context: scene }) },
        surface.h(surface.Route, { path: "/review", element: surface.h(surface.VocabularySceneReview) })),
      surface.h(surface.Route, { path: "/vocabulary", element: surface.h("p", null, "Vocabulary collection") })))))));
  if (!options.stayInReview) {
    await click("Next");
    await click("Start quick quiz");
  }
}

function reviewWord(termType: VocabularyLearningWord["termType"], targetText: string, sceneObjectId: string | null = null, relatedSceneObjectIds: string[] = []): VocabularyLearningWord {
  return { learningKey: targetText, termType, targetText, translation: targetText, sceneObjectId, relatedSceneObjectIds,
    vocabularyItemId: null, partOfSpeech: termType === "object" ? "noun" : termType === "attribute" ? "adjective" : "preposition",
    gender: null, pluralForm: null, phoneticText: null, pronunciationAudioAssetId: null, exampleSentence: null };
}

test("review groups mixed words while retaining photo context and optional image interaction", async () => {
  await mount({ stayInReview: true, words: [
    reviewWord("relationship", "cerca", null, ["table", "chair"]),
    reviewWord("attribute", "rojo", "chair"),
    reviewWord("object", "mesa", "table"),
    reviewWord("object", "silla", "chair"),
  ], items: ["table", "chair"].map((id, i) => ({ id, marker: i + 1, word: id, translation: id, wordClass: "noun", gender: null, x: 30 + i * 30, y: 50, example: "", exampleTranslation: "" })) });
  const section = () => dom.window.document.querySelector(".vocabulary-review-section h2")?.textContent;
  assert.equal(section(), "Objects and adjectives");
  assert.equal(dom.window.document.querySelectorAll("button.scene__marker").length, 2);
  await click("Next");
  assert.equal(section(), "Objects and adjectives");
  assert.deepEqual([...dom.window.document.querySelectorAll(".learning-card__word h2")].map(item => item.textContent), ["silla", "rojo"]);
  assert.ok(dom.window.document.querySelector(".vocabulary-learning-grid--paired"));
  assert.ok(dom.window.document.querySelector(".vocabulary-learning-scene"));
  assert.equal(dom.window.document.querySelectorAll("button.scene__marker").length, 2);
  await click("Next");
  assert.equal(section(), "Relations");
  assert.equal(dom.window.document.querySelectorAll(".scene__marker--active").length, 2);
  assert.ok(button("Start quick quiz"));
  await click("Previous");
  assert.equal(section(), "Objects and adjectives");
  assert.deepEqual(requests, [], "Exploring teaching cards must not submit answers");
});

test("repeated-object markers select the matching word, highlight the clicked instance and speak native text", async () => {
  const spoken: { text: string; lang: string }[] = [];
  const previousSpeech = dom.window.speechSynthesis;
  const previousUtterance = globals.SpeechSynthesisUtterance;
  Object.defineProperty(dom.window, "speechSynthesis", { configurable: true, value: {
    cancel: () => {}, speak: (utterance: { text: string; lang: string }) => spoken.push(utterance),
  } });
  globals.SpeechSynthesisUtterance = class { text: string; constructor(text: string) { this.text = text; } };
  try {
    await mount({ stayInReview: true, words: [reviewWord("object", "mesa", "table"), reviewWord("object", "silla", "chair1", ["chair2"])],
      items: ["table", "chair1", "chair2"].map((id, i) => ({ id, marker: i + 1, word: id, translation: id, wordClass: "noun", gender: null, x: 20 + i * 25, y: 50, example: "", exampleTranslation: "" })) });
    const marker = dom.window.document.querySelector<HTMLButtonElement>('button[aria-label="Marker 3: chair2"]');
    assert.ok(marker);
    await surface.act(async () => marker.click());
    assert.equal(dom.window.document.querySelector(".learning-card__word h2")?.textContent, "silla");
    assert.equal(marker.getAttribute("aria-pressed"), "true");
    assert.equal(dom.window.document.querySelectorAll(".scene__marker--active").length, 1);
    assert.equal(spoken[0].text, "silla");
    assert.equal(spoken[0].lang, "es-ES");
    const replay = dom.window.document.querySelector<HTMLButtonElement>('button[aria-label="Hear silla"]');
    assert.ok(replay);
    await surface.act(async () => replay.click());
    assert.equal(spoken.length, 2);
    assert.deepEqual(requests, []);
  } finally {
    Object.defineProperty(dom.window, "speechSynthesis", { value: previousSpeech, configurable: true });
    globals.SpeechSynthesisUtterance = previousUtterance;
  }
});

test("revisit alternates server-graded recognition and recall and can finish without new rewards", async () => {
  await mount();
  await click("cup");
  assert.deepEqual(requests[0].body, { questionId: "q-cup", optionId: "option-cup", review: true });
  await click("Continue");
  assert.ok(dom.window.document.querySelector('input[aria-label="Type table"]'));
  await type("mesa"); await click("Check answer"); await click("Continue");
  assert.match(text(), /What is mesa/);
  await click("table"); await click("Continue");
  assert.ok(dom.window.document.querySelector('input[aria-label="Type cup"]'));
  await type("taza"); await click("Check answer"); await click("Finish review");
  assert.match(text(), /Review complete/);
  assert.doesNotMatch(text(), /Basil earned|mastered/);
  assert.equal(requests.length, 4);
  assert.deepEqual(requests[1].body, { learningKey: "table", answer: "mesa", reveal: false });
  assert.ok(requests.every(request => /check-vocabulary-(answer|typing)$/.test(request.path)));
  await click("Back to vocabulary");
  assert.match(text(), /Vocabulary collection/);
});

test("a failed recognition check can retry its original option before mixed recall", async () => {
  await mount(); failNext = true;
  await click("cup");
  assert.match(text(), /couldn’t save this answer/);
  await click("Retry answer");
  assert.deepEqual(requests[0], requests[1]);
  await click("Continue");
  assert.ok(dom.window.document.querySelector('input[aria-label="Type table"]'));
});

test("a failed recall check preserves unfinished text and can continue after retry", async () => {
  await mount(); await click("cup"); await click("Continue");
  await type("mes"); failNext = true; await click("Check answer");
  assert.equal(dom.window.document.querySelector("input")?.value, "mes");
  await type("mesa"); await click("Check answer"); await click("Continue");
  assert.match(text(), /What is mesa/);
  await click("table");
  assert.equal(requests.at(-1)?.body.optionId, "option-table");
});

test("typing can be skipped without an answer request while recognition stays required", async () => {
  await mount();
  const assertPhoto = () => {
    assert.equal(dom.window.document.querySelectorAll(".vocabulary-learning-scene").length, 1);
    assert.equal(dom.window.document.querySelector(".vocabulary-learning-scene")?.getAttribute("aria-label"), "Your photo");
    assert.equal(dom.window.document.querySelectorAll("button.scene__marker").length, 0);
  };
  assertPhoto();
  assert.equal(button("Skip typing"), undefined);
  await click("cup"); await click("Continue");
  assertPhoto();
  await type("unfinished");
  const before = requests.length;
  await click("Skip typing");
  assertPhoto();
  assert.equal(requests.length, before);
  assert.match(text(), /What is mesa/);
  assert.equal(button("Skip typing"), undefined);
  await click("table"); await click("Continue");
  await click("Skip typing");
  assert.match(text(), /Review complete/);
  assertPhoto();
  assert.equal(requests.length, 2);
  assert.ok(requests.every(request => request.path.endsWith("check-vocabulary-answer")));
});

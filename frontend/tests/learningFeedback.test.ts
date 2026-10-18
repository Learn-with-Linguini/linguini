import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import { learningFeedback } from "../src/lib/learningFeedback.ts";
import type { LessonAnswerCheck, LatestClueAttempt, SessionTask, TaskActionResult } from "../src/lib/api.ts";

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
  const folder = mkdtempSync(join(tmpdir(), "learning-feedback-"));
  const entry = join(here, `.learningFeedback-${crypto.randomUUID()}.ts`);
  writeFileSync(entry, [
    'export { createElement as h, act } from "react";', 'export { createRoot } from "react-dom/client";',
    'export { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";',
    'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
    'export { AppStateContext } from "../src/state/context";',
    'export { LearningTaskPage } from "../src/pages/LearningTaskPage";',
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
let savedChecks: LessonAnswerCheck[] = [];
let latestAttempt: LatestClueAttempt | null = null;
const replies: (() => Response | Promise<Response>)[] = [];
const actions: (() => TaskActionResult | null)[] = [];
const requests: Record<string, unknown>[] = [];
const originalFetch = globals.fetch;
globals.fetch = async (input: unknown, init?: RequestInit) => {
  const path = new URL(String(input)).pathname;
  if (path.endsWith("/lesson-checks")) return Response.json({ checks: savedChecks, assistanceSteps: {} });
  if (path.endsWith("/latest-attempt")) return Response.json({ attempt: latestAttempt });
  requests.push(JSON.parse(String(init?.body ?? "{}")));
  return replies.shift()?.() ?? new Response("Unexpected fixture request", { status: 500 });
};
const cleanups = new Set<() => Promise<void>>();
test.beforeEach(() => { savedChecks = []; latestAttempt = null; replies.length = 0; actions.length = 0; requests.length = 0; });
test.afterEach(async () => { for (const cleanup of [...cleanups]) await cleanup(); });
test.after(() => {
  globals.fetch = originalFetch;
  dom.window.close();
  for (const handle of (process as unknown as { _getActiveHandles(): { constructor: { name: string }; unref?: () => void }[] })._getActiveHandles()) {
    if (handle.constructor.name === "MessagePort") handle.unref?.();
  }
});
const text = () => dom.window.document.body.textContent ?? "";
const button = (label: string) => [...dom.window.document.querySelectorAll("button")].find(item => item.textContent?.trim() === label);
async function waitFor(assertion: () => void) {
  const deadline = Date.now() + 2_000;
  let lastError: unknown;
  do {
    await surface.act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
    try { assertion(); return; } catch (error) { lastError = error; }
  } while (Date.now() < deadline);
  throw lastError;
}
async function click(label: string) {
  await surface.act(async () => {
    const element = button(label);
    assert.ok(element, `expected ${label}`);
    assert.equal(element.disabled, false, `${label} should be enabled`);
    element.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  });
}
function lesson(missionId = "M01"): SessionTask {
  return { id: "t1", kind: "grammarLesson", phase: "learning", status: "pending", isSkippable: true,
    orderIndex: 0, vocabularyItemId: null, sceneObjectId: null, xpReward: 10, xpBonus: 0,
    publicContent: { kind: "grammarLesson", missionId, practiceLevel: "A0", contentVersion: 1,
      focus: "genderNumberAgreement", title: "Choose the article", checkEachQuestion: true,
      questions: [{ questionId: "q1", prompt: "Choose the article for taza.", interactionType: "multipleChoice",
        tokenBank: [], options: [{ optionId: "a", label: "la" }, { optionId: "b", label: "el" }], allowRetry: missionId === "M06" }] } };
}
function checked(correct: boolean, attemptsLeft = 0): LessonAnswerCheck {
  return { questionId: "q1", answer: correct ? "a" : "b", isCorrect: correct, correctAnswer: "la", attemptsLeft,
    feedback: correct ? "The article matches taza." : "Keep the noun and check its article.",
    outcome: { questionId: "q1", outcome: correct ? "correct" : "incorrect", objectiveId: "article", targetIds: [],
      evidenceType: "recognition", assistance: ["wordBank"], assistanceUsed: true,
      mistakes: correct ? [] : [{ mistake: "wrongArticle", answer: "el", correction: "la", explanation: "Taza is feminine." }],
      correctNote: "Taza uses la.", optionNotes: ["El is used with masculine nouns."] } };
}
function action(task: SessionTask, isCorrect: boolean | null, message: string, xpEarned = 5): TaskActionResult {
  return { task: { ...task, status: "completed" }, nextTaskId: null,
    sessionProgress: { completedTaskCount: 1, skippedTaskCount: 0, terminalTaskCount: 1, totalTaskCount: 1 }, xpEarned,
    attempt: { id: "attempt1", attemptNumber: 1, isCorrect, feedback: { message } } };
}
async function mount(initialTask: SessionTask) {
  let task = initialTask;
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = surface.createRoot(container);
  const client = new surface.QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0, refetchOnWindowFocus: false } } });
  const scene = { id: "scene1", sessionId: "s1", imageUrl: null, mediaAssetId: "asset1", title: "Table", items: [], languageCode: "es" };
  const render = () => surface.act(async () => root.render(surface.h(surface.QueryClientProvider, { client },
    surface.h(surface.AppStateContext.Provider, { value: {
      session: { session: { id: "s1", status: "inProgress" }, tasks: [task], sceneObjects: [] },
      practiceSaving: false, practiceError: null, completeSession: () => false,
      actOnTask: async () => {
        const result = actions.shift()?.() ?? null;
        if (result) { task = result.task; await render(); }
        return result;
      },
    } }, surface.h(surface.MemoryRouter, { initialEntries: ["/practice/sessions/s1/learn/t1"] },
      surface.h(surface.Routes, null, surface.h(surface.Route, { path: "/practice/sessions/:sessionId", element: surface.h(surface.Outlet, { context: scene }) },
        surface.h(surface.Route, { path: "learn/:taskId", element: surface.h(surface.LearningTaskPage) }))))))));
  const close = async () => {
    cleanups.delete(close);
    try { await surface.act(async () => root.unmount()); } finally { client.clear(); container.remove(); }
  };
  cleanups.add(close);
  await render();
  await waitFor(() => assert.doesNotMatch(text(), /Restoring checked answers…|Restoring your place…/));
  return { close, render };
}

test("A0 checked answers retain correctness, server feedback and notes across rerenders and restoration", async () => {
  let view = await mount(lesson());
  await click("la");
  replies.push(() => Response.json(checked(true)));
  await click("Check answer");
  const phrase = learningFeedback("correct", "t1:q1");
  await waitFor(() => assert.match(text(), /Correct!/));
  assert.ok(text().includes(phrase));
  assert.match(text(), /The article matches taza/);
  assert.match(text(), /El is used with masculine nouns/);
  assert.match(text(), /Supported practice: built with the word bank/);
  await view.render();
  assert.ok(text().includes(phrase));
  await view.close();
  savedChecks = [checked(true)];
  view = await mount(lesson());
  assert.ok(text().includes(phrase));
  assert.equal(dom.window.document.querySelectorAll('.feedback [role="status"]').length, 1);
  assert.equal(requests.length, 1, "restoring a result does not submit another check");
});

test("a locked incorrect answer keeps its correction without promising another attempt", async () => {
  await mount(lesson());
  await click("el");
  replies.push(() => Response.json(checked(false)));
  await click("Check answer");
  await waitFor(() => assert.match(text(), /The correct answer is la/));
  assert.ok(text().includes(learningFeedback("incorrect", "t1:q1")));
  assert.match(text(), /Keep the noun and check its article/);
  assert.match(text(), /Taza is feminine/);
  assert.equal(button("Try again"), undefined);
  assert.equal(button("Check again"), undefined);
  assert.equal(button("el")?.disabled, true);
  assert.equal(button("Finish task")?.disabled, false);
});

test("M06 preserves a saved retry and replaces encouragement only after the new grade arrives", async () => {
  savedChecks = [checked(false, 1)];
  await mount(lesson("M06"));
  assert.ok(text().includes(learningFeedback("incorrect", "t1:q1")));
  assert.match(text(), /Keep the noun and check its article/);
  await click("Try again");
  assert.equal(dom.window.document.querySelector('.feedback'), null);
  await click("la");
  replies.push(() => Response.json(checked(true)));
  await click("Check again");
  await waitFor(() => assert.ok(text().includes(learningFeedback("correct", "t1:q1"))));
  assert.match(text(), /The article matches taza/);
  assert.equal(requests[0].answer, "a");
  assert.equal(button("Try again"), undefined);
});

test("a failed question check shows the error without an answer celebration", async () => {
  await mount(lesson());
  await click("la");
  replies.push(() => Response.json({ detail: { message: "Check interrupted" } }, { status: 500 }));
  await click("Check answer");
  await waitFor(() => assert.ok(dom.window.document.querySelector('[role="alert"]')));
  assert.equal(dom.window.document.querySelector('.feedback'), null);
  assert.equal(button("Check answer")?.disabled, false);
  assert.equal(button("la")?.getAttribute("aria-pressed"), "true");
});

test("reading completion keeps neutral participation copy and the server's reward amount", async () => {
  const task: SessionTask = { ...lesson(), kind: "grammarExplanation", publicContent: { kind: "grammarExplanation", title: "Read the pattern", explanation: "Taza uses la.", examples: [] } };
  await mount(task);
  actions.push(() => action(task, null, "Reading participation saved.", 3));
  await click("Mark complete");
  await waitFor(() => assert.match(text(), /Reading participation saved/));
  assert.ok(text().includes(learningFeedback("saved", task.id)));
  assert.ok(!text().includes(learningFeedback("correct", task.id)));
  assert.match(text(), /\+3 Basil earned/);
  assert.doesNotMatch(text(), /mastered|accent|Full marks/i);
});

test("a restored mixed task shows one neutral batch heading and retains the correct answer and explanations", async () => {
  const task = lesson();
  task.status = "completed";
  if (task.publicContent.kind !== "grammarLesson") throw new Error("Expected grammar fixture");
  task.publicContent.checkEachQuestion = false;
  task.publicContent.questions.push({ ...task.publicContent.questions[0], questionId: "q2", prompt: "Choose another article." });
  latestAttempt = { id: "batch1", attemptNumber: 1, text: "", optionId: null, isCorrect: false, feedback: "1 of 2 correct.",
    evaluationDetails: null, assistance: null, answers: { q1: "b", q2: "a" },
    reviewDetails: { questionResults: { q1: false, q2: true }, correctAnswers: { q1: "a", q2: "a" }, questionOutcomes: [checked(false).outcome] } };
  await mount(task);
  await waitFor(() => assert.match(text(), /1 of 2 correct/));
  assert.ok(text().includes(learningFeedback("saved", task.id)));
  assert.ok(!text().includes(learningFeedback("correct", "t1:q1")));
  assert.match(text(), /The correct answer is la/);
  assert.match(text(), /Taza is feminine/);
  assert.match(text(), /Supported practice: built with the word bank/);
  assert.equal(dom.window.document.querySelectorAll('.feedback [role="status"]').length, 1);
});

test("restored checks on a skipped task never add branded praise", async () => {
  const task = lesson();
  task.status = "skipped";
  savedChecks = [checked(true)];
  await mount(task);
  assert.ok(!text().includes(learningFeedback("correct", "t1:q1")));
  assert.ok(!text().includes(learningFeedback("saved", task.id)));
});

test("vocabulary feedback keeps the correct word and a locked answer", async () => {
  const task: SessionTask = { ...lesson(), kind: "vocabularyIntroduction", publicContent: {
    kind: "vocabularyIntroduction", title: "Photo words", allowTypingPractice: true,
    words: [{ learningKey: "cup", termType: "object", vocabularyItemId: "v1", sceneObjectId: null, targetText: "taza", translation: "cup",
      partOfSpeech: "noun", gender: null, pluralForm: null, phoneticText: null, pronunciationAudioAssetId: null, exampleSentence: null }],
    questions: [{ questionId: "word1", prompt: "What is taza?", correctOptionId: "cup",
      options: [{ optionId: "cup", label: "cup" }, { optionId: "table", label: "table" }] }],
  } };
  await mount(task);
  await click("Start quick quiz");
  await click("table");
  assert.ok(text().includes(learningFeedback("incorrect", "t1:word1")));
  assert.match(text(), /Incorrect\. The correct answer is cup/);
  assert.equal(button("cup")?.disabled, true);
  assert.equal(button("Try again"), undefined);
  assert.equal(button("Continue")?.disabled, false);
});

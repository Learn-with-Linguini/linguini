import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import { learningFeedback } from "../src/lib/learningFeedback.ts";
import { queryKeys } from "../src/lib/queryKeys.ts";
import type { LessonAnswerCheck, LatestClueAttempt, SessionTask, TaskActionResult } from "../src/lib/api.ts";
import type { Scene } from "../src/data/types.ts";

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
let vocabularySaved: Record<string, unknown>[] = [];
let vocabularyRestoreFails = false;
let vocabularyRestoreReply: (() => Response | Promise<Response>) | null = null;
let latestAttempt: LatestClueAttempt | null = null;
const replies: (() => Response | Promise<Response>)[] = [];
const actions: (() => TaskActionResult | null)[] = [];
const requests: Record<string, unknown>[] = [];
const taskActions: { action: string; body: unknown }[] = [];
const originalFetch = globals.fetch;
globals.fetch = async (input: unknown, init?: RequestInit) => {
  const path = new URL(String(input)).pathname;
  if (path.endsWith("/vocabulary-checks")) return vocabularyRestoreReply?.() ?? (vocabularyRestoreFails ? Response.json({ detail: { message: "Unavailable" } }, { status: 503 }) : Response.json({ checks: vocabularySaved }));
  if (path.endsWith("/lesson-checks")) return Response.json({ checks: savedChecks, assistanceSteps: {} });
  if (path.endsWith("/latest-attempt")) return Response.json({ attempt: latestAttempt });
  requests.push(JSON.parse(String(init?.body ?? "{}")));
  return replies.shift()?.() ?? new Response("Unexpected fixture request", { status: 500 });
};
const cleanups = new Set<() => Promise<void>>();
test.beforeEach(() => { savedChecks = []; vocabularySaved = []; vocabularyRestoreFails = false; vocabularyRestoreReply = null; latestAttempt = null; replies.length = 0; actions.length = 0; requests.length = 0; taskActions.length = 0; });
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
  return { basilEarned: correct ? 10 : 5, questionId: "q1", answer: correct ? "a" : "b", isCorrect: correct, correctAnswer: "la", attemptsLeft,
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
async function mount(initialTask: SessionTask, scenePatch: Partial<Scene> = {}) {
  let task = initialTask;
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = surface.createRoot(container);
  const client = new surface.QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0, refetchOnWindowFocus: false } } });
  const vocabularyWords = initialTask.publicContent.kind === "vocabularyIntroduction" ? initialTask.publicContent.words : [];
  const scene = { id: "scene1", sessionId: "s1", imageUrl: null, mediaAssetId: "asset1", title: "Table",
    items: vocabularyWords.flatMap((word, position) => word.sceneObjectId ? [{ id: word.sceneObjectId,
      word: word.targetText, translation: word.translation, marker: position + 1, x: 20 + position * 20, y: 40,
      wordClass: word.partOfSpeech, gender: null, example: "", exampleTranslation: "" }] : []), languageCode: "es", ...scenePatch };
  const render = () => surface.act(async () => root.render(surface.h(surface.QueryClientProvider, { client },
    surface.h(surface.AppStateContext.Provider, { value: {
      session: { session: { id: "s1", status: "inProgress" }, tasks: [task], sceneObjects: [] },
      practiceSaving: false, practiceError: null, completeSession: () => false,
      actOnTask: async (_taskId: string, action: string, body: unknown) => {
        taskActions.push({ action, body });
        const result = actions.shift()?.() ?? null;
        if (result) { task = result.task; await render(); }
        return result;
      },
    } }, surface.h(surface.MemoryRouter, { initialEntries: ["/practice/sessions/s1/learn/t1"] },
      surface.h(surface.Routes, null,
        surface.h(surface.Route, { path: "/home", element: surface.h("p", null, "Home destination") }),
        surface.h(surface.Route, { path: "/practice/sessions/:sessionId", element: surface.h(surface.Outlet, { context: scene }) },
          surface.h(surface.Route, { path: "learn", element: surface.h("p", null, "Task list destination") }),
          surface.h(surface.Route, { path: "learn/:taskId", element: surface.h(surface.LearningTaskPage) }))))))));
  const close = async () => {
    cleanups.delete(close);
    try { await surface.act(async () => root.unmount()); } finally { client.clear(); container.remove(); }
  };
  cleanups.add(close);
  await render();
  await waitFor(() => assert.doesNotMatch(text(), /Restoring checked answers|Restoring your place/));
  return { close, render, client };
}

const descriptionScene: Partial<Scene> = {
  imageUrl: "/table.jpg",
  items: [{ id: "cup", word: "taza", translation: "cup", wordClass: "noun", gender: "la",
    marker: 1, x: 25, y: 50, example: "Una taza.", exampleTranslation: "A cup." }],
};

for (const checkEachQuestion of [true, false]) {
  const mode = checkEachQuestion ? "sequential" : "grouped";
  test(`${mode} descriptions show the photo for choices and sentence building without revealing markers`, async () => {
    for (const focus of ["sceneDescription", "chainedDescription"] as const) {
      for (const interactionType of ["multipleChoice", "sentenceBuilding"] as const) {
        const task = lesson();
        if (task.publicContent.kind !== "grammarLesson") throw new Error("Expected grammar fixture");
        task.publicContent.checkEachQuestion = checkEachQuestion;
        task.publicContent.focus = focus;
        task.publicContent.questions[0].interactionType = interactionType;
        task.publicContent.questions[0].tokenBank = ["La", "taza", "está", "sobre", "la", "mesa"];
        const view = await mount(task, descriptionScene);
        const photos = dom.window.document.querySelectorAll('.scene img[alt="Table"]');
        assert.equal(photos.length, 1, `${focus}: ${interactionType}`);
        assert.equal(photos[0].getAttribute("src"), "/table.jpg");
        assert.equal(dom.window.document.querySelector(".scene__marker"), null);
        await view.close();
      }
    }
  });

  test(`${mode} description keeps one interactive photo when answers use markers`, async () => {
    const task = lesson();
    if (task.publicContent.kind !== "grammarLesson") throw new Error("Expected grammar fixture");
    task.publicContent.checkEachQuestion = checkEachQuestion;
    task.publicContent.focus = "sceneDescription";
    task.publicContent.questions[0].options = [{ optionId: "cup-option", label: "1" }];
    task.publicContent.questions[0].markerObjectIds = { "cup-option": "cup" };
    await mount(task, descriptionScene);
    assert.equal(dom.window.document.querySelectorAll('.scene img[alt="Table"]').length, 1);
    const marker = dom.window.document.querySelector<HTMLButtonElement>('button[aria-label="Marker 1"]');
    assert.ok(marker);
    assert.equal(button("Marker 1"), undefined, "marker questions do not repeat photo markers as choices");
    await surface.act(async () => { marker.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
    assert.equal(marker.getAttribute("aria-pressed"), "true");
    assert.equal(button("Check answer")?.disabled, false);
  });

  test(`${mode} grammar keeps the source photo available as context`, async () => {
    const task = lesson();
    if (task.publicContent.kind !== "grammarLesson") throw new Error("Expected grammar fixture");
    task.publicContent.checkEachQuestion = checkEachQuestion;
    await mount(task, descriptionScene);
    assert.equal(dom.window.document.querySelectorAll('.scene img[alt="Table"]').length, 1);
    assert.equal(dom.window.document.querySelector(".scene__marker"), null);
  });
}

test("a description with an object preview keeps its existing photo", async () => {
  const task = lesson();
  if (task.publicContent.kind !== "grammarLesson") throw new Error("Expected grammar fixture");
  task.publicContent.checkEachQuestion = false;
  task.publicContent.focus = "sceneDescription";
  task.publicContent.questions[0].sceneObjectId = "cup";
  await mount(task, descriptionScene);
  assert.equal(dom.window.document.querySelectorAll('.scene img[alt="Table"]').length, 1);
  assert.ok(dom.window.document.querySelector(".object-preview"));
});

test("A0 checked answers retain correctness, server feedback and notes across rerenders and restoration", async () => {
  let view = await mount(lesson());
  await click("la");
  replies.push(() => Response.json(checked(true)));
  await click("Check answer");
  const phrase = learningFeedback("correct", "t1:q1");
  await waitFor(() => assert.match(text(), /Correct!/));
  assert.ok(text().includes(phrase));
  assert.match(text(), /The article matches taza/);
  assert.match(text(), /\+10 Basil earned/);
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

function a2DescriptionLesson(): SessionTask {
  const task = lesson();
  if (task.publicContent.kind !== "grammarLesson") throw new Error("Expected grammar fixture");
  task.publicContent.practiceLevel = "A2";
  task.publicContent.focus = "sceneDescription";
  task.publicContent.title = "Describe the scene";
  task.publicContent.questions = [
    { questionId: "m01-q1", section: "Task 1 · Notice the facts", prompt: "Touch the object: La taza es roja.",
      translation: "Touch the object: The cup is red.", interactionType: "multipleChoice", tokenBank: [],
      options: [{ optionId: "cup-choice", label: "1" }, { optionId: "book-choice", label: "2" }],
      markerObjectIds: { "cup-choice": "cup", "book-choice": "book" } },
    { questionId: "m01-q2", section: "Task 1 · Notice the facts", prompt: "Build the second sentence.",
      interactionType: "sentenceBuilding", options: [], tokenBank: ["La", "taza", "está", "sobre", "la", "mesa."] },
    { questionId: "m01-q3", section: "Task 2 · Describe the scene", prompt: "Choose the matching description.",
      interactionType: "multipleChoice", tokenBank: [], options: [
        { optionId: "description-right", label: "Hay una taza roja junto al libro." },
        { optionId: "description-wrong", label: "Hay una mesa roja debajo del libro." },
      ], completeTranslation: "There is a red cup next to the book." },
    { questionId: "m01-q4", section: "Task 2 · Describe the scene", prompt: "Describe the scene.",
      interactionType: "sentenceBuilding", options: [], tokenBank: ["Hay", "un", "libro", "y", "una", "taza", "roja."] },
    { questionId: "m01-q5", section: "Task 3 · Check a detail", prompt: "A later question should stay hidden.",
      interactionType: "multipleChoice", tokenBank: [], options: [{ optionId: "later", label: "Future answer" }] },
  ];
  return task;
}

const a2Scene: Partial<Scene> = { ...descriptionScene, items: [...descriptionScene.items!, {
  ...descriptionScene.items![0], id: "book", word: "libro", translation: "book", marker: 2, x: 70,
}] };
const contextCard = () => dom.window.document.querySelector('[aria-label="Previous checked sentence"]');

test("A2 construction retains the checked photo sentence when advancing and after refresh", async () => {
  let view = await mount(a2DescriptionLesson(), a2Scene);
  assert.equal(contextCard(), null);
  const marker = dom.window.document.querySelector<HTMLButtonElement>('button[aria-label="Marker 1"]');
  assert.ok(marker);
  await surface.act(async () => marker.click());
  const result = { ...checked(true), questionId: "m01-q1", answer: "cup-choice", correctAnswer: "1" };
  replies.push(() => Response.json(result));
  await click("Check answer");
  await click("Next question");
  assert.match(contextCard()?.textContent ?? "", /La taza es roja/);
  assert.match(contextCard()?.textContent ?? "", /The cup is red/);
  assert.doesNotMatch(contextCard()?.textContent ?? "", /cup-choice|book-choice|^1$/);
  assert.doesNotMatch(text(), /La taza está sobre la mesa\.|A later question should stay hidden|Future answer/);
  await view.close();
  savedChecks = [result];
  view = await mount(a2DescriptionLesson(), a2Scene);
  assert.match(text(), /Build the second sentence/);
  assert.match(contextCard()?.textContent ?? "", /La taza es roja/);
  assert.equal(requests.length, 1, "restoring context never submits another answer");
  await view.close();
});

test("A2 description context uses the previous corrected sentence instead of a wrong answer or another section", async () => {
  savedChecks = [
    { ...checked(true), questionId: "m01-q1", answer: "cup-choice", correctAnswer: "1" },
    { ...checked(true), questionId: "m01-q2", answer: "An earlier section's sentence.", correctAnswer: "An earlier section's sentence." },
    { ...checked(false), questionId: "m01-q3", answer: "description-wrong", correctAnswer: "Hay una taza roja junto al libro." },
    { ...checked(true), questionId: "m01-q5", answer: "later", correctAnswer: "Future answer" },
  ];
  await mount(a2DescriptionLesson(), a2Scene);
  assert.match(contextCard()?.textContent ?? "", /Hay una taza roja junto al libro/);
  assert.match(contextCard()?.textContent ?? "", /There is a red cup next to the book/);
  assert.doesNotMatch(contextCard()?.textContent ?? "", /Hay una mesa roja|description-wrong|earlier section|Future answer/);
  assert.doesNotMatch(text(), /Hay un libro y una taza roja\.|A later question should stay hidden|Future answer/);
  assert.equal(requests.length, 0);
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

function situationLesson(missionId: "M04" | "M05") {
  const task = lesson(missionId);
  if (task.publicContent.kind !== "grammarLesson") throw new Error("Expected grammar fixture");
  const content = task.publicContent;
  content.focus = missionId === "M04" ? "ownership" : "preference";
  content.missionSnapshot = {
    missionId, level: "A0", situation: missionId === "M04" ? "lostAndFound" : "everydayChoice",
    taughtChunks: [], pretend: true,
  };
  const positive = missionId === "M04" ? "Es mío" : "Me gusta";
  const negative = missionId === "M04" ? "No es mío" : "No me gusta";
  const question = content.questions[0];
  delete question.allowRetry;
  question.options = [{ optionId: "a", label: positive }, { optionId: "b", label: negative }];
  question.gapType = "chunkChoice";
  question.slotTemplate = "___.";
  question.completeChunk = `${positive}.`;
  content.questions = [question, { ...question, questionId: "q2" }];
  const check = (questionId: string, correct: boolean): LessonAnswerCheck => {
    const result = { ...checked(correct), questionId, correctAnswer: positive };
    // These single-attempt questions omit both fields in real API responses.
    delete result.attemptsLeft;
    return result;
  };
  return { task, positive, negative, check };
}

for (const missionId of ["M04", "M05"] as const) {
  test(`${missionId} finishes after correcting an earlier mistake and submits the original grades`, async () => {
    const { task, positive, negative, check } = situationLesson(missionId);
    await mount(task);
    const progress = () => dom.window.document.querySelector(".trail__label")?.textContent;
    assert.equal(progress(), "Question 1 of 2");
    assert.equal(dom.window.document.querySelectorAll(".question-progress .label").length, 0);
    await click(negative);
    replies.push(() => Response.json(check("q1", false)));
    await click("Check answer");
    await waitFor(() => assert.equal(button("Next question")?.disabled, false));
    await click(positive);
    await click("Next question");
    assert.equal(progress(), "Question 2 of 2");
    await click(positive);
    replies.push(() => Response.json(check("q2", true)));
    await click("Check answer");
    await waitFor(() => assert.equal(button("Finish task")?.disabled, false));
    actions.push(() => action(task, false, "1 of 2 questions correct."));
    await click("Finish task");
    assert.deepEqual(taskActions, [{ action: "attempts", body: {
      inputMode: "vocabularyReview", answers: { q1: "b", q2: "a" }, typedAnswers: {},
    } }]);
    assert.match(text(), /1 of 2 questions correct/);
  });

  test(`${missionId} can finish after reload with wrong saved answers and no local corrections`, async () => {
    const { task, check } = situationLesson(missionId);
    savedChecks = [check("q1", false), check("q2", false)];
    await mount(task);
    assert.equal(button("Finish task")?.disabled, false);
    actions.push(() => action(task, false, "0 of 2 questions correct."));
    await click("Finish task");
    assert.equal(requests.length, 0, "restoring a lesson does not regrade or reward corrections");
    assert.deepEqual(taskActions[0].body, {
      inputMode: "vocabularyReview", answers: { q1: "b", q2: "b" }, typedAnswers: {},
    });
  });
}

test("an explicitly retryable lesson cannot finish while a saved retry is still open", async () => {
  savedChecks = [checked(false, 2)];
  await mount(lesson("M06"));
  assert.equal(button("Finish task")?.disabled, true);
  assert.equal(taskActions.length, 0);
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

test("reading completion stays neutral and does not turn XP into Basil", async () => {
  const task: SessionTask = { ...lesson(), kind: "grammarExplanation", publicContent: { kind: "grammarExplanation", title: "Read the pattern", explanation: "Taza uses la.", examples: [] } };
  await mount(task);
  actions.push(() => action(task, null, "Reading participation saved.", 3));
  await click("Mark complete");
  await waitFor(() => assert.match(text(), /Reading participation saved/));
  assert.ok(text().includes(learningFeedback("saved", task.id)));
  assert.ok(!text().includes(learningFeedback("correct", task.id)));
  assert.doesNotMatch(text(), /\+3 Basil earned/);
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
  assert.equal(dom.window.document.querySelector('.question-basil'), null, "historical grades do not imply an earned reward");
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
  const task = vocabularyTask();
  await mount(task);
  await click("Start quick quiz");
  replies.push(() => Response.json({ questionId: "word1", acceptedOptionId: "table", isCorrect: false, correctOptionId: "cup", basilEarned: 5 }));
  await click("table");
  await waitFor(() => assert.match(text(), /\+5 Basil earned/));
  assert.ok(dom.window.document.querySelector(".question-basil.basil-reward"));
  assert.ok(text().includes(learningFeedback("incorrect", "t1:word1")));
  assert.match(text(), /Incorrect\. The correct answer is cup/);
  assert.equal(button("cup")?.disabled, true);
  assert.equal(button("Try again"), undefined);
  assert.equal(button("Next question")?.disabled, false);
});

function vocabularyTask(): SessionTask {
  return { ...lesson(), kind: "vocabularyIntroduction", publicContent: {
    kind: "vocabularyIntroduction", title: "Photo words", allowTypingPractice: true,
    words: [{ learningKey: "cup", termType: "object", vocabularyItemId: "v1", sceneObjectId: null, targetText: "taza", translation: "cup",
      partOfSpeech: "noun", gender: null, pluralForm: null, phoneticText: null, pronunciationAudioAssetId: null, exampleSentence: null }],
    questions: [{ questionId: "word1", prompt: "What is taza?", correctOptionId: "cup",
      options: [{ optionId: "cup", label: "cup" }, { optionId: "table", label: "table" }] }],
  } };
}

test("returning home from word review leaves the task unchanged", async () => {
  await mount(vocabularyTask());
  await click("Return home");
  assert.match(text(), /Home destination/);
  assert.deepEqual(taskActions, []);
  assert.deepEqual(requests, []);
});

test("skipping word review marks the whole activity skipped before returning to tasks", async () => {
  const task = vocabularyTask();
  await mount(task);
  const skip = button("Skip this task");
  assert.ok(skip);
  const description = dom.window.document.getElementById(skip.getAttribute("aria-describedby") ?? "");
  assert.match(description?.textContent ?? "", /whole word activity/);
  actions.push(() => ({ ...action(task, null, "Skipped"), task: { ...task, status: "skipped" } }));
  await click("Skip this task");
  assert.deepEqual(taskActions, [{ action: "skip", body: undefined }]);
  assert.match(text(), /Task list destination/);
  assert.deepEqual(requests, []);
});

test("the flashcard shortcut opens exercises without submitting or rewarding the task", async () => {
  const task = vocabularyTask();
  if (task.publicContent.kind !== "vocabularyIntroduction") throw new Error("Expected vocabulary fixture");
  task.publicContent.words.push({ ...task.publicContent.words[0], learningKey: "table", targetText: "mesa", translation: "table" });
  await mount(task);
  await waitFor(() => assert.equal(button("Go to exercises")?.disabled, false));
  await click("Go to exercises");
  assert.match(text(), /What is taza/);
  assert.deepEqual(requests, []);
  assert.deepEqual(taskActions, []);
  assert.doesNotMatch(text(), /Basil earned/);
  replies.push(() => Response.json({ questionId: "word1", acceptedOptionId: "cup", isCorrect: true, correctOptionId: "cup", basilEarned: 10 }));
  await click("cup");
  await waitFor(() => assert.match(text(), /\+10 Basil earned/));
  assert.deepEqual(requests, [{ questionId: "word1", optionId: "cup", review: false }]);
  assert.deepEqual(taskActions, []);
});

test("skipped vocabulary tasks and tasks without questions do not offer the exercise shortcut", async () => {
  const skipped = vocabularyTask();
  skipped.status = "skipped";
  const revision = await mount(skipped);
  assert.equal(button("Go to exercises"), undefined);
  await revision.close();
  const task = vocabularyTask();
  if (task.publicContent.kind !== "vocabularyIntroduction") throw new Error("Expected vocabulary fixture");
  task.publicContent.questions = [];
  await mount(task);
  assert.equal(button("Go to exercises"), undefined);
  assert.deepEqual(requests, []);
  assert.deepEqual(taskActions, []);
});

test("exercise entry waits for saved vocabulary answers before opening the quiz", async () => {
  let finishRestore: (response: Response) => void = () => { throw new Error("Restore has not started"); };
  vocabularyRestoreReply = () => new Promise<Response>(resolve => { finishRestore = resolve; });
  await mount(vocabularyTask());
  assert.equal(button("Go to exercises")?.disabled, true);
  assert.equal(button("Start quick quiz")?.disabled, true);
  assert.doesNotMatch(text(), /What is taza/);
  await surface.act(async () => finishRestore(Response.json({ checks: [] })));
  await waitFor(() => assert.equal(button("Go to exercises")?.disabled, false));
  await click("Go to exercises");
  assert.match(text(), /What is taza/);
  assert.deepEqual(requests, []);
  assert.deepEqual(taskActions, []);
});

test("saved vocabulary answers restore their accepted choice and Basil without another check", async () => {
  vocabularySaved = [{ questionId: "word1", acceptedOptionId: "table", isCorrect: false, correctOptionId: "cup", basilEarned: 5 }];
  await mount(vocabularyTask());
  await waitFor(() => assert.match(text(), /\+5 Basil earned/));
  assert.match(text(), /Incorrect. The correct answer is cup/);
  assert.equal(button("table")?.disabled, true);
  assert.equal(requests.length, 0);
});

test("a failed vocabulary restore blocks checking rather than starting with empty answers", async () => {
  vocabularyRestoreFails = true;
  await mount(vocabularyTask());
  await waitFor(() => assert.match(text(), /We couldn’t restore your word answers/));
  assert.equal(button("Go to exercises")?.disabled, true);
  assert.equal(button("Start quick quiz")?.disabled, true);
  assert.equal(button("table"), undefined);
  assert.doesNotMatch(text(), /\+\d+ Basil earned/);
  assert.equal(requests.length, 0);
});

test("a lost vocabulary reply shows no reward until the canonical saved answer returns", async () => {
  await mount(vocabularyTask());
  await waitFor(() => assert.doesNotMatch(text(), /Restoring word answers/));
  await click("Start quick quiz");
  replies.push(() => { throw new Error("Reply lost"); });
  await click("table");
  await waitFor(() => assert.match(text(), /We couldn’t save this answer/));
  assert.doesNotMatch(text(), /\+\d+ Basil earned/);
  replies.push(() => Response.json({ questionId: "word1", acceptedOptionId: "table", isCorrect: false, correctOptionId: "cup", basilEarned: 5 }));
  await click("Retry answer");
  await waitFor(() => assert.match(text(), /\+5 Basil earned/));
  assert.deepEqual(requests[0], requests[1]);
});

test("refreshing vocabulary checks keeps the learner's typing stage and unfinished text", async () => {
  const view = await mount(vocabularyTask());
  await waitFor(() => assert.doesNotMatch(text(), /Restoring word answers/));
  await click("Start quick quiz");
  const accepted = { questionId: "word1", acceptedOptionId: "cup", isCorrect: true, correctOptionId: "cup", basilEarned: 10 };
  replies.push(() => Response.json(accepted));
  await click("cup");
  await waitFor(() => assert.ok(button("Next question")));
  await click("Next question");
  const input = dom.window.document.querySelector<HTMLInputElement>('input[aria-label="Type cup"]');
  assert.ok(input);
  await surface.act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value")!.set!.call(input, "taz");
    input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
  assert.equal(button("Check answer")?.disabled, false);
  vocabularySaved = [accepted];
  await surface.act(async () => { await view.client.invalidateQueries({ queryKey: queryKeys.vocabularyChecks("t1") }); });
  assert.equal(dom.window.document.querySelector('input[aria-label="Type cup"]'), input);
  assert.equal(input.value, "taz");
  assert.equal(button("Check answer")?.disabled, false);
  assert.equal(requests.length, 1);
});

test("an accent-only typing answer is accepted with yellow guidance", async () => {
  const task = vocabularyTask();
  if (task.publicContent.kind !== "vocabularyIntroduction") throw new Error("Expected vocabulary fixture");
  task.publicContent.words[0].targetText = "canapé";
  task.publicContent.words[0].translation = "sofa";
  task.publicContent.questions[0].options[0] = { optionId: "canapé", label: "canapé" };
  task.publicContent.questions[0].correctOptionId = "canapé";
  await mount(task);
  await waitFor(() => assert.doesNotMatch(text(), /Restoring word answers/));
  await click("Start quick quiz");
  replies.push(() => Response.json({ questionId: "word1", acceptedOptionId: "canapé", isCorrect: true, correctOptionId: "canapé", basilEarned: 10 }));
  await click("canapé");
  await waitFor(() => assert.ok(button("Next question")));
  await click("Next question");

  const input = dom.window.document.querySelector<HTMLInputElement>('input[aria-label="Type sofa"]');
  assert.ok(input);
  await surface.act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value")!.set!.call(input, "canape");
    input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
  replies.push(() => Response.json({ learningKey: "cup", isCorrect: false, isClose: true, correctAnswer: "canapé", revealed: false, basilEarned: 0 }));
  await click("Check answer");

  await waitFor(() => assert.match(text(), /Close! You’re missing some accents/));
  assert.match(text(), /Write it as canapé/);
  assert.ok(dom.window.document.querySelector(".feedback--neutral"));
  assert.equal(input.disabled, true);
  assert.ok(button("Finish task"));
  assert.equal(button("I forgot, lift the lid"), undefined);
});

test("teaching cards highlight their photo object and practice interleaves recognition before typing", async () => {
  const task = vocabularyTask();
  if (task.publicContent.kind !== "vocabularyIntroduction") throw new Error("Expected vocabulary fixture");
  task.publicContent.words = [
    { ...task.publicContent.words[0], learningKey: "cup", sceneObjectId: "object-cup", targetText: "taza", translation: "cup" },
    { ...task.publicContent.words[0], learningKey: "book", sceneObjectId: "object-book", targetText: "libro", translation: "book" },
    { ...task.publicContent.words[0], learningKey: "chair", sceneObjectId: "object-chair", targetText: "silla", translation: "chair" },
  ];
  task.publicContent.questions = task.publicContent.words.map((word, index) => ({
    questionId: `word-${index + 1}`,
    prompt: `Which word means "${word.translation}"?`,
    correctOptionId: word.targetText,
    options: task.publicContent.kind === "vocabularyIntroduction"
      ? task.publicContent.words.map(option => ({ optionId: option.targetText, label: option.targetText }))
      : [],
  }));
  await mount(task);
  await waitFor(() => assert.doesNotMatch(text(), /Restoring word answers/));

  assert.equal(dom.window.document.querySelector(".scene__marker--active .scene__marker-label")?.textContent, "1");
  await click("Next");
  assert.equal(dom.window.document.querySelector(".scene__marker--active .scene__marker-label")?.textContent, "2");
  await click("Next");
  await click("Start quick quiz");

  replies.push(() => Response.json({ questionId: "word-1", acceptedOptionId: "taza", isCorrect: true, correctOptionId: "taza", basilEarned: 10 }));
  await click("taza");
  await waitFor(() => assert.ok(button("Next question")));
  await click("Next question");
  replies.push(() => Response.json({ questionId: "word-2", acceptedOptionId: "libro", isCorrect: true, correctOptionId: "libro", basilEarned: 10 }));
  await click("libro");
  await waitFor(() => assert.ok(button("Next question")));
  await click("Next question");

  const typing = dom.window.document.querySelector<HTMLInputElement>('input[aria-label="Type cup"]');
  assert.ok(typing);
  await surface.act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value")!.set!.call(typing, "taza");
    typing.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  });
  replies.push(() => Response.json({ learningKey: "cup", isCorrect: true, correctAnswer: "taza", revealed: false, basilEarned: 10 }));
  await click("Check answer");
  await waitFor(() => {
    assert.ok(button("Next question"));
    assert.match(text(), /\+10 Basil earned/);
  });
  await click("Next question");

  assert.match(text(), /Which word means "chair"/);
});

test("a completed grouped lesson restores only server-awarded Basil alongside its saved review", async () => {
  const task = lesson();
  task.status = "completed";
  if (task.publicContent.kind !== "grammarLesson") throw new Error("Expected grammar fixture");
  task.publicContent.checkEachQuestion = false;
  savedChecks = [checked(false)];
  latestAttempt = { id: "completed1", attemptNumber: 1, text: "", optionId: null, isCorrect: false, feedback: "Saved review details.",
    evaluationDetails: null, assistance: null, answers: { q1: "b" },
    reviewDetails: { questionResults: { q1: false }, correctAnswers: { q1: "a" }, questionOutcomes: [checked(false).outcome] } };
  await mount(task);
  await waitFor(() => assert.match(text(), /\+5 Basil earned/));
  assert.match(text(), /Saved review details/);
  assert.match(text(), /The correct answer is la/);
  assert.match(text(), /Taza is feminine/);
  assert.equal(requests.length, 0, "opening a review only reads the saved reward");
});

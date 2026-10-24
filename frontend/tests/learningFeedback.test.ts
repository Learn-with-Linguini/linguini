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
let latestAttempt: LatestClueAttempt | null = null;
const replies: (() => Response | Promise<Response>)[] = [];
const actions: (() => TaskActionResult | null)[] = [];
const requests: Record<string, unknown>[] = [];
const originalFetch = globals.fetch;
globals.fetch = async (input: unknown, init?: RequestInit) => {
  const path = new URL(String(input)).pathname;
  if (path.endsWith("/vocabulary-checks")) return vocabularyRestoreFails ? Response.json({ detail: { message: "Unavailable" } }, { status: 503 }) : Response.json({ checks: vocabularySaved });
  if (path.endsWith("/lesson-checks")) return Response.json({ checks: savedChecks, assistanceSteps: {} });
  if (path.endsWith("/latest-attempt")) return Response.json({ attempt: latestAttempt });
  requests.push(JSON.parse(String(init?.body ?? "{}")));
  return replies.shift()?.() ?? new Response("Unexpected fixture request", { status: 500 });
};
const cleanups = new Set<() => Promise<void>>();
test.beforeEach(() => { savedChecks = []; vocabularySaved = []; vocabularyRestoreFails = false; latestAttempt = null; replies.length = 0; actions.length = 0; requests.length = 0; });
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
    await surface.act(async () => { marker.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); });
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
  assert.ok(text().includes(learningFeedback("incorrect", "t1:word1")));
  assert.match(text(), /Incorrect\. The correct answer is cup/);
  assert.equal(button("cup")?.disabled, true);
  assert.equal(button("Try again"), undefined);
  assert.equal(button("Type a word")?.disabled, false);
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
  await click("Start quick quiz");
  assert.equal(button("table")?.disabled, true);
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
  await waitFor(() => assert.ok(button("Type a word")));
  await click("Type a word");
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
  await waitFor(() => assert.ok(button("Type a word")));
  await click("Type a word");

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

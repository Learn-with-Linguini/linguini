import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { ChatInvitePreview, ChatRound, ChatSnapshot } from "../src/lib/friendChats.ts";

process.env.VITE_API_BASE_URL = "http://api.test";
const { chatDraftKey, safeFriendChat, prepareChatCommand, saveChatDraft, readChatDraft, clearChatDrafts, friendInviteStorageKey } = await import("../src/lib/friendChats.ts");
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://app.test/ispy/friends/chat1", pretendToBeVisual: true });
const globals = globalThis as Record<string, unknown>;
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (globals[key] !== undefined) continue;
  try { globals[key] = (dom.window as unknown as Record<string, unknown>)[key]; } catch { /* Read-only browser globals. */ }
}
Object.defineProperty(globalThis, "window", { value: dom.window, configurable: true });
Object.defineProperty(globalThis, "document", { value: dom.window.document, configurable: true });
Object.defineProperty(globalThis, "sessionStorage", { value: dom.window.sessionStorage, configurable: true });
globals.IS_REACT_ACT_ENVIRONMENT = true;
const NativeMessageChannel = globalThis.MessageChannel;
const channels: MessageChannel[] = [];
globals.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); channels.push(this); }
};

const now = "2026-10-30T18:00:00Z";
const target = { key: "secret-key", label: "cup", word: "la taza", translation: "cup", x: .23, y: .47, width: .12, height: .2 };
function round(overrides: Partial<ChatRound> = {}): ChatRound {
  return { id: "round1", senderId: "u2", status: "awaitingGuess", photoStatus: "ready",
    imageUrl: "/api/v1/friend-chats/chat1/rounds/round1/image?width=640", createdAt: now,
    objects: [target], target, clueOptions: [{ id: "red", text: "Es roja.", translation: "It is red.", concept: "adjective",
      cheatSheet: { missionId: "M02", practiceLevel: "A0", contentVersion: 2 } },
    { id: "under", text: "Está debajo de la mesa.", translation: "It is under the table.", concept: "position",
      cheatSheet: { missionId: "M03", practiceLevel: "A0", contentVersion: 1 } }],
    messages: [{ id: "clue1", type: "clue", senderId: "u2", text: "Es roja.", createdAt: now }], retryable: false,
    ...overrides };
}
function fixture(overrides: Partial<ChatSnapshot> = {}): ChatSnapshot {
  return { id: "chat1", status: "active", revision: 4, meId: "u1", targetLanguageCode: "es", viewerLevel: "A0",
    partner: { id: "u2", displayName: "Leo" }, creator: { id: "u2", displayName: "Leo" },
    inviteStatus: "accepted", createdAt: now, updatedAt: now, activeRound: round(), rounds: [], ...overrides };
}
const defaultState = () => ({ user: { id: "u1", cameraEnabled: true, microphoneEnabled: false },
  activeProfile: { id: "profile1", userId: "u1", targetLanguageCode: "es", sourceLanguageCode: "en", proficiencyLevel: "A0" } });
let state = defaultState();
let snapshot = fixture();
let preview: ChatInvitePreview = { status: "open", creator: { id: "u2", displayName: "Leo" }, targetLanguageCode: "es" };
const writes: { path: string; body: Record<string, unknown> }[] = [];
const reads: string[] = [];
const replies: (() => Response | Promise<Response>)[] = [];
const apiPrefix = "/api/v1/friend-chats";
globals.fetch = async (input: unknown, init?: RequestInit) => {
  const path = String(input).replace("http://api.test", "");
  if (init?.method === "POST") {
    writes.push({ path, body: JSON.parse(String(init.body)) });
    if (path === `${apiPrefix}/invites/preview`) return Response.json(preview);
    if (path.endsWith("/help")) return Response.json({ explanation: "The clue describes a colour.", vocabulary: [{ word: "roja", meaning: "red" }],
      hint: "Look below the large table.", cheatsheetRefs: [{ missionCode: "M02", level: "A0", contentVersion: 2 }] });
    return replies.shift()?.() ?? Response.json(snapshot);
  }
  reads.push(path);
  if (path.endsWith("/image?width=640")) return new Response(new Blob(["photo"], { type: "image/webp" }));
  if (path === apiPrefix) return Response.json([snapshot]);
  if (path === `${apiPrefix}/chat1`) return Response.json(snapshot);
  if (path.startsWith("/api/v1/learning-resources/cheatsheets/")) return Response.json({ missionId: "M02", practiceLevel: "A0", contentVersion: 2,
    languageCode: "es", textDirection: "ltr", title: "Stored adjective guide", summary: "The shared lesson guide.", concepts: [] });
  return new Response("not found", { status: 404 });
};

const here = dirname(fileURLToPath(import.meta.url));
async function bundle() {
  const folder = mkdtempSync(join(tmpdir(), "linguini-chat-test-"));
  const entry = join(here, `.friend-chat-entry-${crypto.randomUUID()}.ts`);
  writeFileSync(entry, [
    'export { createElement as h, act } from "react";', 'export { createRoot } from "react-dom/client";',
    'export { MemoryRouter, Route, Routes } from "react-router-dom";', 'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
    'export { AppStateContext } from "../src/state/context";', 'export { AuthProvider } from "../src/state/Auth";',
    'export { FriendChat } from "../src/pages/FriendChat";', 'export { FriendChats } from "../src/pages/FriendChats";',
  ].join("\n"));
  try {
    const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
      plugins: [{ name: "test-environment", transform: code => code.replaceAll("import.meta.env?.VITE_API_BASE_URL", '"http://api.test"').replaceAll("import.meta.env.DEV", "true") },
        { name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null, load: id => id === "\0empty-css" ? "export default {};" : null }],
    });
    const { output } = await bundler.generate({ format: "esm" }); await bundler.close();
    const path = join(folder, "bundle.mjs"); writeFileSync(path, output[0].code);
    return await import(pathToFileURL(path).href);
  } finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
}
const surface = await bundle();
const cleanups = new Set<() => Promise<void>>();
const bodyText = () => dom.window.document.body.textContent ?? "";
const buttons = (label: string) => [...dom.window.document.querySelectorAll<HTMLButtonElement>("button")].filter(element => element.textContent?.trim() === label);
async function waitFor(assertion: () => void, timeoutMs = 2500) {
  let lastError: unknown; const deadline = Date.now() + timeoutMs;
  do {
    await surface.act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
    try { assertion(); return; } catch (error) { lastError = error; }
  } while (Date.now() < deadline);
  throw lastError;
}
async function clickElement(element: Element | undefined | null) {
  assert.ok(element, "expected an interactive element");
  assert.notEqual((element as HTMLButtonElement).disabled, true);
  await surface.act(async () => element.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })));
}
async function click(label: string, occurrence = 0) {
  await clickElement(buttons(label)[occurrence]);
  await waitFor(() => assert.doesNotMatch(bodyText(), /Saving your action…|Creating your private chat…|Joining…/));
}
async function setValue(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const prototype = element.tagName === "TEXTAREA" ? dom.window.HTMLTextAreaElement.prototype : dom.window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value")!.set!;
  await surface.act(async () => { setter.call(element, value); element.dispatchEvent(new dom.window.Event("input", { bubbles: true })); });
}
async function mount(which: "chat" | "list" = "chat", staleTime = 0) {
  const container = dom.window.document.createElement("div"); dom.window.document.body.replaceChildren(container);
  const root = surface.createRoot(container);
  const client = new surface.QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0, staleTime }, mutations: { gcTime: 0 } } });
  let closed = false;
  const close = async () => { if (closed) return; closed = true; try { await surface.act(async () => root.unmount()); } finally { client.clear(); cleanups.delete(close); } };
  cleanups.add(close);
  const render = async () => surface.act(async () => root.render(surface.h(surface.QueryClientProvider, { client },
    surface.h(surface.AuthProvider, null, surface.h(surface.AppStateContext.Provider, { value: state },
      surface.h(surface.MemoryRouter, { initialEntries: [which === "chat" ? "/ispy/friends/chat1" : "/ispy/friends"] },
        surface.h(surface.Routes, null,
          surface.h(surface.Route, { path: "/ispy/friends/:chatId", element: surface.h(surface.FriendChat) }),
          surface.h(surface.Route, { path: "/ispy/friends", element: surface.h(surface.FriendChats) }),
          surface.h(surface.Route, { path: "/profile", element: surface.h("p", null, "Profile destination") }),
        )))))));
  await render();
  await waitFor(() => assert.match(bodyText(), which === "list" ? /Your photo chats/ : /Leo|Your I-Spy chat|Chat unavailable/));
  return { client, close, render };
}
async function selectPhotoWithKeyboard(key = "Enter") {
  await waitFor(() => assert.ok(dom.window.document.querySelector('.friend-photo__image[role="button"] img')));
  const photo = dom.window.document.querySelector('.friend-photo__image[role="button"]')!;
  await surface.act(async () => photo.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key, bubbles: true })));
}
test.beforeEach(() => {
  state = defaultState(); snapshot = fixture(); preview = { status: "open", creator: { id: "u2", displayName: "Leo" }, targetLanguageCode: "es" };
  writes.length = 0; reads.length = 0; replies.length = 0; dom.window.sessionStorage.clear(); dom.window._uxa = [];
  delete (dom.window as unknown as { linguiniFriendInvite?: string }).linguiniFriendInvite;
});
test.afterEach(async () => { for (const close of [...cleanups]) await close(); });
test.after(async () => {
  for (const close of [...cleanups]) await close(); dom.window.close();
  for (const channel of channels) { channel.port1.close(); channel.port2.close(); }
  globals.MessageChannel = NativeMessageChannel;
});

test("receiver snapshots strip target, object geometry and draft options until completion without mutating the response", () => {
  const raw = fixture(); const safe = safeFriendChat(raw);
  assert.deepEqual(safe.activeRound?.objects, []); assert.equal(safe.activeRound?.target, null); assert.deepEqual(safe.activeRound?.clueOptions, []);
  assert.equal(raw.activeRound?.target?.key, "secret-key");
  raw.activeRound!.status = "completed";
  assert.equal(safeFriendChat(raw).activeRound?.target?.word, "la taza");
  raw.activeRound!.status = "cancelled";
  assert.equal(safeFriendChat(raw).activeRound?.target, null);
});

test("a receiver sees the original clue and unmarked photo without private target words, labels or object choices", async () => {
  const view = await mount();
  await waitFor(() => assert.ok(dom.window.document.querySelector('.friend-photo__image[role="button"] img')));
  assert.match(bodyText(), /Es roja\./); assert.doesNotMatch(bodyText(), /la taza|secret-key|cup|Object 1|B1/);
  assert.equal(dom.window.document.querySelectorAll(".friend-photo__object").length, 0);
  assert.ok(dom.window.document.querySelector(".friend-chat[data-cs-mask]"), "private conversation contents are masked before replay collection");
  const cached = view.client.getQueryData(["friend-chats", "u1", "profile1", "chat1"]) as ChatSnapshot;
  assert.deepEqual(cached.activeRound?.objects, []); assert.equal(cached.activeRound?.target, null);
  assert.equal(writes.length, 0);
});

test("an invitation in another target language offers profile selection without changing the learner or joining", async () => {
  dom.window.sessionStorage.setItem(friendInviteStorageKey, "private-invite-token"); preview.targetLanguageCode = "fr";
  await mount("list"); await waitFor(() => assert.match(bodyText(), /Switch to a matching profile/));
  assert.equal(buttons("Join I-Spy chat").length, 0); assert.equal(state.activeProfile.targetLanguageCode, "es");
  assert.deepEqual(writes.map(item => item.path), [`${apiPrefix}/invites/preview`]);
  assert.deepEqual(writes[0].body, { inviteToken: "private-invite-token" });
  assert.equal(reads.some(path => path.includes("private-invite-token")), false);
  await click("Choose a language profile"); assert.match(bodyText(), /Profile destination/);
});

test("a full invitation does not render creator identity or offer a join action", async () => {
  dom.window.sessionStorage.setItem(friendInviteStorageKey, "closed-invite-token"); preview = { status: "full" };
  snapshot = fixture({ partner: null, activeRound: null, rounds: [] });
  await mount("list"); await waitFor(() => assert.match(bodyText(), /already has two players/));
  assert.equal(buttons("Join I-Spy chat").length, 0);
  assert.doesNotMatch(dom.window.document.querySelector(".friend-invite")?.textContent ?? "", /Leo|Spanish|French/);
});

test("a compatible invitation is joined only after confirmation and does not require matching proficiency", async () => {
  dom.window.sessionStorage.setItem(friendInviteStorageKey, "private-invite-token");
  await mount("list"); await waitFor(() => assert.ok(buttons("Join I-Spy chat")[0]));
  assert.equal(writes.filter(item => item.path.endsWith("/join")).length, 0);
  await click("Join I-Spy chat"); await waitFor(() => assert.match(bodyText(), /Tap the object you think they chose/));
  const join = writes.find(item => item.path.endsWith("/join"))!;
  assert.equal(join.body.languageProfileId, "profile1"); assert.equal(join.body.inviteToken, "private-invite-token");
  assert.equal("proficiencyLevel" in join.body, false); assert.equal(dom.window.sessionStorage.getItem(friendInviteStorageKey), null);
});

test("an inviter returning from sharing refreshes a fresh cached invitation without manually reloading", async () => {
  let hidden = true;
  Object.defineProperty(dom.window.document, "hidden", { configurable: true, get: () => hidden });
  Object.defineProperty(dom.window.document, "visibilityState", { configurable: true, get: () => hidden ? "hidden" : "visible" });
  snapshot = fixture({ status: "waiting", revision: 0, creator: { id: "u1", displayName: "Learner" }, partner: null, inviteStatus: "open", activeRound: null });
  saveChatDraft(chatDraftKey("u1", "chat1", "invite"), "a".repeat(43));
  try {
    await mount("chat", 30_000);
    await waitFor(() => assert.match(bodyText(), /Share this link with one friend/));
    const before = reads.filter(path => path === `${apiPrefix}/chat1`).length;
    snapshot = fixture({ status: "active", revision: 1, creator: { id: "u1", displayName: "Learner" }, activeRound: null });
    hidden = false;
    await surface.act(async () => dom.window.dispatchEvent(new dom.window.Event("visibilitychange")));
    await waitFor(() => assert.ok(buttons("Start an I-Spy")[0]), 4500);
    assert.doesNotMatch(bodyText(), /Share this link with one friend/);
    assert.ok(reads.filter(path => path === `${apiPrefix}/chat1`).length > before);
    assert.equal(writes.length, 0, "joining a friend is observed without a mutation from the inviter");
  } finally {
    delete (dom.window.document as unknown as { hidden?: boolean }).hidden;
    delete (dom.window.document as unknown as { visibilityState?: string }).visibilityState;
  }
});

test("polling notices a friend joining while the inviter stays on the invitation screen", async () => {
  snapshot = fixture({ status: "waiting", revision: 0, creator: { id: "u1", displayName: "Learner" }, partner: null, inviteStatus: "open", activeRound: null });
  saveChatDraft(chatDraftKey("u1", "chat1", "invite"), "a".repeat(43));
  await mount("chat", 30_000);
  await waitFor(() => assert.match(bodyText(), /Share this link with one friend/));
  const before = reads.filter(path => path === `${apiPrefix}/chat1`).length;
  snapshot = fixture({ status: "active", revision: 1, creator: { id: "u1", displayName: "Learner" }, activeRound: null });
  await waitFor(() => assert.ok(buttons("Start an I-Spy")[0]), 4500);
  assert.doesNotMatch(bodyText(), /Share this link with one friend/);
  assert.ok(reads.filter(path => path === `${apiPrefix}/chat1`).length > before);
  assert.equal(writes.length, 0);
});

test("choosing a detected object previews its identity and requires an explicit confirmation before changing server state", async () => {
  snapshot.activeRound = round({ senderId: "u1", status: "selectingTarget", target: null, messages: [] });
  await mount(); await waitFor(() => assert.ok(dom.window.document.querySelector('button[aria-label="Choose cup"]')));
  await clickElement(dom.window.document.querySelector('button[aria-label="Choose cup"]'));
  assert.match(bodyText(), /Is this your object/); assert.match(bodyText(), /la taza/); assert.equal(writes.length, 0);
  replies.push(() => { snapshot = fixture({ activeRound: round({ senderId: "u1", status: "composingClue", messages: [] }), revision: 5 }); return Response.json(snapshot); });
  await click("Use this object");
  assert.equal(writes[0].path, `${apiPrefix}/chat1/rounds/round1/target`);
  assert.equal(writes[0].body.objectKey, "secret-key"); assert.equal(writes[0].body.confirm, true);
  await waitFor(() => assert.match(bodyText(), /Build your clue/));
});

test("a custom photo selection requests an identity proposal and confirms it separately", async () => {
  snapshot.activeRound = round({ senderId: "u1", status: "selectingTarget", target: null, messages: [] });
  await mount(); await click("Add another object");
  replies.push(() => { snapshot = fixture({ revision: 5, activeRound: round({ senderId: "u1", status: "selectingTarget", target: { ...target, key: "custom-proposal" }, messages: [] }) }); return Response.json(snapshot); });
  await selectPhotoWithKeyboard();
  await waitFor(() => assert.ok(buttons("Use this object")[0]));
  assert.equal(writes.length, 1); assert.equal(writes[0].body.confirm, false); assert.equal(writes[0].body.x, .5); assert.equal(writes[0].body.y, .5);
  replies.push(() => { snapshot.activeRound!.status = "composingClue"; snapshot.revision = 6; return Response.json(snapshot); });
  await click("Use this object");
  assert.equal(writes[1].body.objectKey, "custom-proposal"); assert.equal(writes[1].body.confirm, true);
});

test("coordinate guesses require location selection and a separate submit confirmation", async () => {
  await mount(); await selectPhotoWithKeyboard("ArrowRight");
  assert.equal(writes.length, 0); assert.equal(buttons("Submit guess").length, 0);
  await click("Confirm this object"); assert.match(bodyText(), /Guess this object/); assert.equal(writes.length, 0);
  await click("Choose again"); assert.equal(buttons("Submit guess").length, 0);
  await click("Confirm this object");
  replies.push(() => { snapshot = fixture({ revision: 5, activeRound: round({ status: "awaitingFollowUp", messages: [
    ...round().messages, { id: "g1", type: "guess", senderId: "u1", x: .52, y: .5, createdAt: now },
    { id: "wrong1", type: "incorrectResult", text: "Not quite.", createdAt: now },
  ] }) }); return Response.json(snapshot); });
  await click("Submit guess");
  assert.equal(writes.length, 1); assert.equal(writes[0].body.x, .52); assert.equal(writes[0].body.y, .5);
  assert.equal("objectKey" in writes[0].body, false); assert.equal("target" in writes[0].body, false);
  await waitFor(() => assert.match(bodyText(), /friend can send another clue/));
  assert.ok(dom.window.document.querySelector('.friend-photo__selection[style*="52%"]'), "the receiver retains their wrong guess location");
});

test("a lost command response survives refresh and replays the original key, coordinates and revision", async () => {
  let view = await mount(); await selectPhotoWithKeyboard(); await click("Confirm this object");
  replies.push(() => { throw new TypeError("Connection lost"); });
  await click("Submit guess"); await waitFor(() => assert.ok(buttons("Retry last action")[0]));
  const original = structuredClone(writes[0]); assert.equal(original.body.expectedRevision, 4);
  await view.close(); snapshot.revision = 9;
  view = await mount(); await waitFor(() => assert.ok(buttons("Retry last action")[0]));
  assert.equal(buttons("Confirm this object")[0]?.disabled, true);
  replies.push(() => Response.json({ ...snapshot, revision: 10 }));
  await click("Retry last action"); assert.deepEqual(writes[1], original);
  await waitFor(() => assert.equal(buttons("Retry last action").length, 0));
  assert.equal(dom.window.sessionStorage.getItem(chatDraftKey("u1", "chat1", "command")), null);
  await view.close();
});

test("pending commands and unsent clue drafts are isolated between accounts", async () => {
  saveChatDraft(chatDraftKey("u1", "chat1", "command"), prepareChatCommand("rounds/round1/guess", 4, { x: .2, y: .3 }, null));
  saveChatDraft(chatDraftKey("u1", "chat1", "round1:composingClue:clue"), { text: "Es roja.", selected: ["red"], stage: 0 });
  state = { ...defaultState(), user: { ...defaultState().user, id: "u3" }, activeProfile: { ...defaultState().activeProfile, id: "profile3", userId: "u3" } };
  snapshot = fixture({ meId: "u3", activeRound: round({ senderId: "u3", status: "composingClue", messages: [] }) });
  await mount(); await waitFor(() => assert.match(bodyText(), /Build your clue/));
  assert.equal(buttons("Retry last action").length, 0);
  assert.equal(dom.window.document.querySelector<HTMLTextAreaElement>("textarea")?.value, "");
  assert.equal(writes.length, 0);
});

test("an A0 clue grows one fact at a time, restores after refresh and reuses the stored mission cheatsheet", async () => {
  snapshot.activeRound = round({ senderId: "u1", status: "composingClue", messages: [] });
  let view = await mount();
  await clickElement(dom.window.document.querySelector('.friend-clue-option__choice'));
  assert.equal(dom.window.document.querySelector<HTMLTextAreaElement>("textarea")?.value, "Es roja.");
  assert.equal(dom.window.document.querySelector<HTMLTextAreaElement>("textarea")?.readOnly, true);
  assert.equal(writes.length, 0);
  await click("Add another detail"); await clickElement(dom.window.document.querySelector('.friend-clue-option__choice'));
  assert.equal(dom.window.document.querySelector<HTMLTextAreaElement>("textarea")?.value, "Es roja. Está debajo de la mesa.");
  await view.close(); view = await mount();
  await waitFor(() => assert.equal(dom.window.document.querySelector<HTMLTextAreaElement>("textarea")?.value, "Es roja. Está debajo de la mesa."));
  await clickElement(dom.window.document.querySelector('button[aria-label="Open cheatsheet"]'));
  await waitFor(() => assert.match(bodyText(), /Stored adjective guide/));
  assert.ok(reads.some(path => path.includes("/learning-resources/cheatsheets/M03?") && path.includes("contentVersion=1")));
  assert.equal(writes.length, 0);
  await view.close();
});

test("suggested clues require explicit application, review and send; successful sends clear the unsent draft", async () => {
  snapshot.activeRound = round({ senderId: "u1", status: "composingClue", messages: [] });
  await mount(); replies.push(() => Response.json({ text: "Es pequeña y roja." }));
  await click("Suggest a clue"); assert.equal(dom.window.document.querySelector<HTMLTextAreaElement>("textarea")?.value, "");
  assert.equal(writes.filter(item => item.path.endsWith("/clue")).length, 0);
  await click("Use this suggestion"); assert.equal(dom.window.document.querySelector<HTMLTextAreaElement>("textarea")?.value, "Es pequeña y roja.");
  await click("Review clue"); assert.equal(writes.filter(item => item.path.endsWith("/clue")).length, 0);
  replies.push(() => { snapshot.activeRound!.status = "awaitingGuess"; snapshot.revision = 5; return Response.json(snapshot); });
  await click("Send clue");
  assert.equal(writes.at(-1)?.body.text, "Es pequeña y roja.");
  assert.equal(readChatDraft(chatDraftKey("u1", "chat1", "round1:composingClue:clue"), null), null);
});

test("A0 can combine multiple true adjective facts and remove one without losing the others", async () => {
  const options = round().clueOptions;
  snapshot.activeRound = round({ senderId: "u1", status: "composingClue", messages: [], clueOptions: [options[0],
    { ...options[0], id: "small", text: "Es pequeña.", translation: "It is small." }, options[1]] });
  await mount();
  const choices = [...dom.window.document.querySelectorAll('.friend-clue-option__choice')];
  await clickElement(choices[0]); await clickElement(choices[1]);
  assert.equal(dom.window.document.querySelector<HTMLTextAreaElement>("textarea")?.value, "Es roja. Es pequeña.");
  await clickElement(choices[0]);
  assert.equal(dom.window.document.querySelector<HTMLTextAreaElement>("textarea")?.value, "Es pequeña.");
  assert.equal(writes.length, 0);
});

test("A1 phrase tiles reorder while retaining the learner's additional text", async () => {
  snapshot.viewerLevel = "A1";
  snapshot.activeRound = round({ senderId: "u1", status: "composingClue", messages: [] });
  await mount();
  const choices = [...dom.window.document.querySelectorAll('.friend-clue-option__choice')];
  await clickElement(choices[0]); await clickElement(choices[1]);
  const input = dom.window.document.querySelector<HTMLTextAreaElement>("textarea")!;
  await setValue(input, `${input.value} Mira bien.`);
  await clickElement(dom.window.document.querySelector('button[aria-label="Move detail 2 earlier"]'));
  assert.equal(input.value, "Está debajo de la mesa. Es roja. Mira bien.");
  assert.equal(writes.length, 0);
});

test("speech stops for clue review and late recognition cannot change the reviewed text", async () => {
  let recognition: { onresult: ((event: unknown) => void) | null; onend: (() => void) | null; stops: number } | null = null;
  class FakeRecognition {
    lang = ""; continuous = false; interimResults = false; stops = 0;
    onresult: ((event: unknown) => void) | null = null; onerror: (() => void) | null = null; onend: (() => void) | null = null;
    constructor() { recognition = this; }
    start() {}
    stop() { this.stops += 1; this.onend?.(); }
  }
  const browser = dom.window as unknown as { SpeechRecognition?: typeof FakeRecognition };
  browser.SpeechRecognition = FakeRecognition;
  state.user.microphoneEnabled = true; snapshot.viewerLevel = "A2";
  snapshot.activeRound = round({ senderId: "u1", status: "composingClue", messages: [] });
  try {
    const view = await mount();
    const input = dom.window.document.querySelector<HTMLTextAreaElement>("textarea")!;
    await setValue(input, "Es roja."); await click("Speak your clue");
    const active = recognition!; assert.ok(active);
    await click("Review clue"); assert.ok(active.stops > 0);
    await surface.act(async () => active.onresult?.({ results: [{ isFinal: true, 0: { transcript: "late words" } }] }));
    assert.equal(input.value, "Es roja.");
    await view.close();
    const previous = active.stops;
    assert.ok(previous > 0);
  } finally { delete browser.SpeechRecognition; }
});

test("the friend's selected pasta avatar is rendered without publishing their proficiency", async () => {
  snapshot.partner!.avatar = "fusilli";
  await mount();
  assert.equal(dom.window.document.querySelector<HTMLImageElement>(".friend-avatar img")?.getAttribute("src"), "/pasta-assets/fusilli.png");
  assert.doesNotMatch(bodyText(), /A0|A1|A2|proficiency/i);
});

test("Linguini help is requested privately without a shared revision, clue text or help message in the chat cache", async () => {
  const view = await mount(); await click("Linguini help · just for you");
  await waitFor(() => assert.match(bodyText(), /Your friend can’t see which help you use/));
  assert.deepEqual(writes[0], { path: `${apiPrefix}/chat1/rounds/round1/help`, body: {} });
  const cached = view.client.getQueryData(["friend-chats", "u1", "profile1", "chat1"]) as ChatSnapshot;
  assert.equal(cached.revision, 4); assert.equal(cached.activeRound?.messages.length, 1);
  assert.equal(JSON.stringify(cached).includes("Look below the large table"), false);
  const events = dom.window._uxa?.filter(item => item[0] === "trackCustomEvent") ?? [];
  assert.ok(events.some(item => item[1] === "ispy_friend_private_help_opened"));
  assert.equal(JSON.stringify(events).includes("roja"), false);
});

test("completed history remains visible and either participant can start the next photo", async () => {
  for (const lastSender of ["u1", "u2"]) {
    snapshot = fixture({ activeRound: null, rounds: [round({ senderId: lastSender, status: "completed", completedAt: now,
      messages: [...round().messages, { id: "found", type: "correctResult", text: "Leo found it!", createdAt: now }] })] });
    const view = await mount();
    assert.match(bodyText(), /Leo found it/); assert.match(bodyText(), /la taza/);
    assert.equal(buttons("Start another I-Spy")[0]?.disabled, false);
    await click("Start another I-Spy"); assert.match(bodyText(), /Choose one photo/);
    assert.ok(dom.window.document.querySelector('input[type="file"]'));
    await view.close();
  }
});

test("reports, leaving and blocking require a separate confirmation and use dedicated commands", async () => {
  for (const action of ["report", "leave", "block"] as const) {
    writes.length = 0; snapshot = fixture({ activeRound: null });
    const view = await mount();
    const label = action === "report" ? "Report user" : action === "leave" ? "Leave conversation" : "Block user";
    await click(label); assert.equal(writes.length, 0);
    if (action === "report") {
      const input = dom.window.document.querySelector<HTMLTextAreaElement>("textarea")!;
      await setValue(input, "Unwanted messages"); await click("Submit report");
    } else await click(label, 1);
    assert.equal(writes[0].path, `${apiPrefix}/chat1/${action}`);
    assert.equal(typeof writes[0].body.commandId, "string"); assert.equal(writes[0].body.expectedRevision, 4);
    if (action === "report") assert.equal(writes[0].body.reason, "Unwanted messages");
    const events = dom.window._uxa?.filter(item => item[0] === "trackCustomEvent") ?? [];
    assert.equal(JSON.stringify(events).includes("Unwanted messages"), false);
    await view.close();
  }
});

test("revoked or cancelled history never fetches an unavailable protected photo", async () => {
  snapshot = fixture({ activeRound: null, rounds: [round({ status: "cancelled", imageUrl: null as unknown as string, messages: [] })] });
  await mount(); await new Promise(resolve => setTimeout(resolve, 40));
  assert.equal(reads.some(path => path.includes("/rounds/round1/image")), false);
  assert.doesNotMatch(bodyText(), /couldn’t load this photo/);
});

test("draft removal is scoped to one account, chat and round", () => {
  const selected = chatDraftKey("u1", "chat1", "round1:guess");
  const otherRound = chatDraftKey("u1", "chat1", "round2:guess");
  const otherOwner = chatDraftKey("u2", "chat1", "round1:guess");
  for (const key of [selected, otherRound, otherOwner]) saveChatDraft(key, { x: .5, y: .5 });
  clearChatDrafts("u1", "chat1", "round1");
  assert.equal(readChatDraft(selected, null), null); assert.ok(readChatDraft(otherRound, null)); assert.ok(readChatDraft(otherOwner, null));
});

test("friend invitation fragments are consumed before analytics scripts without disturbing password recovery fragments", () => {
  const html = readFileSync(join(here, "../index.html"), "utf8");
  const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)];
  const startup = scripts.find(script => script[1].includes("linguini-friend-chat-invite"));
  assert.ok(startup, "the invitation boot script must run before any analytics tag");
  assert.ok(startup.index! < html.indexOf('src="https://t.contentsquare.net/'));
  const invite = new JSDOM("<!doctype html>", { url: "https://www.learnwithlinguini.com/ispy/friends#invite=" + "a".repeat(43), runScripts: "outside-only" });
  invite.window.eval(startup[1]);
  assert.equal(invite.window.location.hash, ""); assert.equal(invite.window.location.pathname, "/ispy/friends");
  assert.equal(invite.window.sessionStorage.getItem(friendInviteStorageKey), "a".repeat(43));
  const invalid = new JSDOM("<!doctype html>", { url: "https://www.learnwithlinguini.com/ispy/friends#invite=invalid", runScripts: "outside-only" });
  invalid.window.eval(startup[1]);
  assert.equal(invalid.window.location.hash, "", "invalid invitations are also removed before analytics reads the URL");
  const recovery = new JSDOM("<!doctype html>", { url: "https://www.learnwithlinguini.com/reset-password#access_token=private&type=recovery", runScripts: "outside-only" });
  recovery.window.eval(startup[1]); assert.equal(recovery.window.location.hash, "#access_token=private&type=recovery");
  invite.window.close(); invalid.window.close(); recovery.window.close();
});

import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { RoomSnapshot } from "../src/lib/rooms.ts";

process.env.VITE_API_BASE_URL = "http://api.test";
const { canStartRoom, prepareRoomCommand, roomReviewPayload, sanitizeRoomSnapshot } = await import("../src/lib/rooms.ts");

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://app.test/rooms/r1", pretendToBeVisual: true });
const globals = globalThis as Record<string, unknown>;
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (globals[key] !== undefined) continue;
  try { globals[key] = (dom.window as unknown as Record<string, unknown>)[key]; } catch { /* read-only Node globals */ }
}
Object.defineProperty(globalThis, "window", { value: dom.window, configurable: true });
Object.defineProperty(globalThis, "document", { value: dom.window.document, configurable: true });
globals.IS_REACT_ACT_ENVIRONMENT = true;
Object.defineProperty(dom.window, "innerWidth", { value: 360 });
// React's bundled browser scheduler uses Node's MessageChannel in this DOM harness.
// Close channels owned by this test after all act queues settle.
const NativeMessageChannel = globalThis.MessageChannel;
const messageChannels: MessageChannel[] = [];
globals.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); messageChannels.push(this); }
};

function fixture(role: "sender" | "guesser" = "guesser", phase: "compose" | "guess" | "reveal" = "guess"): RoomSnapshot {
  return { id: "r1", status: "playing", revision: 7, meId: "u1", expiresAt: "2099-01-01T00:00:00Z",
    sourceLanguageCode: "en", targetLanguageCode: "es", proficiencyLevel: "A1", successfulRounds: 0, roundCount: 2,
    members: [{ userId: "u1", displayName: "Learner", seat: 0, ready: true, acknowledged: false },
      { userId: "u2", displayName: "Friend", seat: 1, ready: true, acknowledged: false }],
    photos: [{ id: "p1", ownerUserId: "u1", mediaAssetId: "a1", status: "ready", imageUrl: "/api/v1/rooms/r1/photos/p1/image?width=640" },
      { id: "p2", ownerUserId: "u2", mediaAssetId: "a2", status: "ready", imageUrl: "/api/v1/rooms/r1/photos/p2/image?width=640" }],
    currentTurn: { id: "t1", index: 0, role, phase, photoId: "p1", imageUrl: "/api/v1/rooms/r1/photos/p1/image?width=640",
      objects: [{ key: "k1", word: "mesa", translation: "table", x: 30, y: 40, marker: 1 },
        { key: "k2", word: "taza", translation: "cup", x: 60, y: 45, marker: 2 }],
      targetObjectKey: "k1", clueOptions: [{ id: "c1", text: "SECRET SENDER PHRASE" }],
      clue: phase === "compose" ? null : "Es roja.", guessCount: 0, guessedObjectKeys: [],
      result: phase === "reveal" ? { isCorrect: false, targetObjectKey: "k1", message: "Look at the red table." } : null },
    contributions: [{ userId: "u1", cluesSent: 0, guessesMade: 0, correctGuesses: 0, basilEarned: 0, xpEarned: 0 },
      { userId: "u2", cluesSent: 1, guessesMade: 0, correctGuesses: 0, basilEarned: 1, xpEarned: 10 }],
  };
}

test("guesser snapshots discard sender-only answers, premature results and private photo review", () => {
  const raw = fixture();
  raw.currentTurn!.result = { isCorrect: true, targetObjectKey: "k1", message: "Premature answer" };
  raw.photos[1].review = { objects: [], relations: [], title: "Private owner review" };
  raw.photos[1].status = "analyzing";
  raw.hostUserId = "u2";
  raw.inviteCode = "private-host-invite";
  const safe = sanitizeRoomSnapshot(raw);
  assert.equal("targetObjectKey" in safe.currentTurn!, false);
  assert.equal("clueOptions" in safe.currentTurn!, false);
  assert.equal(safe.currentTurn!.result, null);
  assert.equal("review" in safe.photos[1], false);
  assert.equal(safe.photos[1].imageUrl, null);
  assert.equal(safe.inviteCode, null);
  assert.equal(raw.currentTurn!.targetObjectKey, "k1", "sanitizing must not mutate the response fixture");
});

test("starting requires two ready participants and two to four ready photos", () => {
  const room = { ...fixture(), status: "lobby" as const, currentTurn: null };
  assert.equal(canStartRoom(room), true);
  assert.equal(canStartRoom({ ...room, photos: room.photos.slice(0, 1) }), false);
  assert.equal(canStartRoom({ ...room, members: room.members.slice(0, 1) }), false);
  assert.equal(canStartRoom({ ...room, photos: [{ ...room.photos[0], status: "awaitingReview" }, room.photos[1]] }), false);
});

test("an unknown command outcome retains its key, revision and original payload", () => {
  const original = prepareRoomCommand("turns/t1/guess", 7, { objectKey: "k2" }, null, () => "stable-id");
  const replay = prepareRoomCommand("turns/t1/guess", 9, { objectKey: "k1" }, original, () => "new-id");
  assert.equal(replay, original);
  assert.deepEqual(replay.body, { commandId: "stable-id", expectedRevision: 7, objectKey: "k2" });
});

test("review payload omits analysis provenance that the strict review API rejects", () => {
  const raw = { title: "Photo", moderationPassed: true, ownerId: "private", version: 1,
    objects: [{ key: "k1", label: "table", x: 20, y: 40, color: "red", confidence: 0.9 }], relations: [] };
  assert.deepEqual(roomReviewPayload(raw), { title: "Photo", objects: [{ key: "k1", label: "table", x: 20, y: 40, color: "red" }], relations: [] });
});

const here = dirname(fileURLToPath(import.meta.url));
async function bundle() {
  const folder = mkdtempSync(join(tmpdir(), "linguini-room-test-"));
  const entry = join(here, `.rooms-entry-${crypto.randomUUID()}.ts`);
  writeFileSync(entry, [
    'export { createElement as h, act } from "react";', 'export { createRoot } from "react-dom/client";',
    'export { MemoryRouter, Route, Routes } from "react-router-dom";',
    'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
    'export { AppStateContext } from "../src/state/context";',
    'export { Room } from "../src/pages/Room";', 'export { Rooms } from "../src/pages/Rooms";',
    'export { GameResources } from "../src/components/GameResources";',
    'export { default as App } from "../src/App";',
    'export { AuthProvider } from "../src/state/Auth";',
  ].join("\n"));
  try {
    const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
      plugins: [{ name: "test-environment", transform: code => code
        .replaceAll("import.meta.env?.VITE_API_BASE_URL", '"http://api.test"')
        .replaceAll("import.meta.env.DEV", "true") },
      { name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null, load: id => id === "\0empty-css" ? "export default {};" : null }],
    });
    const { output } = await bundler.generate({ format: "esm" });
    await bundler.close();
    const outputPath = join(folder, "bundle.mjs");
    writeFileSync(outputPath, output[0].code);
    return await import(pathToFileURL(outputPath).href);
  } finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
}
const surface = await bundle();
const mountedCleanups = new Set<() => Promise<void>>();
function registerCleanup(dispose: () => Promise<void>) {
  let closed = false;
  const close = async () => {
    if (closed) return;
    closed = true;
    try { await dispose(); } finally { mountedCleanups.delete(close); }
  };
  mountedCleanups.add(close);
  return close;
}
test.afterEach(async () => {
  for (const close of [...mountedCleanups]) await close();
});
test.after(async () => {
  for (const close of [...mountedCleanups]) await close();
  dom.window.close();
  for (const channel of messageChannels) { channel.port1.close(); channel.port2.close(); }
  globals.MessageChannel = NativeMessageChannel;
});
let snapshot = fixture();
let activeSnapshot: RoomSnapshot | null = null;
const writes: { path: string; body: Record<string, unknown> }[] = [];
const readPaths: string[] = [];
const replies: (() => Response | Promise<Response>)[] = [];
let resourceSnapshot = { sauce: { remaining: 9, capacity: 10, refillsAt: "2099-01-01T00:00:00Z" }, basilLeaves: 2,
  appearance: "default", ownedAppearances: ["default"] };
globals.fetch = async (input: unknown, init?: RequestInit) => {
  const path = String(input).replace("http://api.test", "");
  if (init?.method === "POST") { writes.push({ path, body: JSON.parse(String(init.body)) }); return replies.shift()?.() ?? Response.json(snapshot); }
  readPaths.push(path);
  if (path.endsWith("/image?width=640")) return new Response(new Blob(["photo"], { type: "image/png" }));
  if (path === "/api/v1/me/game-resources") return Response.json(resourceSnapshot);
  if (path === "/api/v1/me") return Response.json(state.user);
  if (path === "/api/v1/me/language-profiles") return Response.json([{ ...state.activeProfile, isActive: true }]);
  if (path === "/api/v1/me/progress") return Response.json({ xp: 0 });
  if (path === "/api/v1/ispy/games/active") return Response.json(null);
  if (path === "/api/v1/rooms/active") return Response.json(activeSnapshot);
  if (path === "/api/v1/rooms/r1") return Response.json(snapshot);
  return new Response("not found", { status: 404 });
};
const state = { user: { id: "u1", cameraEnabled: true }, activeProfile: { id: "profile1", userId: "u1", targetLanguageCode: "es", sourceLanguageCode: "en", proficiencyLevel: "A1" } };
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
const text = () => dom.window.document.body.textContent ?? "";
const button = (label: string) => [...dom.window.document.querySelectorAll("button")].find(item => item.textContent?.trim() === label);
async function waitFor(assertion: () => void, source = surface, timeoutMs = 2_500) {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown;
  do {
    await source.act(async () => { await sleep(10); });
    try { assertion(); return; } catch (error) { lastError = error; }
  } while (Date.now() < deadline);
  throw lastError;
}
async function click(label: string) {
  await surface.act(async () => {
    const element = button(label);
    assert.ok(element, `expected button ${label}`);
    assert.equal(element.disabled, false, `${label} should be usable`);
    element.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  });
  await waitFor(() => assert.doesNotMatch(text(), /Saving your action…|Saving your jar…|Creating your room…|Joining your friend…/));
}
async function mount(which: "Room" | "Rooms" = "Room", source = surface) {
  const container = dom.window.document.createElement("div");
  dom.window.document.body.replaceChildren(container);
  const root = source.createRoot(container);
  const client = new source.QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  const close = registerCleanup(async () => {
    try { await source.act(async () => root.unmount()); } finally { client.clear(); }
  });
  await source.act(async () => root.render(source.h(source.QueryClientProvider, { client },
    source.h(source.AppStateContext.Provider, { value: state }, source.h(source.MemoryRouter, { initialEntries: [which === "Room" ? "/rooms/r1" : "/rooms"] },
      source.h(source.Routes, null,
        source.h(source.Route, { path: "/rooms/:roomId", element: source.h(source.Room) }),
        source.h(source.Route, { path: "/rooms", element: source.h(source.Rooms) }),
        source.h(source.Route, { path: "/home", element: source.h("p", null, "Home destination") }),
      ))))));
  await waitFor(() => assert.match(text(), which === "Room" ? /I Spy together|Home destination/ : /I Spy with a friend|Home destination/), source);
  return { client, close };
}

async function mountApp(path: string) {
  const container = dom.window.document.createElement("div");
  dom.window.document.body.replaceChildren(container);
  const root = surface.createRoot(container);
  const client = new surface.QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  const close = registerCleanup(async () => {
    try { await surface.act(async () => root.unmount()); } finally { client.clear(); }
  });
  await surface.act(async () => root.render(surface.h(surface.QueryClientProvider, { client },
    surface.h(surface.AuthProvider, null, surface.h(surface.MemoryRouter, { initialEntries: [path] }, surface.h(surface.App))))));
  return { client, close };
}

test("a guesser sees separate numbered touch controls on a narrow screen and no private target clue", async context => {
  snapshot = fixture();
  const revoked: string[] = [];
  const revoke = URL.revokeObjectURL;
  context.after(() => { URL.revokeObjectURL = revoke; });
  URL.revokeObjectURL = url => { revoked.push(url); revoke(url); };
  const view = await mount();
  assert.equal(button("SECRET SENDER PHRASE"), undefined);
  assert.equal(button("Send clue"), undefined);
  assert.ok(dom.window.document.querySelector('.rooms-choices--numbers [aria-pressed="false"]'));
  assert.equal(dom.window.document.querySelectorAll(".rooms-choices--numbers button").length, 2);
  assert.equal(dom.window.document.querySelector<HTMLDetailsElement>(".rooms-word-bank")?.open, false);
  const cached = view.client.getQueryData(["rooms", "u1", "profile1", "r1"]) as RoomSnapshot;
  assert.equal("targetObjectKey" in cached.currentTurn!, false);
  await waitFor(() => assert.ok(dom.window.document.querySelector<HTMLImageElement>(".rooms-photo img")?.src.startsWith("blob:")));
  const imageUrl = dom.window.document.querySelector<HTMLImageElement>(".rooms-photo img")?.src;
  assert.ok(imageUrl?.startsWith("blob:"), "protected photos render authenticated bytes, never a raw API URL");
  await view.close();
  assert.ok(revoked.includes(imageUrl));
  URL.revokeObjectURL = revoke;
});

test("a returning host recovers the invitation from an owner-authorized lobby snapshot", async () => {
  snapshot = { ...fixture(), status: "lobby", currentTurn: null, hostUserId: "u1", inviteCode: "x".repeat(32) };
  snapshot.members = snapshot.members.slice(0, 1);
  const view = await mount();
  assert.ok([...dom.window.document.querySelectorAll<HTMLInputElement>("input[readonly]")].some(input => input.value === "x".repeat(32)));
  await view.close();
});

test("a peer sees room progress after the host starts, without needing a local mutation", async context => {
  writes.length = 0;
  readPaths.length = 0;
  snapshot = { ...fixture(), status: "lobby", currentTurn: null, hostUserId: "u2" };
  const view = await mount();
  context.after(() => view.close());
  view.client.setQueryDefaults(["progress", "profile1"], { gcTime: Infinity });
  view.client.setQueryData(["progress", "profile1"], { xp: 0 });
  snapshot = { ...fixture(), revision: 8, hostUserId: "u2" };
  await surface.act(async () => {
    await view.client.invalidateQueries({ queryKey: ["rooms", "u1", "profile1", "r1"] });
  });
  await waitFor(() => {
    assert.equal(view.client.getQueryState(["progress", "profile1"])?.isInvalidated, true);
    assert.equal(view.client.isFetching(), 0);
  });
  assert.equal(writes.length, 0);
  assert.equal(view.client.getQueryState(["progress", "profile1"])?.isInvalidated, true);
  snapshot = { ...snapshot, revision: 9 };
  await surface.act(async () => {
    await view.client.invalidateQueries({ queryKey: ["rooms", "u1", "profile1", "r1"] });
  });
  await waitFor(() => {
    assert.equal((view.client.getQueryData(["rooms", "u1", "profile1", "r1"]) as RoomSnapshot).revision, 9);
    assert.equal(view.client.isFetching(), 0);
  });
  assert.equal(readPaths.filter(path => path === "/api/v1/me/game-resources").length, 0,
    "the room no longer fetches removed Sauce resources");
  view.client.setQueryData(["progress", "profile1"], { xp: 0 });
  snapshot = { ...snapshot, contributions: snapshot.contributions.map(item => item.userId === "u1"
    ? { ...item, basilEarned: 1, xpEarned: 10 } : item) };
  await surface.act(async () => {
    await view.client.invalidateQueries({ queryKey: ["rooms", "u1", "profile1", "r1"] });
  });
  await waitFor(() => {
    assert.equal(view.client.getQueryState(["progress", "profile1"])?.isInvalidated, true);
    assert.equal(view.client.isFetching(), 0);
  });
  await view.close();
});

test("a lost guess response retries the same key and revision without optimistic credit", async () => {
  writes.length = 0;
  snapshot = fixture();
  const view = await mount();
  await click("Object 2");
  replies.push(() => Response.json({ detail: { message: "Temporarily unavailable" } }, { status: 500 }));
  await click("Check my guess");
  assert.match(text(), /Temporarily unavailable/);
  assert.equal(button("Check my guess")?.disabled, true);
  assert.match(text(), /0 found together/);
  const resolved = fixture("guesser", "reveal");
  resolved.revision = 9;
  replies.push(() => Response.json(resolved));
  await click("Retry action");
  assert.deepEqual(writes[0].body, writes[1].body);
  assert.equal(writes[0].body.expectedRevision, 7);
  assert.equal(writes[0].body.objectKey, "k2");
  assert.match(text(), /Marker 1: mesa/);
  assert.ok(button("Next photo"));
  assert.equal(button("Check my guess"), undefined);
  await view.close();
});

test("a rejected stale command refreshes the snapshot and permits a new revision", async () => {
  writes.length = 0;
  snapshot = fixture();
  const view = await mount();
  await click("Object 2");
  snapshot = { ...fixture(), revision: 8 };
  replies.push(() => Response.json({ detail: { code: "room_stale_revision", message: "The room changed. Try again." } }, { status: 409 }));
  await click("Check my guess");
  await waitFor(() => assert.ok(button("Retry with updated room")));
  replies.push(() => Response.json({ ...fixture("guesser", "reveal"), revision: 9 }));
  await click("Retry with updated room");
  assert.notEqual(writes[0].body.commandId, writes[1].body.commandId);
  assert.equal(writes[1].body.expectedRevision, 8);
  await view.close();
});

test("refresh restores the retry and reveal phases rather than offering a new clue", async () => {
  snapshot = fixture();
  snapshot.currentTurn!.guessCount = 1;
  snapshot.currentTurn!.guessedObjectKeys = ["k1"];
  let view = await mount();
  assert.match(text(), /Try one more object/);
  assert.equal([...dom.window.document.querySelectorAll<HTMLButtonElement>(".rooms-choices--numbers button")][0].disabled, true);
  assert.equal(button("Send clue"), undefined);
  await view.close();
  snapshot = fixture("guesser", "reveal");
  snapshot.members[0].acknowledged = true;
  view = await mount();
  assert.match(text(), /Marker 1: mesa/);
  assert.equal(button("Waiting for your friend…")?.disabled, true);
  assert.equal(button("Check my guess"), undefined);
  await view.close();
});

test("owners confirm only editable facts and peers do not fetch unmoderated thumbnails", async () => {
  writes.length = 0;
  readPaths.length = 0;
  snapshot = { ...fixture(), status: "lobby", currentTurn: null };
  snapshot.members.forEach(member => { member.ready = false; });
  snapshot.photos[0].status = "awaitingReview";
  snapshot.photos[0].review = { title: "My table", objects: [
    { key: "k1", label: "table", x: 30, y: 40, color: "red" }, { key: "k2", label: "cup", x: 60, y: 45, color: null }], relations: [],
    ...{ moderationPassed: true, version: 1, ownerId: "private" } };
  snapshot.photos[1].status = "analyzing";
  const view = await mount();
  assert.equal(readPaths.some(path => path.includes("photos/p2/image")), false);
  assert.match(text(), /Photos you add are shared with the person in this room/);
  await click("Confirm photo facts");
  const review = writes[0].body.review as Record<string, unknown>;
  assert.deepEqual(Object.keys(review).sort(), ["objects", "relations", "title"]);
  assert.equal(review.title, "My table");
  await view.close();
});

test("room entry retries creation with the same command identity", async () => {
  writes.length = 0;
  activeSnapshot = null;
  const view = await mount("Rooms");
  replies.push(() => Response.json({ detail: { message: "Create reply interrupted" } }, { status: 500 }));
  await click("Create a room");
  replies.push(() => Response.json({ room: { ...fixture(), status: "lobby", currentTurn: null }, inviteCode: "a".repeat(32) }));
  await click("Retry request");
  assert.equal(writes[0].body.commandId, writes[1].body.commandId);
  assert.equal(writes[0].body.languageProfileId, "profile1");
  await view.close();
});

test("Play offers a working friend lobby without Sauce resources", async () => {
  activeSnapshot = null;
  readPaths.length = 0;
  const view = await mountApp("/ispy");
  await waitFor(() => assert.ok(button("Play with friends")));
  assert.equal(dom.window.document.querySelectorAll('nav[aria-label="Main"] a').length, 5);
  assert.doesNotMatch(text(), /Coming soon/);
  await click("Play with friends");
  await waitFor(() => assert.ok(button("Create a room")));
  assert.doesNotMatch(text(), /Sauce/);
  assert.ok(readPaths.includes("/api/v1/rooms/active"));
  assert.ok(!readPaths.includes("/api/v1/me/game-resources"));
  assert.equal(dom.window.document.querySelector('nav[aria-label="Main"] a[aria-current="page"]')?.getAttribute("href"), "/ispy");
  assert.ok(dom.window.document.querySelector('button[aria-label="Go back"]'), "the friend lobby uses the shared back control");
  await view.close();
});

test("existing invitation links preserve their code and enter the friend room", async () => {
  activeSnapshot = null;
  writes.length = 0;
  snapshot = { ...fixture(), status: "lobby", currentTurn: null, photos: [] };
  const code = "private invite code";
  const view = await mountApp(`/rooms?code=${encodeURIComponent(code)}`);
  await waitFor(() => assert.ok(button("Join room") && !button("Join room")!.disabled));
  const input = dom.window.document.querySelector<HTMLInputElement>('input[placeholder="Paste your friend’s code"]');
  assert.equal(input?.value, code);
  assert.equal(dom.window.document.querySelector('nav[aria-label="Main"] a[aria-current="page"]')?.getAttribute("href"), "/ispy");
  replies.push(() => Response.json({ room: snapshot }));
  await click("Join room");
  await waitFor(() => assert.match(text(), /I Spy together/));
  assert.equal(writes[0].path, "/api/v1/rooms/join");
  assert.equal(writes[0].body.inviteCode, code);
  assert.equal(writes[0].body.languageProfileId, "profile1");
  await view.close();
});

test("the accent shop keeps the old balance until accepted and safely retries a lost purchase reply", async () => {
  writes.length = 0;
  resourceSnapshot = { ...resourceSnapshot, basilLeaves: 42 };
  const container = dom.window.document.createElement("div");
  dom.window.document.body.replaceChildren(container);
  const root = surface.createRoot(container);
  const client = new surface.QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const close = registerCleanup(async () => {
    try { await surface.act(async () => root.unmount()); } finally { client.clear(); }
  });
  await surface.act(async () => root.render(surface.h(surface.QueryClientProvider, { client },
    surface.h(surface.AppStateContext.Provider, { value: state }, surface.h(surface.GameResources, { shop: true })))));
  await waitFor(() => assert.ok(button("Get accent")));
  replies.push(() => Response.json({ detail: { message: "Purchase reply interrupted" } }, { status: 500 }));
  await click("Get accent");
  assert.match(text(), /42 Basil available/);
  replies.push(() => Response.json({ ...resourceSnapshot, basilLeaves: 22, appearance: "herb", ownedAppearances: ["default", "herb"] }));
  await click("Retry purchase");
  assert.deepEqual(writes[0].body, writes[1].body);
  assert.deepEqual(Object.keys(writes[1].body).sort(), ["appearance", "commandId"]);
  assert.match(text(), /22 Basil available/);
  assert.equal(dom.window.document.querySelectorAll(".game-resources--herb button:disabled").length, 1);
  await close();
});

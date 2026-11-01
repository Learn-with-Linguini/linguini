import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import type { ISpyPhoto, PracticeDetail } from "../src/lib/api.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://app.test/home", pretendToBeVisual: true });
for (const key of ["window", "document", "HTMLElement"] as const) Object.defineProperty(globalThis, key, { value: key === "window" ? dom.window : dom.window[key], configurable: true });
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
const NativeMessageChannel = globalThis.MessageChannel;
const channels: MessageChannel[] = [];
globalThis.MessageChannel = class extends NativeMessageChannel { constructor() { super(); channels.push(this); } };
const here = dirname(fileURLToPath(import.meta.url));
const directory = mkdtempSync(join(tmpdir(), "home-quick-play-"));
const entry = join(here, `.home-quick-play-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";', 'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter, useLocation } from "react-router-dom";', 'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
  'export { HomeQuickPlay } from "../src/components/HomeQuickPlay";', 'export { quickPlayKeys } from "../src/lib/homeQuickPlay";',
].join("\n"));
let surface;
try {
  const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{ name: "api-origin", transform: code => code.replaceAll("import.meta.env?.VITE_API_BASE_URL", '"http://api.test"') },
      { name: "css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null, load: id => id === "\0empty-css" ? "export default {};" : null }],
  });
  try { const { output } = await bundler.generate({ format: "esm" }); const path = join(directory, "bundle.mjs"); writeFileSync(path, output[0].code); surface = await import(pathToFileURL(path).href); }
  finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); rmSync(directory, { recursive: true, force: true }); }

const photo = (id: string, playable = true, source: string = "userUpload"): ISpyPhoto => ({ mediaAsset: { id, source, createdAt: "2026-10-30T12:00:00Z" }, title: `My ${id}`, playable,
  confirmedAt: playable ? "2026-10-30T12:01:00Z" : null }) as ISpyPhoto;
const game = (id = "game1", assetId = "mine1", describe = false): PracticeDetail => ({ title: "My game", session: {
  id, mode: "ispy", status: "inProgress", sceneMediaAssetId: assetId,
}, tasks: [{ kind: "ispyRound", phase: "ispy", status: describe ? "completed" : "pending", orderIndex: 0 },
  { kind: "reflection", phase: "ispy", status: "pending", orderIndex: 1 }] }) as PracticeDetail;
let pages = new Map<string, { photos: ISpyPhoto[]; nextCursor: string | null }>();
let active: PracticeDetail | null = null;
let activeReply: (() => Response | Promise<Response>) | null = null;
let photosReply: (() => Response | Promise<Response>) | null = null;
const posts: { path: string; body: Record<string, unknown> }[] = [];
const reads: string[] = [];
const replies: (() => Response | Promise<Response>)[] = [];
const originalFetch = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  const url = new URL(String(input));
  if (init?.method === "POST") { posts.push({ path: url.pathname, body: JSON.parse(String(init.body)) }); return replies.shift()?.() ?? Response.json(game()); }
  reads.push(url.pathname + url.search);
  if (url.pathname === "/api/v1/ispy/photos") return photosReply?.() ?? Response.json(pages.get(url.searchParams.get("cursor") ?? "") ?? { photos: [], nextCursor: null });
  if (url.pathname === "/api/v1/ispy/games/active") return activeReply?.() ?? Response.json(active);
  if (url.pathname.startsWith("/api/v1/media/")) return new Response(new Blob(["photo"], { type: "image/webp" }));
  throw new Error(`Unexpected request ${url.pathname}`);
};
function CurrentPath() { return surface.h("output", { "aria-label": "Current route" }, surface.useLocation().pathname); }
const cleanups = new Set<() => Promise<void>>();
async function mount() {
  const container = dom.window.document.createElement("div"); dom.window.document.body.replaceChildren(container);
  const root = surface.createRoot(container);
  const client = new surface.QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  let closed = false;
  const close = async () => { if (closed) return; closed = true; await surface.act(async () => root.unmount()); client.clear(); cleanups.delete(close); };
  cleanups.add(close);
  const render = async (owner = "u1", profileId = "p1") => surface.act(async () => root.render(surface.h(surface.QueryClientProvider, { client },
    surface.h(surface.MemoryRouter, { initialEntries: ["/home"] }, surface.h(surface.HomeQuickPlay, { owner, profileId, key: `${owner}:${profileId}` }), surface.h(CurrentPath)))));
  await render(); return { container, client, close, render };
}
async function waitFor(check: () => void) {
  const deadline = Date.now() + 2500; let failure: unknown;
  do { await surface.act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); }); try { check(); return; } catch (error) { failure = error; } } while (Date.now() < deadline);
  throw failure;
}
const text = () => dom.window.document.body.textContent ?? "";
const primary = () => dom.window.document.querySelector<HTMLButtonElement>(".home-quick-play__open")!;
const button = (label: string) => [...dom.window.document.querySelectorAll<HTMLButtonElement>("button")].find(item => item.textContent?.trim() === label)!;
async function click(element: HTMLButtonElement) { assert.ok(element); assert.equal(element.disabled, false); await surface.act(async () => element.click()); }
const path = () => dom.window.document.querySelector('output[aria-label="Current route"]')?.textContent;
test.beforeEach(() => { pages = new Map([["", { photos: [photo("mine1")], nextCursor: null }]]); active = null; activeReply = null; photosReply = null;
  posts.length = 0; reads.length = 0; replies.length = 0; window._uxa = []; });
test.afterEach(async () => { for (const close of [...cleanups]) await close(); });
test.after(() => { globalThis.fetch = originalFetch; dom.window.close(); for (const channel of channels) { channel.port1.close(); channel.port2.close(); } globalThis.MessageChannel = NativeMessageChannel; });

test("quick play randomly selects a playable personal photo without fetching unnecessary later pages", async () => {
  pages.set("", { photos: [photo("mine1", true, "camera"), photo("unfinished", false), photo("catalog", true, "preloaded"), photo("mine2"), photo("mine1", true, "camera")], nextCursor: "next" });
  pages.set("next", { photos: [photo("older-photo")], nextCursor: null });
  const random = Math.random; Math.random = () => .99;
  try {
    await mount(); await waitFor(() => assert.equal(primary().disabled, false));
    assert.match(text(), /My mine2/); assert.doesNotMatch(text(), /unfinished|catalog|grocery/);
    assert.equal(reads.includes("/api/v1/ispy/photos?cursor=next"), false);
    assert.ok(reads.some(read => read.includes("/media/mine2/image"))); assert.equal(posts.length, 0);
    assert.equal(path(), "/home");
  } finally { Math.random = random; }
});

test("quick play checks a later page only when the earlier page has no playable personal photos", async () => {
  pages.set("", { photos: [photo("unfinished", false), photo("catalog", true, "preloaded")], nextCursor: "next" });
  pages.set("next", { photos: [photo("mine2")], nextCursor: null });
  await mount(); await waitFor(() => assert.equal(primary().disabled, false));
  assert.match(text(), /My mine2/); assert.ok(reads.includes("/api/v1/ispy/photos?cursor=next"));
  assert.equal(posts.length, 0);
});

test("clicking quick play starts the selected photo and follows the returned canonical game step", async () => {
  await mount(); await waitFor(() => assert.equal(primary().disabled, false));
  replies.push(() => Response.json(game("actual-game", "mine1", true)));
  await click(primary()); await waitFor(() => assert.equal(path(), "/ispy/games/actual-game/describe"));
  assert.equal(posts.length, 1); assert.equal(posts[0].path, "/api/v1/ispy/games");
  assert.equal(posts[0].body.languageProfileId, "p1"); assert.equal(posts[0].body.mediaAssetId, "mine1");
  assert.equal(typeof posts[0].body.idempotencyKey, "string");
  assert.ok(window._uxa?.some(event => event[1] === "home_explore_ispy_clicked" && (event[2] as { action: string }).action === "start"));
});

test("an unfinished game resumes instead of creating another game", async () => {
  active = game("unfinished", "existing-photo", true);
  await mount(); await waitFor(() => assert.equal(primary().disabled, false));
  assert.match(text(), /Continue your I-Spy/);
  await click(primary()); await waitFor(() => assert.equal(path(), "/ispy/games/unfinished/describe"));
  assert.equal(posts.length, 0);
});

test("quick play rechecks for a game started since the Home preview loaded", async () => {
  await mount(); await waitFor(() => assert.equal(primary().disabled, false));
  active = game("newly-started");
  await click(primary()); await waitFor(() => assert.equal(path(), "/ispy/games/newly-started/clues"));
  assert.equal(posts.length, 0);
});

test("loading photos disables quick play and never submits a start", async () => {
  let resolve!: (response: Response) => void;
  photosReply = () => new Promise(done => { resolve = done; });
  await mount(); assert.equal(primary().disabled, true); assert.match(text(), /Finding a photo/); assert.equal(posts.length, 0);
  await surface.act(async () => resolve(Response.json({ photos: [photo("mine1")], nextCursor: null })));
  await waitFor(() => assert.equal(primary().disabled, false)); assert.equal(posts.length, 0);
});

test("photos that are not playable show an honest empty state with a photo lesson action", async () => {
  pages.set("", { photos: [photo("unfinished", false), photo("catalog", true, "preloaded")], nextCursor: null });
  await mount(); await waitFor(() => assert.ok(button("Start a photo lesson")));
  assert.equal(primary().disabled, true); assert.equal(posts.length, 0);
  await click(button("Start a photo lesson")); assert.equal(path(), "/practice");
});

test("a failed photo list has an explicit retry that loads the real photo", async () => {
  photosReply = () => Response.json({ detail: { message: "Unavailable" } }, { status: 503 });
  await mount(); await waitFor(() => assert.ok(button("Reload quick play"))); assert.equal(primary().disabled, true);
  photosReply = null; await click(button("Reload quick play")); await waitFor(() => assert.equal(primary().disabled, false));
  assert.match(text(), /My mine1/); assert.equal(posts.length, 0);
});

test("a failed active-game check blocks new starts until the learner retries", async () => {
  activeReply = () => Response.json({ detail: { message: "Unavailable" } }, { status: 503 });
  await mount(); await waitFor(() => assert.ok(button("Reload quick play"))); assert.equal(primary().disabled, true);
  activeReply = null; await click(button("Reload quick play")); await waitFor(() => assert.equal(primary().disabled, false));
  assert.equal(posts.length, 0);
});

test("a lost start response retries the same photo and idempotency key even if the photo list changes", async () => {
  const view = await mount(); await waitFor(() => assert.equal(primary().disabled, false));
  replies.push(() => Response.json({ detail: { message: "Lost response" } }, { status: 503 }));
  await click(primary()); await waitFor(() => assert.ok(button("Retry quick play")));
  const original = posts[0];
  pages.set("", { photos: [photo("different")], nextCursor: null });
  await surface.act(async () => view.client.invalidateQueries({ queryKey: surface.quickPlayKeys.photos("u1", "p1") }));
  assert.match(text(), /My mine1/); assert.doesNotMatch(text(), /My different/);
  replies.push(() => Response.json(game("recovered", "mine1")));
  await click(button("Retry quick play")); await waitFor(() => assert.equal(path(), "/ispy/games/recovered/clues"));
  assert.deepEqual(posts[1], original);
});

test("an old account's delayed start response cannot navigate the new account", async () => {
  let resolve!: (response: Response) => void;
  const view = await mount(); await waitFor(() => assert.equal(primary().disabled, false));
  replies.push(() => new Promise(done => { resolve = done; }));
  await click(primary()); await waitFor(() => assert.equal(posts.length, 1));
  await view.render("u2", "p2"); await waitFor(() => assert.equal(primary().disabled, false));
  await surface.act(async () => resolve(Response.json(game("old-account-game"))));
  assert.equal(path(), "/home");
  assert.equal(view.client.getQueryData(surface.quickPlayKeys.active("u2", "p2")), null);
});

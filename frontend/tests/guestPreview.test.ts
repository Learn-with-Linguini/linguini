import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/login" });
for (const key of ["window", "document", "localStorage", "sessionStorage", "HTMLElement"] as const) {
  Object.defineProperty(globalThis, key, { value: key === "window" ? dom.window : dom.window[key], configurable: true });
}
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
Object.defineProperty(dom.window, "matchMedia", { value: (query: string) => ({ matches: query.includes("prefers-reduced-motion") }) });
dom.window.scrollTo = () => {};
globalThis.requestAnimationFrame = callback => setTimeout(() => callback(0), 0) as unknown as number;
globalThis.cancelAnimationFrame = handle => clearTimeout(handle);
const NativeMessageChannel = globalThis.MessageChannel;
const channels: MessageChannel[] = [];
globalThis.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); channels.push(this); }
};
const originalFetch = globalThis.fetch;
const requests: string[] = [];
globalThis.fetch = async input => { requests.push(String(input)); throw new Error("Guest preview must not make API requests"); };
const events: unknown[][] = [];
(dom.window as unknown as Window).gtag = (...args) => { events.push(args); };
const folder = mkdtempSync(join(tmpdir(), "guest-preview-"));
const entry = join(dirname(fileURLToPath(import.meta.url)), `.guestPreview-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter } from "react-router-dom";',
  'export { QueryClient, QueryClientProvider } from "@tanstack/react-query";',
  'export { AuthProvider } from "../src/state/Auth";',
  'export { Login } from "../src/pages/Login";',
  'export { Hero } from "../src/marketing/components/try/Hero";',
  'export { getScene } from "../src/marketing/data/scenes";',
].join("\n"));
let bundled: unknown;
try {
  const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
    plugins: [{ name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
      load: id => id === "\0empty-css" ? "export default {};" : null }],
  });
  try {
    const { output } = await bundler.generate({ format: "esm" });
    const path = join(folder, "bundle.mjs");
    writeFileSync(path, `import.meta.env = {};\n${output[0].code}`);
    bundled = await import(pathToFileURL(path).href);
  } finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
const source = bundled as {
  h: typeof import("react").createElement; act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  QueryClient: typeof import("@tanstack/react-query").QueryClient;
  QueryClientProvider: typeof import("@tanstack/react-query").QueryClientProvider;
  AuthProvider: typeof import("../src/state/Auth.tsx").AuthProvider;
  Login: typeof import("../src/pages/Login.tsx").Login;
  Hero: typeof import("../src/marketing/components/try/Hero.tsx").Hero;
  getScene: typeof import("../src/marketing/data/scenes.ts").getScene;
};
const { h, act, createRoot, MemoryRouter, QueryClient, QueryClientProvider, AuthProvider } = source;
const cleanups = new Set<() => Promise<void>>();
async function mountLogin(mode = "signin") {
  dom.reconfigure({ url: `http://localhost/login?mode=${mode}` });
  const container = dom.window.document.createElement("div");
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  await act(async () => root.render(h(QueryClientProvider, { client }, h(AuthProvider, null,
    h(MemoryRouter, { initialEntries: [`/login?mode=${mode}`] }, h(source.Login))))));
  const cleanup = async () => { await act(async () => root.unmount()); client.clear(); container.remove(); cleanups.delete(cleanup); };
  cleanups.add(cleanup);
  return { container, root };
}
function guestLink(container: HTMLElement) {
  const link = [...container.querySelectorAll("a")].find(anchor => anchor.textContent?.trim() === "Try a photo lesson");
  assert.ok(link, "Guests should have a visible way to try the existing sample lesson");
  return link;
}
async function click(element: Element) {
  assert.equal((element as HTMLButtonElement).disabled, false);
  await act(async () => { element.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true })); });
}
function button(container: Element, label: string) {
  const found = [...container.querySelectorAll("button")].find(candidate => !candidate.disabled && candidate.textContent?.trim() === label);
  assert.ok(found, `Expected enabled button: ${label}`);
  return found;
}
test.beforeEach(() => { events.length = 0; requests.length = 0; dom.window.sessionStorage.clear(); });
test.afterEach(async () => { for (const cleanup of [...cleanups]) await cleanup(); assert.deepEqual(requests, []); });
test.after(() => {
  dom.window.close();
  for (const channel of channels) { channel.port1.close(); channel.port2.close(); }
  globalThis.MessageChannel = NativeMessageChannel;
  globalThis.fetch = originalFetch;
});

for (const mode of ["signin", "signup"]) {
  test(`${mode} offers an unauthenticated sample lesson and tracks its entry`, async () => {
    const { container } = await mountLogin(mode);
    const link = guestLink(container);
    assert.equal(link.target, "");
    assert.match(container.textContent ?? "", /Preview progress won’t be saved to an account\./);
    const destination = new URL(link.href);
    assert.equal(destination.pathname, "/");
    assert.equal(destination.hash, "#try");
    assert.ok(source.getScene(destination.searchParams.get("photo") ?? ""));
    link.addEventListener("click", event => event.preventDefault());
    await act(async () => { link.click(); });
    const event = events.find(event => event[1] === "guest_preview_started");
    assert.ok(event);
    assert.deepEqual(event.slice(0, 2), ["event", "guest_preview_started"]);
    assert.equal((event[2] as Record<string, unknown>).source, mode);
  });
}

test("a guest can follow the entry and finish the real sample lesson without authentication or API calls", async () => {
  const { container, root } = await mountLogin();
  const destination = new URL(guestLink(container).href);
  const scene = source.getScene(destination.searchParams.get("photo") ?? "");
  assert.ok(scene);
  // A normal anchor starts a new document at the public demo's real deep link.
  dom.reconfigure({ url: destination.href });
  await act(async () => root.render(h(source.Hero)));
  assert.equal(container.querySelector("h2")?.textContent, `Found ${scene.words.length} things to learn`);
  await click(button(container, `Start learning ${scene.words.length} words`));
  for (let index = 0; index < scene.words.length; index++) {
    assert.ok(container.textContent?.includes(scene.words[index].es.word));
    await click(button(container, index === scene.words.length - 1 ? "Play I-Spy" : "Next word"));
  }
  assert.equal(container.querySelector("h2")?.textContent, "I-Spy with Linguini");
  await click(button(container, scene.ispy.es.answer));
  await click(button(container, "Next task"));
  assert.equal(container.querySelector("h2")?.textContent, "Describe the scene");
  await click(button(container, scene.blank.es.answer));
  await click(button(container, "Next task"));
  assert.equal(container.querySelector("h2")?.textContent, "Build a sentence");
  const bank = [...container.querySelectorAll("fieldset")].find(fieldset => fieldset.querySelector("legend")?.textContent === "Word tiles");
  assert.ok(bank);
  for (const token of scene.build.es.tokens) await click(button(bank, token));
  await click(button(container, "Check sentence"));
  await click(button(container, "Write today’s journal"));
  assert.equal(container.querySelector("h2")?.textContent, "Keep today in your journal");
  await click(button(container, "Save to journal"));
  assert.equal(container.querySelector("h2")?.textContent, "Saved. That’s a day well spent.");
  assert.ok(events.some(event => event[1] === "demo_completed"));
  assert.ok([...container.querySelectorAll("a")].some(link => link.textContent?.includes("Do this with your own photos")));
});

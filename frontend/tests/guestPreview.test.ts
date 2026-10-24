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
  'export { GuestDemo } from "../src/pages/GuestDemo";',
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
  GuestDemo: typeof import("../src/pages/GuestDemo.tsx").GuestDemo;
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
  const found = [...container.querySelectorAll("button")].find(candidate => !candidate.disabled && (candidate.textContent?.includes(label) || candidate.getAttribute("aria-label") === label));
  assert.ok(found, `Expected enabled button: ${label}. Found: ${[...container.querySelectorAll("button")].map(candidate => `${candidate.textContent?.trim()} (${candidate.disabled ? "disabled" : "enabled"})`).join(", ")}`);
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
    assert.equal(destination.pathname, "/demo");
    assert.equal(destination.hash, "");
    link.addEventListener("click", event => event.preventDefault());
    await act(async () => { link.click(); });
    const event = events.find(event => event[1] === "guest_preview_started");
    assert.ok(event);
    assert.deepEqual(event.slice(0, 2), ["event", "guest_preview_started"]);
    assert.equal((event[2] as Record<string, unknown>).source, mode);
  });
}

test("a guest can follow the entry and finish a sample lesson without authentication or API calls", async () => {
  const { container, root } = await mountLogin();
  const destination = new URL(guestLink(container).href);
  const scene = source.getScene("hillside-street");
  assert.ok(scene);
  dom.reconfigure({ url: destination.href });
  await act(async () => root.render(h(MemoryRouter, { initialEntries: ["/demo"] }, h(source.GuestDemo))));
  assert.equal(container.querySelector("h1")?.textContent, "Try a photo lesson");
  assert.equal(container.querySelector('input[type="file"]'), null);
  assert.doesNotMatch(container.textContent ?? "", /Upload photo/);
  await click(button(container, `Choose ${scene.title}`));
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
  assert.equal(container.querySelector("h1")?.textContent, "Review your scene");
  assert.match(container.textContent ?? "", /found five useful objects/i);
  assert.equal(container.querySelectorAll("[data-demo-marker]").length, 5);
  assert.match(container.textContent ?? "", /Describing words/);
  assert.match(container.textContent ?? "", /Position words/);
  await click(button(container, "See translations"));
  assert.equal(container.querySelectorAll('[data-demo-marker][data-active="true"]').length, 1);
  for (let index = 0; index < 5; index++) {
    assert.ok(container.textContent?.includes(scene.words[index].es.word));
    assert.match(container.textContent ?? "", /rojo/);
    assert.match(container.textContent ?? "", /al lado de/);
    await click(button(container, index === 4 ? "Try a task" : "Next word"));
  }
  assert.equal(container.querySelector("h1")?.textContent, "Choose the right word");
  await click(button(container, scene.words[0].es.word));
  await click(button(container, "Finish demo"));
  assert.equal(container.querySelector("h1")?.textContent, "You finished a photo lesson");
  assert.match(container.textContent ?? "", /wasn’t saved and no Basil was awarded/);
  assert.ok(events.some(event => event[1] === "guest_demo_completed"));
  assert.ok([...container.querySelectorAll("a")].some(link => link.textContent?.includes("Create my free account")));
});

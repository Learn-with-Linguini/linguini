import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test, { after } from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/", pretendToBeVisual: true });
const { window } = dom;
for (const key of ["window", "document", "localStorage", "sessionStorage", "HTMLElement", "Element", "Node", "SVGElement", "navigator", "HTMLMediaElement", "MutationObserver", "getComputedStyle", "requestAnimationFrame", "cancelAnimationFrame"] as const) {
  Object.defineProperty(globalThis, key, { value: key === "window" ? window : window[key], configurable: true });
}

// Browser APIs JSDOM does not implement, stubbed to inert no-ops.
Object.defineProperty(window, "matchMedia", {
  value: (media: string) => ({ matches: false, media, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false }),
  configurable: true,
});
Object.defineProperty(window, "IntersectionObserver", {
  value: class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } },
  configurable: true,
});
Object.defineProperty(window, "ResizeObserver", {
  value: class { observe() {} unobserve() {} disconnect() {} },
  configurable: true,
});
Object.defineProperty(window, "scrollTo", { value: () => {}, configurable: true });
window.Element.prototype.scrollIntoView = () => {};
for (const method of ["play", "pause", "load"] as const) {
  Object.defineProperty(window.HTMLMediaElement.prototype, method, { value: () => Promise.resolve(), configurable: true });
}
for (const key of ["matchMedia", "IntersectionObserver", "ResizeObserver"] as const) {
  Object.defineProperty(globalThis, key, { value: window[key], configurable: true });
}
(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
const NativeMessageChannel = globalThis.MessageChannel;
const channels: MessageChannel[] = [];
globalThis.MessageChannel = class extends NativeMessageChannel {
  constructor() { super(); channels.push(this); }
};

const here = dirname(fileURLToPath(import.meta.url));
const folder = mkdtempSync(join(tmpdir(), "marketing-pages-"));
const entry = join(here, `.marketingPages-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h, act } from "react";',
  'export { createRoot } from "react-dom/client";',
  'export { MemoryRouter } from "react-router-dom";',
  'export { default as MarketingApp } from "../src/marketing/MarketingApp";',
].join("\n"));
let bundled: unknown;
try {
  const bundler = await rolldown({
    input: entry, platform: "node",
    resolve: { extensions: [".tsx", ".ts", ".js"] },
    transform: { define: { "import.meta.env": "{}" } },
    plugins: [{ name: "test-css", resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
      load: id => id === "\0empty-css" ? "export default {};" : null }],
  });
  try {
    const { output } = await bundler.generate({ format: "esm" });
    const path = join(folder, "bundle.mjs");
    writeFileSync(path, output[0].code);
    bundled = await import(pathToFileURL(path).href);
  } finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); rmSync(folder, { recursive: true, force: true }); }
const { h, act, createRoot, MemoryRouter, MarketingApp } = bundled as {
  h: typeof import("react").createElement; act: typeof import("react").act;
  createRoot: typeof import("react-dom/client").createRoot;
  MemoryRouter: typeof import("react-router-dom").MemoryRouter;
  MarketingApp: typeof import("../src/marketing/MarketingApp.tsx").default;
};

const mounted: { root: { unmount(): void }; container: HTMLElement }[] = [];
after(() => {
  for (const { root, container } of mounted) {
    act(() => root.unmount());
    container.remove();
  }
});
function renderRoute(path: string) {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  mounted.push({ root, container });
  act(() => root.render(h(MemoryRouter, { initialEntries: [path] }, h(MarketingApp))));
  return container;
}
function h1Text(path: string): string {
  const container = renderRoute(path);
  const h1 = container.querySelector("h1");
  const text = h1?.textContent.trim() ?? "";
  assert.ok(h1, `${path} rendered no h1`);
  assert.ok(text.length > 0, `${path} rendered an empty h1`);
  assert.ok(container.textContent.length > 200, `${path} rendered too little content (${container.textContent.length} chars)`);
  return text;
}

test("every marketing page renders without crashing", () => {
  const routes: [path: string, expectedH1: RegExp | null][] = [
    ["/", /language of\s+your day/i],
    ["/blog", /Linguini blog/i],
    ["/blog/launch-week", /How we’re launching Linguini/i],
    ["/blog/linguini-business-model", /The Linguini business model/i],
    ["/blog/why-we-teach-with-your-photos", /Why we teach with your photos/i],
    ["/blog/linguini-vs-duolingo", /Linguini vs Duolingo/i],
    ["/learn/spanish", /Learn Spanish/i],
    ["/learn/french", /Learn French/i],
    ["/learn/german", /Learn German/i],
    ["/learn/korean", /Learn Korean/i],
    ["/privacy", /Privacy policy/i],
    ["/terms", /Terms of service/i],
    ["/credits", /Photo credits/i],
    ["/share", null],
  ];
  for (const [path, expected] of routes) {
    const text = h1Text(path);
    if (expected) assert.match(text, expected, `${path} h1 was "${text}"`);
  }
});

test("unknown learn languages and blog slugs render the 404 page", () => {
  for (const path of ["/learn/elvish", "/blog/not-a-post"]) {
    assert.match(h1Text(path), /Page not found/i, path);
  }
});

test("an old blog slug redirects to its canonical post", () => {
  assert.match(h1Text("/blog/inside-a-linguini-lesson"), /Why we teach with your photos/i);
});

test("the home tab title is just the brand name", () => {
  h1Text("/");
  assert.equal(document.title, "Linguini");
});

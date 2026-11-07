import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import { prerenderDocument } from "../scripts/prerender-document.mjs";

test("the real client entry preserves cold 404s and mounts query-dependent share cards", async () => {
  const folder = mkdtempSync(join(process.cwd(), "tests/.marketing-bootstrap-"));
  const fixture = join(folder, "server.ts");
  const clientProxy = join(folder, "client.ts");
  writeFileSync(fixture, 'export { renderPage } from "../../src/prerender"; export { act } from "react";');
  writeFileSync(clientProxy, [
    'import * as client from "react-dom/client";',
    'export function createRoot(...args) { const root = client.createRoot(...args); globalThis.__seoBootstrapRoots.push(root); return root; }',
    'export function hydrateRoot(...args) { const root = client.hydrateRoot(...args); globalThis.__seoBootstrapRoots.push(root); return root; }',
  ].join("\n"));
  const bundler = await rolldown({
    input: { main: "src/main.tsx", server: fixture }, platform: "node",
    resolve: { extensions: [".tsx", ".ts", ".js"] },
    transform: { define: { "import.meta.env": "{}" } },
    external: ["react", "react-dom", "react-dom/server", "react/jsx-runtime"],
    plugins: [{
      name: "bootstrap-fixture",
      resolveId(id, importer) {
        if (id.endsWith(".css")) return "\0css";
        if (id === "react-dom/client") return importer === clientProxy ? { id, external: true } : clientProxy;
        return null;
      },
      load: id => id === "\0css" ? "export default {}" : null,
    }],
  });
  const keys = ["window", "document", "navigator", "HTMLElement", "Element", "Node", "IntersectionObserver", "ResizeObserver", "IS_REACT_ACT_ENVIRONMENT", "__seoBootstrapRoots"];
  const original = new Map(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  const consoleError = console.error;
  const errors: unknown[][] = [];
  let dom: JSDOM | undefined;
  const roots: { unmount(): void }[] = [];
  try {
    const { output } = await bundler.generate({ format: "esm", dir: folder, entryFileNames: "[name].mjs", chunkFileNames: "[name]-[hash].mjs" });
    for (const chunk of output) {
      if (chunk.type === "chunk") writeFileSync(join(folder, chunk.fileName), chunk.code);
    }
    const { renderPage, act } = await import(pathToFileURL(join(folder, "server.mjs")).href);
    const template = '<!doctype html><html><head><title data-shell-meta>Linguini</title></head><body><div id="root"></div></body></html>';
    console.error = (...args) => errors.push(args);
    for (const [scenario, url, markup] of [
      ["missing", "https://www.learnwithlinguini.com/seo-missing-page", renderPage("/404")],
      ["share", "https://www.learnwithlinguini.com/share?lang=fr&title=Coffee%20break&words=caf%C3%A9,table", null],
    ] as const) {
      dom = new JSDOM(prerenderDocument(template, markup, [], scenario === "missing" ? "not-found" : undefined), { url, pretendToBeVisual: true });
      const { window } = dom;
      for (const key of ["window", "document", "navigator", "HTMLElement", "Element", "Node"]) {
        Object.defineProperty(globalThis, key, { value: key === "window" ? window : window[key], configurable: true });
      }
      const Observer = class { observe() {} unobserve() {} disconnect() {} };
      for (const key of ["IntersectionObserver", "ResizeObserver"]) Object.defineProperty(globalThis, key, { value: Observer, configurable: true });
      Object.defineProperty(window, "matchMedia", { value: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }), configurable: true });
      Object.defineProperty(window, "scrollTo", { value: () => {}, configurable: true });
      Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { value: true, configurable: true });
      Object.defineProperty(globalThis, "__seoBootstrapRoots", { value: roots, configurable: true });
      const initialHeading = window.document.querySelector("h1");
      await act(async () => { await import(`${pathToFileURL(join(folder, "main.mjs")).href}?scenario=${scenario}`); });
      assert.equal(roots.length, 1);
      assert.equal(window.document.querySelectorAll("title").length, 1);
      assert.equal(window.document.querySelectorAll('meta[name="robots"]').length, 1);
      assert.equal(window.document.querySelector<HTMLMetaElement>('meta[name="robots"]')?.content, "noindex,follow");
      assert.equal(window.document.querySelector('link[rel="canonical"]'), null);
      if (scenario === "missing") {
        assert.equal(window.document.querySelector("h1"), initialHeading);
        assert.match(initialHeading?.textContent ?? "", /Page not found/);
        assert.equal(window.location.pathname, "/seo-missing-page");
      } else {
        assert.equal(window.document.querySelector("h1")?.textContent, "Coffee break");
        assert.equal(window.document.querySelector("[data-shell-meta]"), null);
        assert.match(window.document.body.textContent ?? "", /journal · French/);
      }
      await act(async () => { roots.pop()?.unmount(); });
      dom.window.close();
      dom = undefined;
    }
    assert.deepEqual(errors, []);
  } finally {
    for (const root of roots) root.unmount();
    console.error = consoleError;
    dom?.window.close();
    for (const [key, descriptor] of original) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
    await bundler.close();
    rmSync(folder, { recursive: true, force: true });
  }
});

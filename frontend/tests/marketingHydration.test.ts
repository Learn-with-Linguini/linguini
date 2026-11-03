import assert from "node:assert/strict";
import { rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";
import { prerenderDocument } from "../scripts/prerender-document.mjs";

test("marketing HTML hydrates without replacing content or duplicating head metadata", async () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const entry = join(here, `.marketingHydration-${crypto.randomUUID()}.ts`);
  writeFileSync(entry, [
    'export { createElement as h, StrictMode, act, lazy } from "react";',
    'export { hydrateRoot } from "react-dom/client";',
    'export { renderToString } from "react-dom/server";',
    'export { StaticRouter, BrowserRouter } from "react-router-dom";',
    'export { SiteRoot } from "../src/SiteRoot";',
    'export { default as MarketingApp } from "../src/marketing/MarketingApp";',
  ].join("\n"));
  let dom: JSDOM | undefined;
  let root: ReturnType<typeof import("react-dom/client").hydrateRoot> | undefined;
  const globals = ["window", "document", "navigator", "HTMLElement", "Element", "Node", "IntersectionObserver", "ResizeObserver", "IS_REACT_ACT_ENVIRONMENT"];
  const original = new Map(globals.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  try {
    const bundler = await rolldown({
      input: entry, platform: "node", resolve: { extensions: [".tsx", ".ts", ".js"] },
      transform: { define: { "import.meta.env": "{}" } },
      external: ["react", "react-dom/client", "react-dom/server", "react/jsx-runtime"],
      plugins: [{ name: "test-css", resolveId: id => id.endsWith(".css") ? "\0css" : null, load: id => id === "\0css" ? "export default {}" : null }],
    });
    const outputPath = join(here, `.marketingHydration-${crypto.randomUUID()}.mjs`);
    let app;
    try {
      const { output } = await bundler.generate({ format: "esm" });
      writeFileSync(outputPath, output[0].code);
      app = await import(pathToFileURL(outputPath).href);
    } finally { await bundler.close(); rmSync(outputPath, { force: true }); }
    const { h, StrictMode, act, lazy, hydrateRoot, renderToString, StaticRouter, BrowserRouter, SiteRoot, MarketingApp } = app;
    const path = "/blog/why-we-teach-with-your-photos";
    const server = h(StrictMode, null, h(StaticRouter, { location: path }, h(SiteRoot, null, h(MarketingApp))));
    const html = prerenderDocument('<!doctype html><html><head><title>Fallback</title></head><body><div id="root"></div></body></html>', renderToString(server));
    assert.match(html, /<!--\$-->/, "Suspense boundary survives extraction");
    dom = new JSDOM(html, { url: `https://www.learnwithlinguini.com${path}`, pretendToBeVisual: true });
    const { window } = dom;
    for (const key of ["window", "document", "navigator", "HTMLElement", "Element", "Node"]) {
      Object.defineProperty(globalThis, key, { value: key === "window" ? window : window[key], configurable: true });
    }
    Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { value: true, configurable: true });
    const Observer = class { observe() {} unobserve() {} disconnect() {} };
    for (const key of ["IntersectionObserver", "ResizeObserver"]) {
      Object.defineProperty(globalThis, key, { value: Observer, configurable: true });
      Object.defineProperty(window, key, { value: Observer, configurable: true });
    }
    Object.defineProperty(window, "matchMedia", { value: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }), configurable: true });
    Object.defineProperty(window, "scrollTo", { value: () => {}, configurable: true });
    window.Element.prototype.scrollIntoView = () => {};
    // JSDOM does not initialize this media property from the server's muted attribute.
    window.document.querySelectorAll("video").forEach(video => { video.muted = video.hasAttribute("muted"); });
    const heading = window.document.querySelector("h1");
    const errors: Error[] = [];
    const LazyMarketingApp = lazy(async () => ({ default: MarketingApp }));
    await act(async () => {
      root = hydrateRoot(window.document.getElementById("root")!, h(StrictMode, null, h(BrowserRouter, null, h(SiteRoot, null, h(LazyMarketingApp)))), { onRecoverableError: (error: Error) => errors.push(error) });
    });
    assert.deepEqual(errors, []);
    assert.equal(window.document.querySelector("h1"), heading, "hydration reuses the server content");
    assert.equal(window.document.querySelectorAll('link[rel="canonical"]').length, 1);
    assert.equal(window.document.querySelectorAll('meta[name="description"]').length, 1);
    assert.equal(window.document.querySelectorAll("title").length, 1);
    const link = window.document.querySelector<HTMLAnchorElement>('a[href="/learn/german"]');
    assert.ok(link);
    await act(async () => { link.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 })); });
    assert.match(window.document.querySelector("h1")?.textContent ?? "", /Learn German/);
    assert.equal(window.document.querySelectorAll('link[rel="canonical"]').length, 1);
    assert.equal(window.document.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href, "https://www.learnwithlinguini.com/learn/german");
    assert.equal(window.document.querySelectorAll('meta[name="description"]').length, 1);
    assert.equal(window.document.querySelectorAll("title").length, 1);
    assert.equal(window.document.querySelector('meta[property="article:published_time"]'), null);
    await act(async () => {
      window.history.pushState({}, "", "/learn/german?utm_source=search#words-title");
      window.dispatchEvent(new window.PopStateEvent("popstate"));
    });
    assert.equal(window.document.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href, "https://www.learnwithlinguini.com/learn/german");
    await act(async () => {
      window.history.pushState({}, "", "/blog/missing-post");
      window.dispatchEvent(new window.PopStateEvent("popstate"));
    });
    assert.match(window.document.querySelector("h1")?.textContent ?? "", /Page not found/);
    assert.equal(window.document.querySelector('link[rel="canonical"]'), null);
    assert.equal(window.document.querySelector<HTMLMetaElement>('meta[name="robots"]')?.content, "noindex,follow");
    await act(async () => {
      window.history.pushState({}, "", "/share?title=Coffee%20break&words=caf%C3%A9,table&lang=fr");
      window.dispatchEvent(new window.PopStateEvent("popstate"));
    });
    assert.equal(window.document.querySelector("h1")?.textContent, "Coffee break");
    assert.equal(window.document.querySelector('link[rel="canonical"]'), null);
    assert.equal(window.document.querySelector<HTMLMetaElement>('meta[name="robots"]')?.content, "noindex,follow");
    assert.equal(window.document.querySelectorAll("title").length, 1);
    await act(async () => { root?.unmount(); });
    root = undefined;
    const errorMarkup = renderToString(h(StrictMode, null, h(StaticRouter, { location: "/404" }, h(SiteRoot, null, h(MarketingApp)))));
    const errorDocument = new JSDOM(prerenderDocument('<!doctype html><html><head></head><body><div id="root"></div></body></html>', errorMarkup, [], "not-found"));
    window.document.head.innerHTML = errorDocument.window.document.head.innerHTML;
    window.document.body.innerHTML = errorDocument.window.document.body.innerHTML;
    errorDocument.window.close();
    window.history.replaceState({}, "", "/not-a-real-page");
    const errorHeading = window.document.querySelector("h1");
    await act(async () => {
      root = hydrateRoot(window.document.getElementById("root")!, h(StrictMode, null, h(BrowserRouter, null, h(SiteRoot, null, h(LazyMarketingApp)))), { onRecoverableError: (error: Error) => errors.push(error) });
    });
    assert.deepEqual(errors, []);
    assert.equal(window.document.querySelector("h1"), errorHeading);
    assert.match(errorHeading?.textContent ?? "", /Page not found/);
    assert.equal(window.location.pathname, "/not-a-real-page", "the 404 bootstrap preserves the missing URL");
    assert.equal(window.document.querySelector('link[rel="canonical"]'), null);
    await act(async () => { root?.unmount(); });
    root = undefined;
  } finally {
    root?.unmount();
    dom?.window.close();
    for (const [key, descriptor] of original) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
    rmSync(entry, { force: true });
  }
});

test("the query-dependent share shell has no baked-in journal or homepage canonical", () => {
  const html = prerenderDocument('<!doctype html><html><head><title>Fallback</title><link rel="canonical" href="https://www.learnwithlinguini.com/"></head><body><div id="root"></div></body></html>', null);
  const dom = new JSDOM(html, { url: "https://www.learnwithlinguini.com/share?title=Private" });
  try {
    assert.equal(dom.window.document.getElementById("root")?.innerHTML, "");
    assert.equal(dom.window.document.getElementById("root")?.dataset.prerendered, undefined);
    assert.equal(dom.window.document.querySelector('link[rel="canonical"]'), null);
    assert.equal(dom.window.document.querySelector<HTMLMetaElement>('meta[name="robots"]')?.content, "noindex,follow");
    assert.doesNotMatch(html, /Private/);
  } finally { dom.window.close(); }
});

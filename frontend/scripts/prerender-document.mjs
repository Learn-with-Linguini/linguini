import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

/** Move React's hoisted head nodes without reparsing or dropping Suspense markers. */
export function prerenderDocument(template, markup, styles = [], page) {
  const dom = new JSDOM(template);
  const { document } = dom.window;
  const container = document.getElementById("root");
  assert.ok(container);
  document.head.querySelectorAll("title,meta[name='description'],meta[name='robots'],meta[property^='og:'],meta[property^='article:'],meta[name^='twitter:'],link[rel='canonical']").forEach(node => node.remove());
  if (markup === null) {
    const title = document.createElement("title");
    title.textContent = "Linguini";
    title.setAttribute("data-shell-meta", "");
    const robots = document.createElement("meta");
    robots.name = "robots";
    robots.content = "noindex,follow";
    robots.setAttribute("data-shell-meta", "");
    document.head.append(title, robots);
  } else {
    const fragment = JSDOM.fragment(markup);
    for (const node of [...fragment.childNodes]) {
      if (node.nodeType === 1 && ["TITLE", "META", "LINK"].includes(node.nodeName)) document.head.append(node);
    }
    container.append(fragment);
    container.dataset.prerendered = "true";
    if (page) container.dataset.page = page;
    for (const href of styles) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = `/${href}`;
      document.head.append(link);
    }
  }
  const html = dom.serialize();
  dom.window.close();
  return html;
}

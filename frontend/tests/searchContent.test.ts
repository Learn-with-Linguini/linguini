import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";
import { rolldown } from "rolldown";

const here = dirname(fileURLToPath(import.meta.url));
const folder = mkdtempSync(join(tmpdir(), "search-content-"));
const entry = join(here, `.searchContent-${crypto.randomUUID()}.ts`);
writeFileSync(entry, [
  'export { createElement as h } from "react";',
  'export { renderToStaticMarkup } from "react-dom/server";',
  'export { StaticRouter } from "react-router-dom";',
  'export { default as MarketingApp } from "../src/marketing/MarketingApp";',
  'export { languagePages } from "../src/marketing/data/languages";',
  'export { posts } from "../src/marketing/data/posts";',
].join("\n"));

type GraphNode = Record<string, unknown>;
type RenderBundle = {
  h: typeof import("react").createElement;
  renderToStaticMarkup: typeof import("react-dom/server").renderToStaticMarkup;
  StaticRouter: typeof import("react-router-dom").StaticRouter;
  MarketingApp: typeof import("../src/marketing/MarketingApp.tsx").default;
  languagePages: typeof import("../src/marketing/data/languages.ts").languagePages;
  posts: typeof import("../src/marketing/data/posts.ts").posts;
};

let bundle: RenderBundle;
try {
  const bundler = await rolldown({
    input: entry,
    platform: "node",
    resolve: { extensions: [".tsx", ".ts", ".js"] },
    transform: { define: { "import.meta.env": "{}" } },
    plugins: [{
      name: "test-css",
      resolveId: id => id.endsWith(".css") ? "\0empty-css" : null,
      load: id => id === "\0empty-css" ? "export default {};" : null,
    }],
  });
  try {
    const { output } = await bundler.generate({ format: "esm" });
    const path = join(folder, "bundle.mjs");
    writeFileSync(path, output[0].code);
    bundle = await import(pathToFileURL(path).href) as RenderBundle;
  } finally {
    await bundler.close();
  }
} finally {
  rmSync(entry, { force: true });
  rmSync(folder, { recursive: true, force: true });
}

function render(path: string) {
  const { h, renderToStaticMarkup, StaticRouter, MarketingApp } = bundle;
  const dom = new JSDOM(renderToStaticMarkup(h(StaticRouter, { location: path }, h(MarketingApp))));
  const { document } = dom.window;
  const graphs = Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
    .flatMap(node => {
      const data = JSON.parse(node.textContent ?? "{}");
      return (data["@graph"] ?? [data]) as GraphNode[];
    });
  return { document, graphs, close: () => dom.window.close() };
}

function assertReferencesResolve(graphs: GraphNode[]) {
  const definitions = new Set(graphs.map(node => node["@id"]).filter(Boolean));
  function visit(value: unknown) {
    if (Array.isArray(value)) return value.forEach(visit);
    if (!value || typeof value !== "object") return;
    const object = value as GraphNode;
    if (Object.keys(object).length === 1 && typeof object["@id"] === "string") {
      assert.ok(definitions.has(object["@id"]), `Unresolved entity ${object["@id"]}`);
    }
    Object.values(object).forEach(visit);
  }
  graphs.forEach(visit);
}

test("app structured data describes the English interface and all four taught languages", () => {
  const page = render("/");
  try {
    const app = page.graphs.find(node => node["@type"] === "SoftwareApplication");
    assert.ok(app);
    assert.equal(app.inLanguage, "en");
    const features = (app.featureList as string[]).join(" ");
    for (const language of ["Spanish", "French", "German", "Korean"]) assert.match(features, new RegExp(language));
    assert.equal(app.aggregateRating, undefined);
    assert.equal(app.review, undefined);
    assertReferencesResolve(page.graphs);
  } finally { page.close(); }
});

test("language pages pair visible vocabulary with meaningful term descriptions", () => {
  for (const language of bundle.languagePages) {
    const page = render(`/learn/${language.slug}`);
    try {
      const terms = page.graphs.find(node => node["@type"] === "DefinedTermSet");
      assert.ok(terms);
      assert.equal(terms.inLanguage, language.lang);
      const words = terms.hasDefinedTerm as GraphNode[];
      assert.ok(words.length > 0);
      const visibleWords = new Set(Array.from(page.document.querySelectorAll('tbody th[scope="row"]'))
        .map(node => node.firstChild?.textContent?.trim()));
      for (const word of words) {
        assert.ok(visibleWords.has(word.name as string), `${language.name}: ${String(word.name)} is absent from the page`);
        assert.doesNotMatch(String(word.description), /\((?:none|undefined|null)\)/);
      }
      if (language.lang === "ko") {
        assert.ok(words.every(word => !String(word.description).includes("(")));
        assert.match(page.document.body.textContent ?? "", /Korean has no grammatical gender or articles/);
      }
      assertReferencesResolve(page.graphs);
    } finally { page.close(); }
  }
});

test("articles identify their publisher, editorial dates and breadcrumb destinations", () => {
  for (const post of bundle.posts) {
    const page = render(`/blog/${post.slug}`);
    try {
      const article = page.graphs.find(node => node["@type"] === "BlogPosting");
      const publisher = page.graphs.find(node => node["@type"] === "Organization");
      const breadcrumb = page.graphs.find(node => node["@type"] === "BreadcrumbList");
      assert.ok(article && publisher && breadcrumb);
      assert.equal(publisher.name, "Linguini");
      assert.equal(article.datePublished, post.date);
      assert.equal(article.dateModified, post.updatedDate ?? post.date);
      const dates = Array.from(page.document.querySelectorAll("time")).map(node => node.dateTime);
      assert.ok(dates.includes(post.date));
      if (post.updatedDate) assert.ok(dates.includes(post.updatedDate));
      const items = breadcrumb.itemListElement as GraphNode[];
      assert.deepEqual(items.map(item => item.position), [1, 2, 3]);
      assert.equal(items.at(-1)?.item, article.url);
      assertReferencesResolve(page.graphs);
    } finally { page.close(); }
  }
});

test("comparison offers current beta access and links every supported language", () => {
  const page = render("/blog/linguini-vs-duolingo");
  try {
    const ownRow = Array.from(page.document.querySelectorAll("tbody tr"))
      .find(row => row.querySelector("th")?.textContent === "Linguini");
    assert.match(ownRow?.textContent ?? "", /Public beta\$0 during betaUnlimited photo lessons during beta/);
    for (const language of bundle.languagePages) {
      assert.ok(page.document.querySelector(`a[href="/learn/${language.slug}"]`));
    }
    assert.doesNotMatch(page.document.body.textContent ?? "", /Free covers one photo lesson|Plus raises it to ten/);
  } finally { page.close(); }
});

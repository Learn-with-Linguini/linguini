import assert from "node:assert/strict";
import test from "node:test";
import { inspectPage, parseSitemap } from "../scripts/seoChecks.mjs";

test("sitemap checks reject HTML fallbacks, duplicates and mixed canonical hosts", () => {
  const sitemap = (locations: string[]) => `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${locations.map(url => `<url><loc>${url}</loc></url>`).join("")}</urlset>`;
  assert.throws(() => parseSitemap("<html><body>SPA fallback</body></html>"));
  assert.throws(() => parseSitemap(sitemap(["https://example.com/", "https://example.com/"])));
  assert.throws(() => parseSitemap(sitemap(["https://example.com/", "https://preview.example.com/blog"])));
  assert.throws(() => parseSitemap(sitemap(["https://example.com/blog?campaign=test"])));
  assert.deepEqual(parseSitemap(sitemap(["https://example.com/", "https://example.com/blog"])).map(url => url.pathname), ["/", "/blog"]);
});

test("HTML checks detect homepage fallback metadata and missing initial content", () => {
  const result = inspectPage('<html><head><title>Linguini</title><meta name="description" content="Learn a language from a photograph of your day."><meta name="robots" content="index,follow"><link rel="canonical" href="https://example.com/"></head><body><div id="root"></div></body></html>', new URL("https://example.com/learn/korean"));
  assert.ok(result.problems.some(problem => problem.includes("canonical")));
  assert.ok(result.problems.includes("missing server-rendered page content"));
  assert.ok(result.problems.includes("missing server-rendered structured data"));
});

test("noindex shells cannot carry the homepage canonical", () => {
  const result = inspectPage('<html><head><title>Linguini</title><meta name="robots" content="noindex,follow"><link rel="canonical" href="https://example.com/"></head><body></body></html>', new URL("https://example.com/login"), { indexable: false });
  assert.deepEqual(result.problems, ["utility/error page must not inherit a canonical"]);
});

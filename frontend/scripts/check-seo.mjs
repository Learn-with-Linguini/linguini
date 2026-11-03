#!/usr/bin/env node
/** Check the actual HTTP response, without executing JavaScript. */
import assert from "node:assert/strict";
import { inspectPage, parseSitemap } from "./seoChecks.mjs";

const base = new URL(process.argv[2] ?? "http://localhost:4173");
const request = (path, options = {}) => fetch(new URL(path, base), { signal: AbortSignal.timeout(15000), ...options });
const sitemapResponse = await request("/sitemap.xml");
assert.equal(sitemapResponse.status, 200);
assert.match(sitemapResponse.headers.get("content-type") ?? "", /(?:application|text)\/xml/);
const urls = parseSitemap(await sitemapResponse.text());
const canonicalOrigin = urls[0].origin;

for (const url of urls) {
  const response = await request(url.pathname, { redirect: "manual" });
  assert.equal(response.status, 200, `${url.pathname}: HTTP ${response.status}`);
  assert.match(response.headers.get("content-type") ?? "", /text\/html/);
  const { problems, document } = inspectPage(await response.text(), url);
  assert.deepEqual(problems, [], `${url.pathname}: ${problems.join("; ")}`);
  const robots = response.headers.get("x-robots-tag") ?? "";
  assert.ok(!/noindex/i.test(robots), `${url.pathname}: X-Robots-Tag prevents indexing (preview deployments intentionally do this)`);
  const image = new URL(document.querySelector('meta[property="og:image"]').content);
  const imageResponse = image.origin === canonicalOrigin ? await request(image.pathname) : await fetch(image, { signal: AbortSignal.timeout(15000) });
  assert.equal(imageResponse.status, 200, `Missing sharing image: ${image.pathname}`);
  assert.match(imageResponse.headers.get("content-type") ?? "", /^image\//);
  console.log(`✓ ${url.pathname}`);
}

for (const path of ["/login", "/demo", "/home", "/practice/sessions/seo-check/analysis", "/ispy/friends/seo-check", "/share?lang=ko"]) {
  const response = await request(path, { redirect: "manual" });
  assert.equal(response.status, 200, `${path}: route refresh is broken`);
  const { problems } = inspectPage(await response.text(), new URL(path, canonicalOrigin), { indexable: false });
  assert.deepEqual(problems, [], `${path}: ${problems.join("; ")}`);
  assert.match(response.headers.get("x-robots-tag") ?? "", /noindex/i, `${path}: missing response noindex`);
}

for (const path of ["/seo-missing-page", "/blog/seo-missing-post", "/learn/seo-missing-language", "/assets/seo-missing.js"]) {
  const response = await request(path, { redirect: "manual" });
  assert.equal(response.status, 404, `${path}: missing resources must return 404`);
  const { problems } = inspectPage(await response.text(), new URL(path, canonicalOrigin), { indexable: false });
  assert.deepEqual(problems, [], `${path}: ${problems.join("; ")}`);
}

const redirect = await request("/blog/inside-a-linguini-lesson", { redirect: "manual" });
assert.ok([301, 308].includes(redirect.status), "Old article needs a permanent redirect");
assert.equal(new URL(redirect.headers.get("location"), base).pathname, "/blog/why-we-teach-with-your-photos");
const robots = await request("/robots.txt");
assert.equal(robots.status, 200);
assert.match(robots.headers.get("content-type") ?? "", /^text\/plain/);
assert.ok((await robots.text()).includes(`Sitemap: ${canonicalOrigin}/sitemap.xml`));
const manifest = await request("/manifest.webmanifest");
assert.equal(manifest.status, 200);
assert.equal((await manifest.json()).lang, "en");
const llms = await request("/llms.txt");
assert.equal(llms.status, 200);
assert.match(await llms.text(), /^# Linguini\n/);
console.log(`\n${urls.length} raw HTML pages, app refreshes, sharing images, redirects, discovery files and real 404s passed.`);

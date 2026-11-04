import assert from "node:assert/strict";
import { rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { rolldown } from "rolldown";
import { parseSitemap } from "../scripts/seoChecks.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const entry = join(here, `.siteFiles-${crypto.randomUUID()}.ts`);
const outputPath = entry.replace(/\.ts$/, ".mjs");
writeFileSync(entry, [
  'export { createSiteFiles } from "../vite/siteFiles";',
  'export { normalizeSiteUrl } from "../src/marketing/lib/siteUrl";',
  'export { marketingRoutes } from "../src/marketing/routes";',
  'export { posts } from "../src/marketing/data/posts";',
].join("\n"));
let bundle;
try {
  const bundler = await rolldown({ input: entry, platform: "node", resolve: { extensions: [".ts", ".js"] } });
  try {
    const { output } = await bundler.generate({ format: "esm" });
    writeFileSync(outputPath, output[0].code);
    bundle = await import(pathToFileURL(outputPath).href);
  } finally { await bundler.close(); }
} finally { rmSync(entry, { force: true }); rmSync(outputPath, { force: true }); }

test("sitemap and discovery files follow canonical routes and known editorial dates", () => {
  const files = bundle.createSiteFiles({ siteUrl: "https://example.com/" });
  const urls = parseSitemap(files["sitemap.xml"]);
  assert.deepEqual(urls.map(url => url.pathname), bundle.marketingRoutes);
  assert.equal((files["sitemap.xml"].match(/<lastmod>/g) ?? []).length, bundle.posts.length);
  for (const post of bundle.posts) {
    assert.ok(files["sitemap.xml"].includes(`<lastmod>${post.updatedDate ?? post.date}</lastmod>`));
  }
  for (const path of ["/login", "/share", "/home", "/404"]) assert.ok(!urls.some(url => url.pathname === path));
  const manifest = JSON.parse(files["manifest.webmanifest"]);
  for (const name of ["Spanish", "French", "German", "Korean"]) assert.ok(manifest.description.includes(name));
  assert.match(files["llms.txt"], /\[Interactive demo\]\(https:\/\/example.com\/demo\)/);
  const korean = files["llms.txt"].split("\n").find((line: string) => line.includes("[Learn Korean"));
  assert.doesNotMatch(korean, /articles|gender/);
});

test("malformed canonical origins and IndexNow keys fail the build instead of emitting bad discovery data", () => {
  for (const value of ["ftp://example.com", "https://user:password@example.com", "https://example.com/path", "https://example.com?x=1", "https://example.com/#fragment"]) {
    assert.throws(() => bundle.normalizeSiteUrl(value));
  }
  assert.equal(bundle.normalizeSiteUrl(" https://example.com/ "), "https://example.com");
  assert.equal(bundle.normalizeSiteUrl(undefined), "https://www.learnwithlinguini.com");
  for (const key of ["short", "bad key with spaces", "x".repeat(129)]) {
    assert.throws(() => bundle.createSiteFiles({ siteUrl: "https://example.com", indexNowKey: key }));
  }
  const files = bundle.createSiteFiles({ siteUrl: "https://example.com", indexNowKey: "valid-key-123" });
  assert.equal(files["indexnow-key.txt"], "valid-key-123");
});

import assert from "node:assert/strict";
import { readFile, readdir, stat } from "node:fs/promises";
import { isAbsolute, join, relative, resolve, sep } from "node:path";
import { inspectPage, parseSitemap } from "./seoChecks.mjs";

const directory = resolve(process.argv[2] ?? "dist");
const read = name => readFile(join(directory, name), "utf8");
const urls = parseSitemap(await read("sitemap.xml"));
const origin = urls[0].origin;
const titles = new Set();
const descriptions = new Set();
const pages = new Set();

async function requireAsset(href) {
  const url = new URL(href, origin);
  if (url.origin !== origin) return;
  const file = resolve(directory, `.${decodeURIComponent(url.pathname)}`);
  const rel = relative(directory, file);
  assert.ok(rel && !rel.startsWith("..") && !isAbsolute(rel), `Asset escapes output directory: ${href}`);
  assert.ok((await stat(file)).isFile(), `Missing asset: ${href}`);
}

for (const url of urls) {
  const file = url.pathname === "/" ? "index.html" : `${url.pathname.slice(1)}.html`;
  const { document, problems, title, description } = inspectPage(await read(file), url);
  assert.deepEqual(problems, [], `${url.pathname}: ${problems.join("; ")}`);
  assert.ok(!titles.has(title), `Duplicate title: ${title}`);
  assert.ok(!descriptions.has(description), `Duplicate description: ${url.pathname}`);
  titles.add(title);
  descriptions.add(description);
  pages.add(file);
  for (const element of document.querySelectorAll('link[rel="stylesheet"], script[src], img[src], meta[property="og:image"]')) {
    await requireAsset(element.getAttribute("href") ?? element.getAttribute("src") ?? element.getAttribute("content"));
  }
  const image = new URL(document.querySelector('meta[property="og:image"]').content);
  if (image.origin === origin) {
    const bytes = await readFile(join(directory, image.pathname.slice(1)));
    assert.equal(bytes.subarray(0, 8).toString("hex"), "89504e470d0a1a0a", `Sharing card must be a PNG: ${image.pathname}`);
    assert.equal(bytes.readUInt32BE(16), 1200, `Sharing card width: ${image.pathname}`);
    assert.equal(bytes.readUInt32BE(20), 630, `Sharing card height: ${image.pathname}`);
  }
  console.log(`✓ ${url.pathname}: content, canonical, metadata, structured data and assets`);
}

for (const file of ["app.html", "share.html", "404.html"]) {
  const { document, problems } = inspectPage(await read(file), new URL(`/${file}`, origin), { indexable: false });
  assert.deepEqual(problems, [], `${file}: ${problems.join("; ")}`);
  if (file === "404.html") assert.match(document.querySelector("h1")?.textContent ?? "", /not found/i);
}

for (const file of (await readdir(directory, { recursive: true })).map(name => name.split(sep).join("/"))) {
  if (!file.endsWith(".html") || pages.has(file) || ["app.html", "share.html", "404.html"].includes(file)) continue;
  const { document } = inspectPage(await read(file), new URL(`/${file}`, origin), { indexable: false });
  assert.ok(/noindex/.test(document.querySelector('meta[name="robots"]')?.content ?? ""), `Indexable page omitted from sitemap: ${file}`);
}

const robots = await read("robots.txt");
assert.match(robots, /^User-agent: \*$/m);
assert.ok(robots.includes(`Sitemap: ${origin}/sitemap.xml`), "Robots sitemap origin disagrees");
assert.doesNotMatch(robots, /^Disallow:\s*\//m, "Allow crawlers to read app noindex tags");
const manifest = JSON.parse(await read("manifest.webmanifest"));
assert.equal(manifest.lang, "en");
for (const icon of manifest.icons) await requireAsset(icon.src);
assert.match(await read("llms.txt"), /^# Linguini\n/);
const config = JSON.parse(await readFile(new URL("../vercel.json", import.meta.url), "utf8"));
assert.equal(config.cleanUrls, true);
assert.ok(!config.rewrites.some(rule => ["/(.*)", "/:path*"].includes(rule.source)), "Universal SPA rewrites conceal missing pages");
for (const source of [...config.rewrites.map(rule => rule.source), "/app", "/share", "/404"]) {
  assert.ok(config.headers.some(rule => rule.source === source && rule.headers.some(header => header.key.toLowerCase() === "x-robots-tag" && /noindex/i.test(header.value))), `Missing noindex response header for ${source}`);
}
console.log(`\n${urls.length} indexable pages and noindex app/share/error pages verified in raw build output.`);

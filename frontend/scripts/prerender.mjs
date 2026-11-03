import assert from "node:assert/strict";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { prerenderDocument } from "./prerender-document.mjs";
import { learnerRoutePatterns, marketingRoutes, movedPosts, renderPage } from "../dist-ssr/prerender.js";

const output = resolve("dist");
const template = await readFile(resolve(output, "index.html"), "utf8");
const manifest = JSON.parse(await readFile(resolve(output, ".vite/manifest.json"), "utf8"));
const config = JSON.parse(await readFile("vercel.json", "utf8"));

assert.deepEqual(config.rewrites, learnerRoutePatterns.map(source => ({ source, destination: "/app" })), "Vercel learner rewrites must match routes.ts");
assert.deepEqual(config.redirects, Object.entries(movedPosts).map(([from, to]) => ({ source: `/blog/${from}`, destination: `/blog/${to}`, permanent: true })), "Vercel blog redirects must match movedPosts");
assert.deepEqual(config.headers, [...learnerRoutePatterns, "/app", "/share", "/404"].map(source => ({ source, headers: [{ key: "X-Robots-Tag", value: "noindex, follow" }] })), "Vercel noindex headers must cover every app/share/error route");

const styles = new Set();
const visited = new Set();
function collectStyles(key) {
  if (visited.has(key)) return;
  visited.add(key);
  const chunk = manifest[key];
  assert.ok(chunk, `Missing client chunk ${key}`);
  chunk.css?.forEach(file => styles.add(file));
  chunk.imports?.forEach(collectStyles);
}
collectStyles("src/marketing/MarketingApp.tsx");

for (const path of marketingRoutes) {
  const html = prerenderDocument(template, renderPage(path), styles);
  const destination = resolve(output, path === "/" ? "index.html" : `${path.slice(1)}.html`);
  await mkdir(dirname(destination), { recursive: true });
  await writeFile(destination, html);
}
for (const name of ["app", "share"]) {
  await writeFile(resolve(output, `${name}.html`), prerenderDocument(template, null));
}
await writeFile(resolve(output, "404.html"), prerenderDocument(template, renderPage("/404"), styles, "not-found"));
await rm(resolve("dist-ssr"), { recursive: true });
console.log(`Rendered ${marketingRoutes.length} public pages, app/share shells and a 404 page.`);

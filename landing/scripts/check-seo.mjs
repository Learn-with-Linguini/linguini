#!/usr/bin/env node
/**
 * Crawl the sitemap and check every page for the tags search engines and link previews need.
 *
 *   npm run build && npx next start --port 3456   # in one terminal
 *   node scripts/check-seo.mjs http://localhost:3456
 *
 * Also works against production: node scripts/check-seo.mjs https://linguini-landing.vercel.app
 * Canonical and og:url are compared by path, so a local build with the production site URL passes.
 * Exits 1 if any page fails.
 */
const base = (process.argv[2] ?? "http://localhost:3000").replace(/\/$/, "");
// Social crawlers get metadata in <head> without streaming; check what they see.
const headers = { "User-Agent": "facebookexternalhit/1.1" };

const decode = s => s.replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#x27;/g, "'");
const meta = (html, key) => {
  const tag = html.match(new RegExp(`<meta[^>]+(?:property|name)="${key}"[^>]*>`, "i"))?.[0];
  return tag ? decode(tag.match(/content="([^"]*)"/i)?.[1] ?? "") : "";
};
const pathOf = url => {
  try {
    return new URL(url).pathname.replace(/\/$/, "") || "/";
  } catch {
    return "";
  }
};

async function checkPage(url) {
  const problems = [];
  const warnings = [];
  const res = await fetch(url, { headers });
  if (!res.ok) return { problems: [`HTTP ${res.status}`], warnings };
  const html = await res.text();
  const path = pathOf(url);

  const title = decode(html.match(/<title>([^<]*)<\/title>/i)?.[1] ?? "");
  const description = meta(html, "description");
  const canonical = html.match(/<link rel="canonical" href="([^"]+)"/i)?.[1] ?? "";
  const h1s = (html.match(/<h1[\s>]/gi) ?? []).length;

  if (title.length < 10 || title.length > 70) problems.push(`title is ${title.length} chars: "${title}"`);
  if (description.length < 50) problems.push(`description is ${description.length} chars`);
  // Longer descriptions are not penalised, but search results cut them off around here.
  else if (description.length > 160) warnings.push(`description is ${description.length} chars; results show about 160`);
  if (pathOf(canonical) !== path) problems.push(`canonical ${canonical || "missing"} ≠ ${path}`);
  if (h1s !== 1) problems.push(`${h1s} <h1> elements`);

  for (const key of ["og:title", "og:description", "og:url", "og:image", "og:type", "twitter:card", "twitter:image"]) {
    if (!meta(html, key)) problems.push(`missing ${key}`);
  }
  if (meta(html, "og:url") && pathOf(meta(html, "og:url")) !== path) problems.push(`og:url points at ${meta(html, "og:url")}`);
  if (path !== "/" && meta(html, "og:description") === homeDescription) problems.push("og:description is the home page's");

  const image = meta(html, "og:image");
  if (image) {
    // Fetch from this server even when the tag carries the production host.
    const img = await fetch(`${base}${new URL(image).pathname}${new URL(image).search}`);
    const type = img.headers.get("content-type") ?? "";
    if (!img.ok || !type.startsWith("image/")) problems.push(`og:image ${img.status} ${type}`);
  }

  for (const [, json] of html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)) {
    try {
      JSON.parse(json);
    } catch {
      problems.push("invalid JSON-LD");
    }
  }
  return { problems, warnings };
}

const home = await fetch(`${base}/`, { headers }).then(r => r.text());
const homeDescription = meta(home, "og:description");

const sitemap = await fetch(`${base}/sitemap.xml`).then(r => r.text());
const urls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => `${base}${pathOf(m[1]) === "/" ? "/" : pathOf(m[1])}`);

let failed = 0;
for (const url of urls) {
  const { problems, warnings } = await checkPage(url);
  failed += problems.length ? 1 : 0;
  const mark = problems.length ? "✗" : warnings.length ? "!" : "✓";
  const notes = [...problems, ...warnings.map(w => `warning: ${w}`)].map(p => `\n    ${p}`).join("");
  console.log(`${mark} ${url.replace(base, "") || "/"}${notes}`);
}

for (const file of ["/robots.txt", "/llms.txt", "/manifest.webmanifest"]) {
  const res = await fetch(`${base}${file}`);
  failed += res.ok ? 0 : 1;
  console.log(`${res.ok ? "✓" : "✗"} ${file}${res.ok ? "" : ` HTTP ${res.status}`}`);
}

console.log(`\n${urls.length} pages checked, ${failed} with problems.`);
process.exit(failed ? 1 : 0);

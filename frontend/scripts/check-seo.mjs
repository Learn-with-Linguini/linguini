#!/usr/bin/env node
/**
 * Check client-rendered search and sharing metadata on every URL in the sitemap.
 *
 *   npm run build && npx vite preview --port 4173
 *   node scripts/check-seo.mjs http://localhost:4173
 *
 * Set CHROME to a local Chrome/Chromium executable when its default path differs.
 */
import { openPage, sleep } from "./chrome.mjs";

const base = (process.argv[2] ?? "http://localhost:4173").replace(/\/$/, "");
const homeResponse = await fetch(`${base}/`);
if (!homeResponse.ok) throw new Error(`Home returned HTTP ${homeResponse.status}`);

const sitemapResponse = await fetch(`${base}/sitemap.xml`);
if (!sitemapResponse.ok) throw new Error(`Sitemap returned HTTP ${sitemapResponse.status}`);
const sitemap = await sitemapResponse.text();
const urls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(match => {
  const parsed = new URL(match[1]);
  return `${base}${parsed.pathname}`;
});

const browser = await openPage(`${base}/`);
const evaluateMetadata = `(() => {
  const meta = key => document.querySelector('meta[name="' + key + '"],meta[property="' + key + '"]')?.content ?? "";
  const canonical = document.querySelector('link[rel="canonical"]')?.href ?? "";
  const jsonLd = [...document.querySelectorAll('script[type="application/ld+json"]')].map(node => {
    try { JSON.parse(node.textContent ?? ""); return true; } catch { return false; }
  });
  return { title: document.title, description: meta("description"), canonical, h1s: document.querySelectorAll("h1").length,
    ogTitle: meta("og:title"), ogDescription: meta("og:description"), ogUrl: meta("og:url"), ogImage: meta("og:image"),
    ogType: meta("og:type"), twitterCard: meta("twitter:card"), twitterImage: meta("twitter:image"), jsonLd };
})()`;
const pathOf = value => {
  try {
    return new URL(value).pathname.replace(/\/$/, "") || "/";
  } catch {
    return "";
  }
};

async function checkPage(url, homeDescription) {
  const problems = [];
  const warnings = [];
  const response = await fetch(url);
  if (!response.ok) return { problems: [`HTTP ${response.status}`], warnings };

  await browser.send("Page.navigate", { url });
  await sleep(700);
  const page = await browser.evaluate(evaluateMetadata);
  const path = pathOf(url);

  if (page.title.length < 10 || page.title.length > 70) problems.push(`title is ${page.title.length} chars: "${page.title}"`);
  if (page.description.length < 50) problems.push(`description is ${page.description.length} chars`);
  else if (page.description.length > 160) warnings.push(`description is ${page.description.length} chars; results show about 160`);
  if (pathOf(page.canonical) !== path) problems.push(`canonical ${page.canonical || "missing"} ≠ ${path}`);
  if (page.h1s !== 1) problems.push(`${page.h1s} <h1> elements`);

  for (const [key, value] of Object.entries({
    "og:title": page.ogTitle,
    "og:description": page.ogDescription,
    "og:url": page.ogUrl,
    "og:image": page.ogImage,
    "og:type": page.ogType,
    "twitter:card": page.twitterCard,
    "twitter:image": page.twitterImage,
  })) {
    if (!value) problems.push(`missing ${key}`);
  }
  if (page.ogUrl && pathOf(page.ogUrl) !== path) problems.push(`og:url points at ${page.ogUrl}`);
  if (path !== "/" && page.ogDescription === homeDescription) problems.push("og:description is the home page's");

  if (page.ogImage) {
    const imageUrl = new URL(page.ogImage);
    const image = await fetch(`${base}${imageUrl.pathname}${imageUrl.search}`);
    const type = image.headers.get("content-type") ?? "";
    if (!image.ok || !type.startsWith("image/")) problems.push(`og:image ${image.status} ${type}`);
  }
  if (page.jsonLd.some(valid => !valid)) problems.push("invalid JSON-LD");
  return { problems, warnings };
}

const home = await browser.evaluate(evaluateMetadata);
const homeDescription = home.ogDescription;
let failed = 0;

try {
  for (const url of urls) {
    const { problems, warnings } = await checkPage(url, homeDescription);
    failed += problems.length ? 1 : 0;
    const mark = problems.length ? "✗" : warnings.length ? "!" : "✓";
    const notes = [...problems, ...warnings.map(warning => `warning: ${warning}`)].map(note => `\n    ${note}`).join("");
    console.log(`${mark} ${url.replace(base, "") || "/"}${notes}`);
  }

  for (const file of ["/robots.txt", "/llms.txt", "/manifest.webmanifest"]) {
    const response = await fetch(`${base}${file}`);
    failed += response.ok ? 0 : 1;
    console.log(`${response.ok ? "✓" : "✗"} ${file}${response.ok ? "" : ` HTTP ${response.status}`}`);
  }
} finally {
  browser.close();
}

console.log(`\n${urls.length} pages checked, ${failed} with problems.`);
process.exit(failed ? 1 : 0);

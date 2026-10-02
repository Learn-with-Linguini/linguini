#!/usr/bin/env node
/**
 * Ask IndexNow search engines (Bing and partners) to re-crawl every URL in the live sitemap.
 * Run after a production deploy that changes content:
 *
 *   INDEXNOW_KEY=<same key as on Vercel> node scripts/indexnow.mjs https://linguini-landing.vercel.app
 *
 * The deployed site must serve the key at /indexnow-key.txt (set INDEXNOW_KEY on Vercel too).
 */
const base = (process.argv[2] ?? process.env.NEXT_PUBLIC_SITE_URL ?? "").replace(/\/$/, "");
const key = process.env.INDEXNOW_KEY;
if (!base || !key) {
  console.error("Usage: INDEXNOW_KEY=<key> node scripts/indexnow.mjs <site-url>");
  process.exit(1);
}

const keyLocation = `${base}/indexnow-key.txt`;
const served = await fetch(keyLocation).then(r => (r.ok ? r.text() : ""));
if (served.trim() !== key) {
  console.error(`${keyLocation} does not serve this key. Set INDEXNOW_KEY on the deployment and redeploy.`);
  process.exit(1);
}

const sitemap = await fetch(`${base}/sitemap.xml`).then(r => r.text());
const urlList = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => m[1]);

const response = await fetch("https://api.indexnow.org/indexnow", {
  method: "POST",
  headers: { "Content-Type": "application/json; charset=utf-8" },
  body: JSON.stringify({ host: new URL(base).host, key, keyLocation, urlList }),
});
console.log(`IndexNow: ${response.status} ${response.statusText} for ${urlList.length} URLs`);
process.exit(response.ok ? 0 : 1);

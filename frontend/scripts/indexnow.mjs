#!/usr/bin/env node
/**
 * Notify IndexNow after a production content deployment. This does not guarantee indexing.
 *
 *   INDEXNOW_KEY=<deployed key> node scripts/indexnow.mjs https://www.learnwithlinguini.com
 *
 * Requires the deployed /indexnow-key.txt, an indexable canonical home page and a valid sitemap.
 */
import { isIP } from "node:net";
import { pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";

const endpoint = "https://api.indexnow.org/indexnow";
const sitemapNamespace = "http://www.sitemaps.org/schemas/sitemap/0.9";
const maxUrls = 10_000;
const maxDocumentBytes = 5 * 1024 * 1024;
const hasNoIndex = value => /\b(?:noindex|none)\b/i.test(value ?? "");

function productionOrigin(value) {
  let url;
  try { url = new URL(value); } catch { throw new Error("Supply an explicit production http(s) origin."); }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.port || url.search || url.hash ||
      url.pathname !== "/" || (value !== url.origin && value !== `${url.origin}/`)) {
    throw new Error("The site URL must be a canonical http(s) origin, without credentials, a custom port, path, query or fragment.");
  }
  const hostname = url.hostname;
  if (isIP(hostname.replace(/^\[|\]$/g, "")) || hostname === "localhost" || hostname.endsWith(".localhost") ||
      hostname.endsWith(".local") || hostname.endsWith(".vercel.app") ||
      /(?:^|[.-])(?:dev|development|preview|staging|test)(?:[.-]|$)/i.test(hostname)) {
    throw new Error("Use the public production domain; preview, development and local hosts cannot be submitted.");
  }
  return url.origin;
}

async function readText(response, limit) {
  const reader = response.body?.getReader();
  if (!reader) return "";
  const decoder = new TextDecoder();
  let size = 0;
  let text = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) return text + decoder.decode();
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel();
        throw new Error(`Response exceeds the ${limit}-byte limit.`);
      }
      text += decoder.decode(value, { stream: true });
    }
  } finally { reader.releaseLock(); }
}

function mimeType(response) {
  return (response.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase();
}

function sitemapUrls(xml, origin) {
  if (/<!DOCTYPE|<!ENTITY/i.test(xml)) throw new Error("Sitemap must not contain a document type or entity declaration.");
  let dom;
  try { dom = new JSDOM(xml, { contentType: "application/xml" }); }
  catch { throw new Error("Sitemap is not valid XML."); }
  try {
    const root = dom.window.document.documentElement;
    if (root.localName !== "urlset" || root.namespaceURI !== sitemapNamespace) {
      throw new Error("Sitemap must be a urlset in the standard sitemap namespace.");
    }
    const entries = Array.from(root.children);
    if (!entries.length || entries.length > maxUrls) {
      throw new Error(`Sitemap must contain between 1 and ${maxUrls} URLs.`);
    }
    const urls = new Set();
    for (const entry of entries) {
      const locations = Array.from(entry.children).filter(node => node.localName === "loc" && node.namespaceURI === sitemapNamespace);
      if (entry.localName !== "url" || entry.namespaceURI !== sitemapNamespace || locations.length !== 1 || locations[0].children.length) {
        throw new Error("Every sitemap url must contain exactly one text loc element.");
      }
      const value = locations[0].textContent.trim();
      let url;
      try { url = new URL(value); } catch { throw new Error("Sitemap contains an invalid absolute URL."); }
      if (url.origin !== origin || url.username || url.password || url.search || url.hash || value !== url.href) {
        throw new Error("Sitemap URLs must use the canonical site origin, with no credentials, query or fragment.");
      }
      urls.add(url.href);
    }
    return [...urls];
  } finally { dom.window.close(); }
}

/** Validate deployment content before sending a single, bounded IndexNow notification. */
export async function submitIndexNow({ siteUrl, key, fetchImpl = fetch, timeoutMs = 15_000 }) {
  const origin = productionOrigin(siteUrl);
  if (typeof key !== "string" || !/^[A-Za-z0-9-]{8,128}$/.test(key)) {
    throw new Error("INDEXNOW_KEY must contain 8–128 letters, digits or dashes, matching the deployed key.");
  }
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 60_000) {
    throw new Error("Request timeout must be an integer between 1 and 60000 milliseconds.");
  }

  async function request(url, options = {}, readLimit) {
    const signal = AbortSignal.timeout(timeoutMs);
    let response;
    try {
      response = await fetchImpl(url, { ...options, redirect: "error", signal });
      if (response.redirected || (response.url && response.url !== url)) {
        throw new Error("Use the final canonical deployment origin; redirects are not accepted.");
      }
      if (readLimit !== undefined) {
        if (response.status !== 200) throw new Error(`Deployment returned HTTP ${response.status} for ${new URL(url).pathname}.`);
        return { response, text: await readText(response, readLimit) };
      }
      return { response };
    } catch (error) {
      await response?.body?.cancel().catch(() => {});
      if (signal.aborted) throw new Error(`Request to ${new URL(url).host}${new URL(url).pathname} timed out after ${timeoutMs}ms.`);
      if (error instanceof Error && error.name === "TypeError") throw new Error(`Could not fetch ${new URL(url).host}${new URL(url).pathname}; check network access and the canonical origin.`);
      throw new Error(error instanceof Error ? error.message.slice(0, 400) : "The request failed.");
    }
  }

  const keyLocation = `${origin}/indexnow-key.txt`;
  const keyFile = await request(keyLocation, {}, 512);
  if (mimeType(keyFile.response) !== "text/plain" || keyFile.text.trim() !== key) {
    throw new Error("The deployed /indexnow-key.txt must serve this exact key as text/plain. Set INDEXNOW_KEY and redeploy.");
  }

  const home = await request(`${origin}/`, {}, maxDocumentBytes);
  if (hasNoIndex(home.response.headers.get("x-robots-tag"))) {
    throw new Error("The production home page is marked noindex.");
  }
  if (!["text/html", "application/xhtml+xml"].includes(mimeType(home.response))) {
    throw new Error("The production home page must serve HTML.");
  }
  const dom = new JSDOM(home.text);
  try {
    const { document } = dom.window;
    const canonicals = document.querySelectorAll('link[rel="canonical"]');
    if (canonicals.length !== 1 || canonicals[0].getAttribute("href") !== `${origin}/`) {
      throw new Error("Home must declare exactly one canonical URL matching the supplied production origin.");
    }
    if (Array.from(document.querySelectorAll("meta[name]")).some(node =>
      /^(?:robots|googlebot|bingbot)$/i.test(node.getAttribute("name") ?? "") && hasNoIndex(node.getAttribute("content")))) {
      throw new Error("The production home page is marked noindex.");
    }
  } finally { dom.window.close(); }

  const sitemap = await request(`${origin}/sitemap.xml`, {}, maxDocumentBytes);
  if (!["application/xml", "text/xml"].includes(mimeType(sitemap.response))) {
    throw new Error("The deployed /sitemap.xml must serve XML, not an HTML fallback.");
  }
  const urlList = sitemapUrls(sitemap.text, origin);
  const { response } = await request(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify({ host: new URL(origin).hostname, key, keyLocation, urlList }),
  });
  await response.body?.cancel().catch(() => {});
  if (response.status !== 200 && response.status !== 202) {
    throw new Error(`IndexNow returned HTTP ${response.status}. Check the key, sitemap URLs and submission frequency.`);
  }
  return { status: response.status, submitted: urlList.length };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (process.argv.length !== 3) throw new Error("Usage: INDEXNOW_KEY=<key> node scripts/indexnow.mjs <production-origin>");
    const result = await submitIndexNow({ siteUrl: process.argv[2], key: process.env.INDEXNOW_KEY });
    console.log(`IndexNow received ${result.submitted} URLs (HTTP ${result.status}); crawling and indexing are not guaranteed.`);
  } catch (error) {
    console.error(error instanceof Error ? error.message.slice(0, 400) : "IndexNow submission failed.");
    process.exitCode = 1;
  }
}

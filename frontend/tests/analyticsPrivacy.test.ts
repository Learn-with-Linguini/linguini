import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { JSDOM } from "jsdom";
import { initAnalytics, trackAction, trackPageView } from "../src/lib/analytics.ts";

function browser(url: string, referrer = "") {
  const dom = new JSDOM("<!doctype html><title>Linguini</title>", { url, ...(referrer ? { referrer } : {}) });
  Object.defineProperty(globalThis, "window", { value: dom.window, configurable: true });
  Object.defineProperty(globalThis, "document", { value: dom.window.document, configurable: true });
  return dom;
}
function commands() {
  return (window.dataLayer ?? []).map(command => Array.from(command as IArguments));
}
function assertNoCredentials(value: unknown) {
  const encoded = JSON.stringify(value);
  for (const privateValue of ["fake-access-secret", "fake-refresh-secret", "fake-oauth-code", "private-message", "learner%40example.com"]) {
    assert.ok(!encoded.includes(privateValue), "Analytics must not receive authentication or free-text URL values");
  }
}

test("cold OAuth callback configures safe defaults before loading analytics providers", () => {
  const href = "https://www.learnwithlinguini.com/login?code=fake-oauth-code#access_token=fake-access-secret&refresh_token=fake-refresh-secret";
  const dom = browser(href, "https://www.learnwithlinguini.com/reset-password?code=fake-oauth-code");
  try {
    const beforeScriptLoad: { src: string; ga: unknown[][]; cs: unknown[][] }[] = [];
    const append = document.head.appendChild.bind(document.head);
    Object.defineProperty(document.head, "appendChild", { value(node: HTMLScriptElement) {
      beforeScriptLoad.push({ src: node.src, ga: commands(), cs: [...window._uxa ?? []] });
      return append(node);
    } });
    initAnalytics();
    const contentsquareLoad = beforeScriptLoad.find(load => load.src.includes("contentsquare.net"));
    assert.ok(contentsquareLoad?.cs.some(command => command[0] === "setQuery" && command[1] === ""));
    assert.ok(contentsquareLoad?.cs.some(command => command[0] === "referrer:removeQueryString"));
    const googleLoad = beforeScriptLoad.find(load => load.src.includes("googletagmanager.com"));
    assert.ok(googleLoad?.ga.some(command => command[0] === "config"));
    assertNoCredentials(beforeScriptLoad);
    const config = commands().find(command => command[0] === "config");
    assert.ok(config);
    assert.equal((config[2] as Record<string, unknown>).page_location, "https://www.learnwithlinguini.com/login");
    assert.equal((config[2] as Record<string, unknown>).page_referrer, "https://www.learnwithlinguini.com/reset-password");
    assertNoCredentials(commands());
    const queue = window._uxa ?? [];
    assert.ok(queue.some(command => command[0] === "setQuery" && command[1] === ""));
    assert.ok(queue.some(command => command[0] === "referrer:removeQueryString"));
    assert.equal(document.querySelectorAll('script[src="https://t.contentsquare.net/uxa/6a01544c67dfc.js"]').length, 1);
    initAnalytics();
    assert.equal(document.querySelectorAll('script[src="https://t.contentsquare.net/uxa/6a01544c67dfc.js"]').length, 1);
    assert.equal(window.location.href, href, "Supabase must retain the original callback URL");
  } finally { dom.window.close(); }
});

test("pageviews and custom-event defaults exclude secret queries, fragments and referrer values", () => {
  const dom = browser("https://www.learnwithlinguini.com/contact?subject=learner%40example.com&description=private-message#fake-access-secret");
  try {
    initAnalytics();
    trackPageView("/contact?subject=learner%40example.com&description=private-message", "Contact");
    trackAction("contact_form_submitted", { type: "feedback" });
    assertNoCredentials(commands());
    assertNoCredentials(window._uxa);
    const page = commands().find(command => command[0] === "event" && command[1] === "page_view");
    assert.equal((page?.[2] as Record<string, unknown>).page_path, "/contact");
    const action = commands().find(command => command[0] === "event" && command[1] === "contact_form_submitted");
    assert.equal((action?.[2] as Record<string, unknown>).page_location, "https://www.learnwithlinguini.com/contact");
  } finally { dom.window.close(); }
});

test("campaign attribution survives sanitization while callback codes and arbitrary data do not", () => {
  const href = "https://www.learnwithlinguini.com/login?mode=signup&utm_source=campus&utm_campaign=launch&code=fake-oauth-code&email=learner%40example.com#refresh_token=fake-refresh-secret";
  const dom = browser(href);
  try {
    initAnalytics();
    trackPageView();
    const page = commands().find(command => command[0] === "event" && command[1] === "page_view");
    const params = page?.[2] as Record<string, unknown>;
    assert.equal(params.page_location, "https://www.learnwithlinguini.com/login?mode=signup&utm_source=campus&utm_campaign=launch");
    assertNoCredentials(commands());
    assertNoCredentials(window._uxa);
    assert.equal(window.location.href, href);
  } finally { dom.window.close(); }
});

test("HTML does not start Contentsquare before URL privacy overrides are configured", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  assert.ok(!/<script[^>]+src=["']https:\/\/t\.contentsquare\.net\//.test(html));
});

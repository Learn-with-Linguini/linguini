import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { type TestContext } from "node:test";
import { JSDOM } from "jsdom";
import {
  GA_MEASUREMENT_IDS,
  initAnalytics,
  resolveGaMeasurementId,
  trackAction,
  trackPageView,
} from "../src/lib/analytics.ts";

function browser(t: TestContext, url = "https://www.learnwithlinguini.com/practice") {
  const dom = new JSDOM("<!doctype html><html><head><title>Linguini</title></head></html>", {
    url,
    referrer: "https://identity.example/login?code=REFERRER_SECRET#REFERRER_FRAGMENT",
  });
  const globals = ["window", "document"] as const;
  const descriptors = globals.map(key => Object.getOwnPropertyDescriptor(globalThis, key));
  for (const key of globals) {
    Object.defineProperty(globalThis, key, {
      configurable: true, value: key === "window" ? dom.window : dom.window.document,
    });
  }
  t.after(() => {
    dom.window.close();
    globals.forEach((key, index) => {
      if (descriptors[index]) Object.defineProperty(globalThis, key, descriptors[index]!);
      else delete (globalThis as Record<string, unknown>)[key];
    });
  });
  return dom.window as unknown as Window;
}

function assertNoUrlSecrets(value: unknown) {
  const serialized = JSON.stringify(value);
  for (const secret of [
    "ACCESS_SECRET", "REFRESH_SECRET", "RECOVERY_SECRET", "INVITE_SECRET",
    "REFERRER_SECRET", "REFERRER_FRAGMENT", "CALLER_SECRET", "utm_source",
  ]) assert.ok(!serialized.includes(secret), `Analytics included ${secret}`);
}

test("resolveGaMeasurementId maps dev and prod hostnames accurately", () => {
  assert.equal(resolveGaMeasurementId("dev.learnwithlinguini.com"), GA_MEASUREMENT_IDS.dev);
  assert.equal(resolveGaMeasurementId("www.learnwithlinguini.com"), GA_MEASUREMENT_IDS.prod);
  assert.equal(resolveGaMeasurementId("learnwithlinguini.com"), GA_MEASUREMENT_IDS.prod);
  assert.equal(resolveGaMeasurementId("other.domain.com"), null);
});

test("trackPageView sends pathname-only page and referrer dimensions", t => {
  const win = browser(t);
  const calls: unknown[][] = [];
  win.gtag = (...args) => { calls.push(args); };

  trackPageView("/practice/sessions/123/learn?code=RECOVERY_SECRET#ACCESS_SECRET", "Linguini - Practice");

  assert.deepEqual(win._uxa, [
    ["setPath", "/practice/sessions/123/learn"],
    ["setQuery", ""],
    ["referrer:removeQueryString"],
    ["trackPageview", "/practice/sessions/123/learn"],
  ]);
  assert.deepEqual(calls[1], ["event", "page_view", {
    page_path: "/practice/sessions/123/learn",
    page_location: "https://www.learnwithlinguini.com/practice/sessions/123/learn",
    page_referrer: "https://identity.example/login",
    page_title: "Linguini - Practice",
    send_to: GA_MEASUREMENT_IDS.prod,
  }]);
  assert.equal(calls[0][0], "set");
  assertNoUrlSecrets([calls, win._uxa]);
});

test("trackAction preserves action parameters and overrides unsafe URL dimensions", t => {
  const win = browser(t, "https://www.learnwithlinguini.com/rooms?code=INVITE_SECRET#ACCESS_SECRET");
  const calls: unknown[][] = [];
  win.gtag = (...args) => { calls.push(args); };
  const originalUrl = win.location.href;

  trackAction("task_answer_checked", {
    taskId: "task-1", isCorrect: true,
    page_path: "/rooms?code=CALLER_SECRET", page_location: "https://example.com/#CALLER_SECRET",
    page_referrer: "https://example.com/?code=CALLER_SECRET",
  });

  const expected = {
    taskId: "task-1", isCorrect: true, page_path: "/rooms",
    page_location: "https://www.learnwithlinguini.com/rooms",
    page_referrer: "https://identity.example/login",
  };
  assert.deepEqual(calls[1], ["event", "task_answer_checked", expected]);
  assert.deepEqual(win._uxa?.at(-1), ["trackCustomEvent", "task_answer_checked", expected]);
  assertNoUrlSecrets([calls, win._uxa]);
  assert.equal(win.location.href, originalUrl);
});

test("first-load privacy configuration precedes either third-party tag", t => {
  const win = browser(t,
    "https://www.learnwithlinguini.com/reset-password?code=RECOVERY_SECRET&utm_source=campaign"
    + "#access_token=ACCESS_SECRET&refresh_token=REFRESH_SECRET&type=recovery",
  );
  const originalUrl = win.location.href;
  const appended: { src: string; commands: unknown; ga: unknown; referrerPolicy: string }[] = [];
  const append = document.head.appendChild.bind(document.head);
  document.head.appendChild = function <T extends Node>(node: T): T {
    const script = node as unknown as HTMLScriptElement;
    appended.push({
      src: script.src, commands: structuredClone(win._uxa),
      ga: win.dataLayer?.map(args => Array.from(args as ArrayLike<unknown>)),
      referrerPolicy: script.referrerPolicy,
    });
    return append(node);
  };

  initAnalytics();

  assert.equal(appended.length, 2);
  const contentsquare = appended.find(item => item.src.includes("contentsquare.net"))!;
  assert.deepEqual(contentsquare.commands, [
    ["setPath", "/reset-password"], ["setQuery", ""], ["referrer:removeQueryString"],
  ]);
  const ga = appended.find(item => item.src.includes("googletagmanager.com"))!;
  assert.ok((ga.ga as unknown[][]).some(call => call[0] === "config"));
  assert.equal(appended.every(item => item.referrerPolicy === "no-referrer"), true);
  assertNoUrlSecrets(appended);
  trackPageView();
  trackAction("password_reset_completed");
  assertNoUrlSecrets([win._uxa, win.dataLayer]);
  assert.equal(win.location.href, originalUrl, "Recovery must retain its token for Supabase");

  initAnalytics();
  assert.equal(appended.length, 2, "Repeated initialization must not load tags twice");
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  assert.equal(html.includes("t.contentsquare.net/uxa/"), false, "The tag must wait for URL overrides");
});

test("SPA changes replace global URL defaults before page and action events", t => {
  const win = browser(t, "https://www.learnwithlinguini.com/reset-password#access_token=ACCESS_SECRET");
  const calls: unknown[][] = [];
  win.gtag = (...args) => { calls.push(args); };
  initAnalytics();
  win.history.pushState(null, "", "/rooms?code=INVITE_SECRET#refresh_token=REFRESH_SECRET");
  const originalUrl = win.location.href;

  trackPageView("/rooms?code=INVITE_SECRET");
  trackAction("room_joined");

  const pageEvent = calls.find(call => call[0] === "event" && call[1] === "page_view")!;
  const actionEvent = calls.find(call => call[0] === "event" && call[1] === "room_joined")!;
  assert.equal((pageEvent[2] as { page_path: string }).page_path, "/rooms");
  assert.equal((actionEvent[2] as { page_location: string }).page_location,
    "https://www.learnwithlinguini.com/rooms");
  assert.deepEqual(calls.at(-2), ["set", {
    page_path: "/rooms", page_location: "https://www.learnwithlinguini.com/rooms",
    page_referrer: "https://identity.example/login",
  }]);
  assertNoUrlSecrets([calls, win._uxa]);
  assert.equal(win.location.href, originalUrl);
});

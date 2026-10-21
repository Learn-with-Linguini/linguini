import assert from "node:assert/strict";
import test from "node:test";
import {
  ATTRIBUTION_STORAGE_KEY,
  captureAttribution,
  clearStoredAttribution,
  extractAttributionFromQuery,
  getStoredAttribution,
} from "../src/lib/attribution.ts";

test("extractAttributionFromQuery parses UTM parameters correctly", () => {
  const query = "?utm_source=tiktok&utm_medium=social&utm_campaign=public_beta&utm_content=week_1_photo&utm_term=learn_spanish";
  const result = extractAttributionFromQuery(query);
  assert.deepEqual(result, {
    utmSource: "tiktok",
    utmMedium: "social",
    utmCampaign: "public_beta",
    utmContent: "week_1_photo",
    utmTerm: "learn_spanish",
  });
});

test("extractAttributionFromQuery returns null when no UTM parameters exist", () => {
  assert.equal(extractAttributionFromQuery("?foo=bar&baz=1"), null);
  assert.equal(extractAttributionFromQuery(""), null);
});

test("captureAttribution stores first-touch attribution in localStorage", () => {
  const storage = new Map<string, string>();
  const mockLocalStorage = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  };

  (globalThis as unknown as { window: unknown }).window = globalThis;
  (globalThis as unknown as { localStorage: unknown }).localStorage = mockLocalStorage;

  clearStoredAttribution();
  assert.equal(getStoredAttribution(), null);

  const initial = captureAttribution("?utm_source=x&utm_medium=social&utm_campaign=public_beta");
  assert.deepEqual(initial, {
    utmSource: "x",
    utmMedium: "social",
    utmCampaign: "public_beta",
  });

  assert.equal(storage.has(ATTRIBUTION_STORAGE_KEY), true);
  assert.deepEqual(getStoredAttribution(), {
    utmSource: "x",
    utmMedium: "social",
    utmCampaign: "public_beta",
  });

  // Second touch should preserve original first-touch source
  const secondTouch = captureAttribution("?utm_source=linkedin&utm_medium=social&utm_campaign=second_touch");
  assert.deepEqual(secondTouch, {
    utmSource: "x",
    utmMedium: "social",
    utmCampaign: "public_beta",
  });
});

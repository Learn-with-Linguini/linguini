import assert from "node:assert/strict";
import test from "node:test";

process.env.VITE_API_BASE_URL = "http://api.test";
const { appearanceCommand, getGameResources, selectAppearance, saucePercent } = await import("../src/lib/gameResources.ts");

test("Sauce visual ratios stay bounded and a zero-capacity jar is empty", () => {
  const refillsAt = "2026-10-14T00:00:00Z";
  assert.equal(saucePercent({ capacity: 10, remaining: 3, refillsAt }), 30);
  assert.equal(saucePercent({ capacity: 10, remaining: 12, refillsAt }), 100);
  assert.equal(saucePercent({ capacity: 0, remaining: 0, refillsAt }), 0);
});

test("appearance retries retain the original accent and purchase key", () => {
  const command = appearanceCommand("herb", null, () => "same-purchase");
  assert.equal(appearanceCommand("pasta", command, () => "different-purchase"), command);
  assert.deepEqual(command, { appearance: "herb", commandId: "same-purchase" });
});

test("resource requests use the central API and purchase only a server-priced accent", async () => {
  const calls: { url: string; body: unknown; method?: string }[] = [];
  const resources = { sauce: { capacity: 10, remaining: 9, refillsAt: "2026-10-14T00:00:00Z" },
    basilLeaves: 25, appearance: "default", ownedAppearances: ["default"] };
  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : null });
    return Response.json(resources);
  };
  assert.deepEqual(await getGameResources(), resources);
  assert.deepEqual(await selectAppearance("herb", "purchase-1"), resources);
  assert.equal(calls[0].url, "http://api.test/api/v1/me/game-resources");
  assert.deepEqual(calls[1], { url: "http://api.test/api/v1/me/game-resources/appearance", method: "POST",
    body: { appearance: "herb", commandId: "purchase-1" } });
});

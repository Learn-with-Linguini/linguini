import assert from "node:assert/strict";
import test from "node:test";
import { assertSelectableLanguage, checkSelectableLanguage, profileLanguageChoices } from "../src/lib/languageChoices.ts";

test("existing choices remain available when pack discovery is off", () => {
  const choices = profileLanguageChoices([]);
  assert.equal(choices.find(language => language.code === "es")?.name, "Spanish");
  assert.ok(choices.every(language => !language.experimental));
});

test("pack-only Spanish locale is selectable with supported levels and status", () => {
  const choices = profileLanguageChoices([
    { code: "es-MX", levels: ["A0", "A1"], experimental: true },
    { code: "es", levels: ["A1"], experimental: true },
  ]);
  const added = choices.find(language => language.code === "es-MX");
  assert.ok(added?.name.includes("Spanish"));
  assert.deepEqual(added?.levels, ["A0", "A1"]);
  assert.equal(added?.experimental, true);
  assert.equal(choices.filter(language => language.code === "es").length, 1);
  assert.deepEqual(choices.find(language => language.code === "es")?.levels, ["A1"]);
  assert.equal(choices.find(language => language.code === "es")?.experimental, true);
});

test("save validation uses discovered Spanish levels and preserves legacy choices", () => {
  const packs = [{ code: "es-MX", levels: ["A1" as const], experimental: true }];
  assert.doesNotThrow(() => assertSelectableLanguage("es-MX", "A1", packs));
  assert.throws(() => assertSelectableLanguage("es-MX", "A2", packs), /available/);
  assert.throws(() => assertSelectableLanguage("es-MX", "A1", []), /available/);
  assert.doesNotThrow(() => assertSelectableLanguage("es", "A0", []));
});

test("built-in languages never wait on or depend on pack discovery", async () => {
  let calls = 0;
  const failingDiscovery = async () => { calls += 1; throw new Error("503 language_packs_unavailable"); };
  // Onboarding and profile saves for Spanish must not fail when discovery is down.
  await checkSelectableLanguage("es", "A2", failingDiscovery);
  assert.equal(calls, 0);
  // Pack levels only add M01; they do not restrict a built-in language's levels.
  assert.doesNotThrow(() => assertSelectableLanguage("ko", "B1", [
    { code: "ko", levels: ["A0"], experimental: true },
  ]));
});

test("pack-only languages are still checked against discovery", async () => {
  const packs = async () => [{ code: "it", levels: ["A0" as const, "A1" as const], experimental: true }];
  await checkSelectableLanguage("it", "A1", packs);
  await assert.rejects(checkSelectableLanguage("it", "A2", packs), /level available/);
  await assert.rejects(
    checkSelectableLanguage("it", "A0", async () => { throw new Error("503"); }), /503/,
  );
});

test("a saved profile remains selected if its pack is removed", () => {
  const choices = profileLanguageChoices([], "es-MX");
  assert.equal(choices.filter(language => language.code === "es-MX").length, 1);
  assert.deepEqual(choices.find(language => language.code === "es-MX")?.levels, []);
});

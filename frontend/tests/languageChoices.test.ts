import assert from "node:assert/strict";
import test from "node:test";
import { assertSelectableLanguage, checkSelectableLanguage, profileLanguageChoices } from "../src/lib/languageChoices.ts";

test("choices come only from pack discovery", () => {
  assert.deepEqual(profileLanguageChoices([]), []);
  const choices = profileLanguageChoices([
    { code: "ko", levels: ["A0"], experimental: true },
    { code: "es", levels: ["A1"], experimental: false },
    { code: "it", levels: [], experimental: true },
  ]);
  // Known languages keep their display order, name and flag; a pack with no ready level is not offered.
  assert.deepEqual(choices.map(language => language.code), ["es", "ko"]);
  assert.equal(choices[0].name, "Spanish");
  assert.ok(choices[0].flag);
  assert.deepEqual(choices[1].levels, ["A0"]);
  assert.equal(choices[1].experimental, true);
});

test("a pack-only locale is selectable with its levels and status", () => {
  const choices = profileLanguageChoices([
    { code: "es-MX", levels: ["A0", "A1"], experimental: true },
    { code: "es", levels: ["A1"], experimental: true },
  ]);
  const added = choices.find(language => language.code === "es-MX");
  assert.ok(added?.name.includes("Spanish"));
  assert.deepEqual(added?.levels, ["A0", "A1"]);
  assert.equal(added?.experimental, true);
  assert.equal(choices.filter(language => language.code === "es").length, 1);
});

test("save validation uses the discovered languages and levels for every language", () => {
  const packs = [{ code: "es", levels: ["A0" as const, "A1" as const], experimental: true }];
  assert.doesNotThrow(() => assertSelectableLanguage("es", "A1", packs));
  assert.throws(() => assertSelectableLanguage("es", "A2", packs), /level available/);
  assert.throws(() => assertSelectableLanguage("fr", "A1", packs), /available practice language/);
  assert.throws(() => assertSelectableLanguage("es", "A0", []), /available practice language/);
});

test("choosing a language waits on discovery and fails when it is down", async () => {
  const packs = async () => [{ code: "it", levels: ["A0" as const, "A1" as const], experimental: true }];
  await checkSelectableLanguage("it", "A1", packs);
  await assert.rejects(checkSelectableLanguage("it", "A2", packs), /level available/);
  await assert.rejects(checkSelectableLanguage("es", "A1", packs), /available practice language/);
  await assert.rejects(
    checkSelectableLanguage("it", "A0", async () => { throw new Error("503"); }), /503/,
  );
});

test("keeping the current language never depends on discovery", async () => {
  let calls = 0;
  const failingDiscovery = async () => { calls += 1; throw new Error("503 language_packs_unavailable"); };
  // Name or goal edits still save while the language's pack is unavailable.
  await checkSelectableLanguage("es", "A1", failingDiscovery, "es");
  assert.equal(calls, 0);
  await assert.rejects(checkSelectableLanguage("fr", "A1", failingDiscovery, "es"), /503/);
});

test("a saved profile remains selected if its pack is removed", () => {
  const choices = profileLanguageChoices([], "es-MX");
  assert.equal(choices.filter(language => language.code === "es-MX").length, 1);
  assert.deepEqual(choices.find(language => language.code === "es-MX")?.levels, []);
});

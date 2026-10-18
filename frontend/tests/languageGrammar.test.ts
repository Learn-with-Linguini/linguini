import assert from "node:assert/strict";
import test from "node:test";
import type { LanguageOption } from "../src/data/types.ts";
import { registryGender } from "../src/lib/languageGrammar.ts";

const spanish = {
  code: "es",
  englishName: "Spanish",
  nativeName: "Español",
  script: "Latn",
  direction: "ltr",
  wordSeparator: "space",
  learnable: true,
  instruction: false,
  speech: { synthesisLocale: "es-ES", synthesis: "browserVoice", recognition: false },
  grammar: { grammatical_gender: ["masculine", "feminine"] },
  features: { missionLevels: ["A0", "A1", "A2"] },
} satisfies LanguageOption;

const noGender = {
  ...spanish,
  code: "qaa",
  grammar: undefined,
} satisfies LanguageOption;

test("registryGender displays only genders listed for the card language", () => {
  assert.equal(registryGender([spanish], "es", "feminine"), "feminine");
  assert.equal(registryGender([noGender], "qaa", "feminine"), null);
  assert.equal(registryGender([spanish], "unknown", "feminine"), null);
});

import assert from "node:assert/strict";
import test from "node:test";
import { languageName, learnableLanguages } from "../src/lib/languages.ts";
import type { LanguageOption } from "../src/data/types.ts";

const languages: LanguageOption[] = [
  {
    code: "es",
    englishName: "Spanish",
    nativeName: "Español",
    script: "Latn",
    direction: "ltr",
    flag: "🇪🇸",
    wordSeparator: "space",
    learnable: true,
    instruction: false,
    speech: { synthesisLocale: "es-ES", synthesis: "browserVoice", recognition: false },
    features: { missionLevels: ["A0", "A1", "A2"] },
  },
  {
    code: "en",
    englishName: "English",
    nativeName: "English",
    script: "Latn",
    direction: "ltr",
    wordSeparator: "space",
    learnable: false,
    instruction: true,
    speech: { synthesisLocale: "en-US", synthesis: "browserVoice", recognition: false },
    features: { missionLevels: [] },
  },
];

test("learnableLanguages keeps registered-but-unavailable languages out of pickers", () => {
  assert.deepEqual(learnableLanguages(languages).map(language => language.code), ["es"]);
});

test("languageName looks up canonical codes case-insensitively", () => {
  assert.equal(languageName(languages, "ES"), "Spanish");
  assert.equal(languageName(languages, "EN"), "English");
  assert.equal(languageName(languages, "fr"), undefined);
});

import assert from "node:assert/strict";
import test from "node:test";
import { speechLocale } from "../src/lib/speech.ts";

test("speech locales expand supported language codes and preserve unknown locales", () => {
  assert.equal(speechLocale("es"), "es-ES");
  assert.equal(speechLocale("fr"), "fr-FR");
  assert.equal(speechLocale("de"), "de-DE");
  assert.equal(speechLocale("ko"), "ko-KR");
  assert.equal(speechLocale("es-MX"), "es-MX");
  assert.equal(speechLocale("it"), "it");
});

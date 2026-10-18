import assert from "node:assert/strict";
import test from "node:test";
import { hasVoiceFor } from "../src/lib/speech.ts";

const voice = (lang: string) => ({ lang }) as SpeechSynthesisVoice;

test("browser voice matching prefers a normalized exact locale", () => {
  assert.equal(hasVoiceFor([voice("fr-FR")], "FR-fr"), true);
  assert.equal(hasVoiceFor([voice("fr_CA")], "fr-CA"), true);
});

test("browser voice matching falls back to the primary language subtag", () => {
  assert.equal(hasVoiceFor([voice("fr-FR")], "fr-CA"), true);
});

test("browser voice matching rejects an unrelated locale", () => {
  assert.equal(hasVoiceFor([voice("es-ES")], "fr-FR"), false);
});

import assert from "node:assert/strict";
import test from "node:test";
import { availablePackVoice, speak, speechLocale } from "../src/lib/speech.ts";

test("speech locales expand supported language codes and preserve unknown locales", () => {
  assert.equal(speechLocale("es"), "es-ES");
  assert.equal(speechLocale("fr"), "fr-FR");
  assert.equal(speechLocale("de"), "de-DE");
  assert.equal(speechLocale("ko"), "ko-KR");
  assert.equal(speechLocale("es-MX"), "es-MX");
  assert.equal(speechLocale("it"), "it");
});

test("pack speech uses native text and configured Spanish locale only with an available voice", () => {
  const oldWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const oldUtterance = Object.getOwnPropertyDescriptor(globalThis, "SpeechSynthesisUtterance");
  const spoken: { text: string; lang: string }[] = [];
  const voices: { lang: string }[] = [];
  Object.defineProperty(globalThis, "window", { configurable: true, value: {
    speechSynthesis: { getVoices: () => voices, cancel() {}, speak: (value: typeof spoken[number]) => spoken.push(value) },
  } });
  Object.defineProperty(globalThis, "SpeechSynthesisUtterance", { configurable: true,
    value: class { text: string; lang = ""; constructor(text: string) { this.text = text; } },
  });
  try {
    const settings = { speechLocale: "es-MX", speechSynthesis: "browserVoice" as const };
    assert.equal(availablePackVoice(settings), false);
    speak("la taza", "es", settings);
    assert.equal(spoken.length, 0, "configuration does not install a voice");
    voices.push({ lang: "es-MX" });
    speak("la taza", "es", settings);
    assert.equal(spoken[0].text, "la taza");
    assert.equal(spoken[0].lang, "es-MX");
    speak("el libro", "es", { ...settings, speechSynthesis: "none" });
    assert.equal(spoken.length, 1);
  } finally {
    if (oldWindow) Object.defineProperty(globalThis, "window", oldWindow);
    else Reflect.deleteProperty(globalThis, "window");
    if (oldUtterance) Object.defineProperty(globalThis, "SpeechSynthesisUtterance", oldUtterance);
    else Reflect.deleteProperty(globalThis, "SpeechSynthesisUtterance");
  }
});

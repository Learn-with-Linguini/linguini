/** Plays the word with the browser voice when available; silently no-ops otherwise. */
const VOICE_LOCALES: Record<string, string> = {
  es: "es-ES",
  fr: "fr-FR",
  de: "de-DE",
  ko: "ko-KR",
};

export function speechLocale(lang: string) {
  return VOICE_LOCALES[lang] ?? lang;
}

export function speak(text: string, lang: string) {
  if (typeof window === "undefined" || !window.speechSynthesis) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = speechLocale(lang);
  utterance.rate = 0.9;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

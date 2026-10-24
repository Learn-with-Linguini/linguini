/** Plays the word with the browser voice when available; silently no-ops otherwise. */
const VOICE_LOCALES: Record<string, string> = {
  es: "es-ES",
  fr: "fr-FR",
  de: "de-DE",
  ko: "ko-KR",
};

export interface SpeechPreferences { speechLocale: string; speechSynthesis: "browserVoice" | "none" }

export function availablePackVoice(settings: SpeechPreferences) {
  if (settings.speechSynthesis === "none" || typeof window === "undefined" || !window.speechSynthesis) return false;
  const locale = settings.speechLocale.toLowerCase();
  return window.speechSynthesis.getVoices().some(voice => voice.lang.toLowerCase() === locale
    || voice.lang.toLowerCase().split("-")[0] === locale.split("-")[0]);
}

export function speechLocale(lang: string) {
  return VOICE_LOCALES[lang] ?? lang;
}

export function speak(text: string, lang: string, settings?: SpeechPreferences | null) {
  if (typeof window === "undefined" || !window.speechSynthesis) return;
  if (settings && !availablePackVoice(settings)) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = settings?.speechLocale ?? speechLocale(lang);
  utterance.rate = 0.9;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

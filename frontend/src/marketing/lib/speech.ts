const voiceLang = { es: "es-ES", fr: "fr-FR" } as const;

export type Lang = keyof typeof voiceLang;

export function canSpeak(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** Plays a word with the browser's built-in voice. Silently does nothing where unsupported. */
export function speak(text: string, lang: Lang) {
  if (!canSpeak()) return;
  const synth = window.speechSynthesis;
  synth.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = voiceLang[lang];
  utterance.rate = 0.9;
  const voice = synth.getVoices().find(v => v.lang.toLowerCase().startsWith(lang));
  if (voice) utterance.voice = voice;
  synth.speak(utterance);
}

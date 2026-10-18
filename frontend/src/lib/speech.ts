import { useEffect, useState } from "react";

export function hasVoiceFor(
  voices: readonly Pick<SpeechSynthesisVoice, "lang">[],
  locale: string,
): boolean {
  const normalize = (value: string) => value.replaceAll("_", "-").toLocaleLowerCase();
  const expected = normalize(locale);
  if (voices.some(voice => normalize(voice.lang) === expected)) return true;
  const primary = expected.split("-")[0];
  return voices.some(voice => normalize(voice.lang).split("-")[0] === primary);
}

export function useSpeechVoice(locale: string): boolean {
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.speechSynthesis) {
      setAvailable(false);
      return;
    }
    const synthesis = window.speechSynthesis;
    const update = () => setAvailable(hasVoiceFor(synthesis.getVoices(), locale));
    update();
    synthesis.addEventListener("voiceschanged", update);
    return () => synthesis.removeEventListener("voiceschanged", update);
  }, [locale]);

  return available;
}

export function speak(text: string, lang: string) {
  if (typeof window === "undefined" || !window.speechSynthesis) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  utterance.rate = 0.9;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

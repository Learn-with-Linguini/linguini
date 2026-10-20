import { createContext, useContext, useEffect, useState } from "react";
import type { LanguageDisplayContext } from "../lib/api";
import { availablePackVoice, speak } from "../lib/speech";

export const TargetLanguageContext = createContext<LanguageDisplayContext | null>(null);

export function useTargetLanguage() {
  const settings = useContext(TargetLanguageContext);
  const [, setVoiceRevision] = useState(0);
  useEffect(() => {
    if (!settings || typeof window === "undefined" || !window.speechSynthesis) return;
    const changed = () => setVoiceRevision(value => value + 1);
    window.speechSynthesis.addEventListener("voiceschanged", changed);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", changed);
  }, [settings]);
  return {
    settings,
    nativeProps: { dir: settings?.direction, lang: settings?.locale },
    speak: (text: string, language: string) => speak(text, language, settings),
    speechAvailable: () => settings ? availablePackVoice(settings)
      : typeof window !== "undefined" && Boolean(window.speechSynthesis),
  };
}

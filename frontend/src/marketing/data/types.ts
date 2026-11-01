export type Lang = "es" | "fr" | "de" | "ko";

export const languageNames: Record<Lang, string> = {
  es: "Spanish",
  fr: "French",
  de: "German",
  ko: "Korean",
};

export type Gender = "masculine" | "feminine" | "neuter" | "none";

export type WordEntry = {
  /** Target word including its article, e.g. "la mesa", "das Auto", "꽃". */
  word: string;
  gender: Gender;
  ipa: string;
};

export type SceneWord = {
  id: string;
  en: string;
  /** Marker position as a percentage of the photo's width and height. */
  x: number;
  y: number;
  es: WordEntry;
  fr: WordEntry;
  de: WordEntry;
  ko: WordEntry;
};

export type ISpyRound = {
  clue: string;
  clueEn: string;
  answer: string;
  choices: string[];
};

export type BlankRound = {
  /** Sentence with a single "___" gap. */
  sentence: string;
  en: string;
  answer: string;
  options: string[];
};

export type BuildRound = {
  en: string;
  /** Correct order of tiles. */
  tokens: string[];
};

export type JournalDraft = {
  title: string;
  body: string;
};

export type Scene = {
  id: string;
  photo: string;
  title: string;
  place: string;
  width: number;
  height: number;
  alt: string;
  words: SceneWord[];
  ispy: Record<Lang, ISpyRound>;
  /** Word card retained for the fixed gap exercise in every language. */
  blankWordId: string;
  blank: Record<Lang, BlankRound>;
  build: Record<Lang, BuildRound>;
  journal: Record<Lang, JournalDraft>;
};

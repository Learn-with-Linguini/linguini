export type Lang = "es" | "fr";

export const languageNames: Record<Lang, string> = { es: "Spanish", fr: "French" };

export type Gender = "masculine" | "feminine";

export type WordEntry = {
  /** Target word including its article, e.g. "la mesa". */
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
  blank: Record<Lang, BlankRound>;
  build: Record<Lang, BuildRound>;
  journal: Record<Lang, JournalDraft>;
};

import { getPhoto, photos, type Photo } from "./photos";

export type JournalLang = "es" | "fr";

export const LANGUAGE_NAME: Record<JournalLang, string> = {
  es: "Spanish",
  fr: "French",
};

export const JOURNAL_LIMITS = {
  words: 5,
  wordLength: 28,
  titleLength: 60,
} as const;

export const DEFAULT_JOURNAL_PHOTO: Photo = getPhoto("cafe-interior") ?? photos[0]!;

export type JournalCard = {
  photo: Photo;
  lang: JournalLang;
  words: string[];
  title?: string;
};

type RawParam = string | string[] | null | undefined;

function first(value: RawParam): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

const UNSAFE_CHARS = /[\p{Cc}\p{Cf}\p{Co}\p{Cs}\p{Extended_Pictographic}️]/gu;

export function cleanText(value: string, max: number): string {
  const chars = Array.from(value.normalize("NFC").replace(UNSAFE_CHARS, "").replace(/\s+/g, " ").trim());
  if (chars.length <= max) return chars.join("");
  const cut = chars.slice(0, max - 1).join("");
  const lastSpace = cut.lastIndexOf(" ");
  const head = lastSpace >= Math.floor(max * 0.6) ? cut.slice(0, lastSpace) : cut;
  return `${head.replace(/[\s.,;:·–—-]+$/u, "")}…`;
}

export function parseJournalCard(params: {
  photo?: RawParam;
  lang?: RawParam;
  words?: RawParam;
  title?: RawParam;
}): JournalCard {
  const photo = getPhoto(first(params.photo).trim().slice(0, 80)) ?? DEFAULT_JOURNAL_PHOTO;
  const lang: JournalLang = first(params.lang).trim().toLowerCase() === "fr" ? "fr" : "es";
  const seen = new Set<string>();
  const words: string[] = [];

  for (const part of first(params.words).slice(0, 600).split(",")) {
    const word = cleanText(part, JOURNAL_LIMITS.wordLength);
    const key = word.toLocaleLowerCase();
    if (!word || seen.has(key)) continue;
    seen.add(key);
    words.push(word);
    if (words.length === JOURNAL_LIMITS.words) break;
  }

  const title = cleanText(first(params.title).slice(0, 400), JOURNAL_LIMITS.titleLength) || undefined;
  return { photo, lang, words, title };
}

export function journalQuery(card: JournalCard): string {
  const query = new URLSearchParams();
  query.set("photo", card.photo.stem);
  query.set("lang", card.lang);
  if (card.words.length > 0) query.set("words", card.words.join(","));
  if (card.title) query.set("title", card.title);
  return query.toString();
}

export function journalTitle(card: JournalCard): string {
  if (card.title) return card.title;
  const count = card.words.length;
  if (count === 0) return `A day in ${LANGUAGE_NAME[card.lang]}`;
  return count === 1 ? "The word I learned today" : `${count} words I learned today`;
}

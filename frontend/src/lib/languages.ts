import type { LanguageOption } from "../data/types";

export function learnableLanguages(languages: LanguageOption[]): LanguageOption[] {
  return languages.filter(language => language.learnable);
}

export function languageName(languages: LanguageOption[], code: string | null | undefined): string | undefined {
  return languages.find(language => language.code.toLowerCase() === code?.toLowerCase())?.englishName;
}

import { languages } from "../config/languages.ts";
import type { PackPracticeLanguage } from "./api.ts";

export function languageDisplayName(code: string): string {
  const known = languages.find(language => language.code === code);
  if (known) return known.name;
  try { return new Intl.DisplayNames(["en"], { type: "language" }).of(code) ?? code; }
  catch { return code; }
}

export function languageFlag(code: string): string {
  return languages.find(language => language.code === code)?.flag ?? "";
}

/** Practice languages come only from pack discovery: a language and level are selectable
 * when a discovered pack offers them. */
export function assertSelectableLanguage(code: string, level: string | undefined, packs: PackPracticeLanguage[]) {
  const pack = packs.find(language => language.code === code);
  if (!pack?.levels.length) throw new Error("Choose an available practice language.");
  if (level && !pack.levels.includes(level as PackPracticeLanguage["levels"][number])) throw new Error("Choose a level available for this language pack.");
}

/** Validate before saving. Keeping the current language (``keep``) never waits on
 * discovery, so name or goal edits still save while its pack is unavailable. */
export async function checkSelectableLanguage(
  code: string, level: string | undefined, loadPacks: () => Promise<PackPracticeLanguage[]>, keep?: string,
) {
  if (keep && code === keep) return;
  assertSelectableLanguage(code, level, await loadPacks());
}

const knownOrder = (code: string) => {
  const index = languages.findIndex(language => language.code === code);
  return index < 0 ? languages.length : index;
};

export function profileLanguageChoices(packs: PackPracticeLanguage[], activeCode = "") {
  const choices = packs
    .filter(pack => pack.levels.length)
    .sort((a, b) => knownOrder(a.code) - knownOrder(b.code) || a.code.localeCompare(b.code))
    .map(pack => ({ code: pack.code, name: languageDisplayName(pack.code), flag: languageFlag(pack.code), levels: pack.levels, experimental: pack.experimental }));
  // Preserve the selected profile if its pack becomes unavailable; do not select a
  // different language implicitly or claim that its lessons remain available.
  if (activeCode && !choices.some(choice => choice.code === activeCode)) {
    choices.push({ code: activeCode, name: languageDisplayName(activeCode), flag: languageFlag(activeCode), levels: [], experimental: false });
  }
  return choices;
}

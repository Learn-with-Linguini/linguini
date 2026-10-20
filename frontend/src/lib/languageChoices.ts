import { languages } from "../config/languages.ts";
import type { PackPracticeLanguage } from "./api.ts";

export function languageDisplayName(code: string): string {
  const known = languages.find(language => language.code === code);
  if (known) return known.name;
  try { return new Intl.DisplayNames(["en"], { type: "language" }).of(code) ?? code; }
  catch { return code; }
}

const isBuiltInLanguage = (code: string) => languages.some(language => language.code === code);

/** Built-in languages keep every level; packs only limit pack-only languages. */
export function assertSelectableLanguage(code: string, level: string | undefined, packs: PackPracticeLanguage[]) {
  if (isBuiltInLanguage(code)) return;
  const pack = packs.find(language => language.code === code);
  if (!pack) throw new Error("Choose an available practice language.");
  if (level && !pack.levels.includes(level as PackPracticeLanguage["levels"][number])) throw new Error("Choose a level available for this language pack.");
}

/** Validate before saving; only pack-only languages wait on pack discovery, so a
 * discovery failure never blocks onboarding or saves for built-in languages. */
export async function checkSelectableLanguage(
  code: string, level: string | undefined, loadPacks: () => Promise<PackPracticeLanguage[]>,
) {
  if (isBuiltInLanguage(code)) return;
  assertSelectableLanguage(code, level, await loadPacks());
}

export function profileLanguageChoices(packs: PackPracticeLanguage[], activeCode = "") {
  const choices = languages.map(language => ({ ...language, levels: [] as PackPracticeLanguage["levels"], experimental: false }));
  for (const pack of packs) {
    if (!pack.levels.length) continue;
    const existing = choices.find(choice => choice.code === pack.code);
    if (existing) {
      existing.levels = pack.levels;
      existing.experimental = pack.experimental;
      continue;
    }
    choices.push({ code: pack.code, name: languageDisplayName(pack.code), flag: "", levels: pack.levels, experimental: pack.experimental });
  }
  // Preserve the selected profile if its pack becomes unavailable; do not select a
  // different language implicitly or claim that its lessons remain available.
  if (activeCode && !choices.some(choice => choice.code === activeCode)) {
    choices.push({ code: activeCode, name: languageDisplayName(activeCode), flag: "", levels: [], experimental: false });
  }
  return choices;
}

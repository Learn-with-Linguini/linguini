import type { LanguageOption } from "../data/types";

export function registryGender(
  languages: readonly LanguageOption[] | null | undefined,
  code: string | null | undefined,
  gender: string | null | undefined,
): string | null {
  if (!code || !gender) return null;
  const language = languages?.find(
    item => item.code.toLowerCase() === code.toLowerCase(),
  );
  return language?.grammar?.grammatical_gender?.includes(gender) ? gender : null;
}

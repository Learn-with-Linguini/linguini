import type { LanguageProfile, LanguageProfilePatch, ProficiencyLevel } from "./api.ts";

export interface OnboardingProfileApi {
  updateLanguageProfile: (id: string, patch: LanguageProfilePatch) => Promise<unknown>;
  createLanguageProfile: (code: string, minutes: number, proficiencyLevel: ProficiencyLevel) => Promise<unknown>;
}

/** Activate the onboarding language's profile with the placed level, creating it when missing. */
export async function saveOnboardingProfile(
  api: OnboardingProfileApi,
  profiles: Pick<LanguageProfile, "id" | "targetLanguageCode" | "sourceLanguageCode">[],
  code: string,
  minutes: number,
  proficiencyLevel: ProficiencyLevel,
) {
  const existing = profiles.find(
    profile => profile.targetLanguageCode === code && profile.sourceLanguageCode === "en",
  );
  if (existing) {
    return api.updateLanguageProfile(existing.id, {
      isActive: true,
      dailyGoalMinutes: minutes,
      proficiencyLevel,
    });
  }
  return api.createLanguageProfile(code, minutes, proficiencyLevel);
}

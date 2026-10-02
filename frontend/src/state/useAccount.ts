import { useCallback, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { languages } from "../config/languages";
import { createLanguageProfile, getCurrentUser, getLanguageProfiles, updateLanguageProfile, updateUser } from "../lib/api";
import type { LanguageProfilePatch, UserPatch } from "../lib/api";
import { friendlyError, queryError, queryKeys } from "../lib/queryKeys";

async function loadAccount(signal?: AbortSignal) {
  const [user, profiles] = await Promise.all([getCurrentUser(signal), getLanguageProfiles(signal)]);
  return { user, profiles };
}

type Account = Awaited<ReturnType<typeof loadAccount>>;

async function saveProfileSettingsWork(code: string, patch: UserPatch, preferences: LanguageProfilePatch) {
  if (!languages.some(language => language.code === code)) throw new Error("Choose a supported language.");
  await updateUser(patch);
  // A previous save may have created the profile before a later request failed.
  const profiles = await getLanguageProfiles();
  const existing = profiles.find(profile => profile.targetLanguageCode === code && profile.sourceLanguageCode === "en");
  const profile = existing ?? await createLanguageProfile(code, preferences.dailyGoalMinutes ?? 10);
  await updateLanguageProfile(profile.id, { ...preferences, isActive: true });
}

export function useAccount() {
  const queryClient = useQueryClient();
  const { data, isPending: loading, error: queryErrorValue } = useQuery({ queryKey: queryKeys.account, queryFn: ({ signal }) => loadAccount(signal) });
  const error = queryError(queryErrorValue);
  const [profileError, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const save = useMutation({
    mutationFn: (action: () => Promise<unknown>) => action(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.account }),
    onError: (reason) => setError(friendlyError(reason)),
    onSettled: () => { inFlight.current = false; },
  });
  const profileSaving = save.isPending;
  const activeProfile = data?.profiles.find((profile) => profile.isActive) ?? null;
  const option = languages.find((language) => language.code === activeProfile?.targetLanguageCode);

  const run = useCallback(async (action: () => Promise<unknown>): Promise<boolean> => {
    if (inFlight.current) return false;
    inFlight.current = true;
    setError(null);
    try { await save.mutateAsync(action); return true; }
    catch { inFlight.current = false; return false; }
  }, [save.mutateAsync]);

  const setLanguage = useCallback((code: string, minutes?: number) => run(async () => {
    const profile = data?.profiles.find((row) => row.targetLanguageCode.toLowerCase() === code && row.sourceLanguageCode === "en");
    if (profile) return updateLanguageProfile(profile.id, { isActive: true, ...(minutes === undefined ? {} : { dailyGoalMinutes: minutes }) });
    return createLanguageProfile(code, minutes);
  }), [data, run]);
  const saveUser = useCallback((patch: UserPatch) => run(() => updateUser(patch)), [run]);
  const saveProfileSettings = useCallback((code: string, patch: UserPatch, preferences: LanguageProfilePatch) => run(
    () => saveProfileSettingsWork(code, patch, preferences)
  ), [run]);
  // Optimistic variant: patches the cached account so callers can navigate immediately; rolls back on error.
  const startProfileSettingsSave = useCallback((code: string, userPatch: UserPatch, preferences: LanguageProfilePatch): boolean => {
    if (inFlight.current) return false;
    inFlight.current = true;
    const snapshot = queryClient.getQueryData<Account>(queryKeys.account);
    queryClient.setQueryData<Account>(queryKeys.account, (current) => {
      if (!current) return current;
      const active = current.profiles.find(profile => profile.isActive) ?? null;
      const languageKnown = !active || active.targetLanguageCode === code
        || current.profiles.some(profile => profile.targetLanguageCode === code && profile.sourceLanguageCode === "en");
      return {
        user: { ...current.user, ...userPatch },
        // A never-before-seen language creates a profile server-side; nothing to patch optimistically.
        profiles: languageKnown && active
          ? current.profiles.map(profile => profile.id === active.id ? { ...profile, ...preferences } : profile)
          : current.profiles,
      };
    });
    setError(null);
    save.mutate(() => saveProfileSettingsWork(code, userPatch, preferences), {
      onError: () => {
        if (snapshot !== undefined) queryClient.setQueryData(queryKeys.account, snapshot);
        void queryClient.invalidateQueries({ queryKey: queryKeys.account });
      },
    });
    return true;
  }, [save.mutate, queryClient]);
  const activateLanguageProfile = useCallback((id: string) => run(async () => {
    if (!data?.profiles.some((profile) => profile.id === id)) throw new Error("Language profile not found.");
    return updateLanguageProfile(id, { isActive: true });
  }), [data, run]);
  const completeOnboarding = useCallback((code: string, minutes: number, patch: UserPatch) => run(async () => {
    await updateUser(patch);
    const profile = data?.profiles.find((row) => row.targetLanguageCode === code && row.sourceLanguageCode === "en");
    if (profile) await updateLanguageProfile(profile.id, { isActive: true, dailyGoalMinutes: minutes });
    else await createLanguageProfile(code, minutes);
  }), [data, run]);
  const saveLanguageProfile = useCallback((patch: LanguageProfilePatch) => run(() => {
    if (!activeProfile) throw new Error("Choose a language first.");
    return updateLanguageProfile(activeProfile.id, patch);
  }), [activeProfile, run]);

  return {
    data, loading, error,
    user: data?.user ?? null,
    activeProfile,
    languageProfiles: data?.profiles ?? [],
    activateLanguageProfile,
    profileSaving, profileError, setLanguage, saveUser, saveProfileSettings, startProfileSettingsSave, saveLanguageProfile, completeOnboarding,
    learner: {
      name: data?.user.displayName ?? "",
      languageCode: activeProfile?.targetLanguageCode ?? "",
      language: option?.name ?? activeProfile?.targetLanguageCode ?? "Choose a language",
      languageFlag: option?.flag ?? "",
      level: activeProfile?.proficiencyLevel ?? "A1",
      dailyMinutes: activeProfile?.dailyGoalMinutes ?? null,
      goal: data?.user.learningGoal ?? "",
      micOn: data?.user.microphoneEnabled ?? false,
      cameraOn: data?.user.cameraEnabled ?? false,
    },
  };
}

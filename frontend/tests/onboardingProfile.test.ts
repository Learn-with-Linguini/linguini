import assert from "node:assert/strict";
import test from "node:test";
import { saveOnboardingProfile } from "../src/lib/onboardingProfile.ts";
import type { OnboardingProfileApi } from "../src/lib/onboardingProfile.ts";

function recordingApi() {
  const calls: Array<{ method: string; args: unknown[] }> = [];
  return {
    calls,
    api: {
      updateLanguageProfile: async (...args: Parameters<OnboardingProfileApi["updateLanguageProfile"]>) => {
        calls.push({ method: "updateLanguageProfile", args });
      },
      createLanguageProfile: async (...args: Parameters<OnboardingProfileApi["createLanguageProfile"]>) => {
        calls.push({ method: "createLanguageProfile", args });
      },
    },
  };
}

test("onboarding updates an existing English-source language profile", async () => {
  const { api, calls } = recordingApi();

  await saveOnboardingProfile(api, [
    { id: "es-profile", targetLanguageCode: "es", sourceLanguageCode: "en" },
  ], "es", 20, "A2");

  assert.deepEqual(calls, [{
    method: "updateLanguageProfile",
    args: ["es-profile", { isActive: true, dailyGoalMinutes: 20, proficiencyLevel: "A2" }],
  }]);
});

test("onboarding creates a profile when the language is missing", async () => {
  const { api, calls } = recordingApi();

  await saveOnboardingProfile(api, [], "es", 10, "A0");

  assert.deepEqual(calls, [{
    method: "createLanguageProfile",
    args: ["es", 10, "A0"],
  }]);
});

test("onboarding does not update a profile with a different source language", async () => {
  const { api, calls } = recordingApi();

  await saveOnboardingProfile(api, [
    { id: "es-fr-profile", targetLanguageCode: "es", sourceLanguageCode: "fr" },
  ], "es", 10, "A1");

  assert.deepEqual(calls, [{
    method: "createLanguageProfile",
    args: ["es", 10, "A1"],
  }]);
});

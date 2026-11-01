import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { OnboardingSteps } from "../components/OnboardingSteps";
import { trackAction } from "../lib/analytics.ts";
import { readOnboardingProgress, savedPastaAvatar, type OnboardingDraft } from "../lib/onboardingDraft";
import { AppStateProvider } from "../state/AppState";
import { useAppState } from "../state/useAppState";

const defaultDraft: OnboardingDraft = {
  // The language step starts on the first language pack discovery offers.
  name: "", languageCode: "", goal: "", minutes: 10,
  microphoneEnabled: false, cameraEnabled: false, avatar: "farfalle", proficiencyLevel: "A0",
};

/** Collect preferences once, after a learner has created their account. */
export function Onboarding() {
  const navigate = useNavigate();
  const location = useLocation();
  const { learner, user, completeOnboarding, profileSaving, profileError } = useAppState();
  const [completionStarted, setCompletionStarted] = useState(false);
  const navigationState = location.state as { from?: string; languageChangeCode?: string } | null;
  const destination = navigationState?.from ?? "/home";
  // Route state is intentionally ephemeral: a browser restore or reload drops it.
  // The in-progress draft is the durable source of truth for a language reset.
  const savedProgress = user ? readOnboardingProgress(user.id) : null;
  // Which languages may be chosen is checked against pack discovery when the setup saves.
  const resumedLanguageCode = savedProgress?.restartingForLanguage
    ? savedProgress.draft.languageCode || undefined : undefined;
  const languageChangeCode = navigationState?.languageChangeCode ?? resumedLanguageCode;
  const restartingForLanguage = Boolean(languageChangeCode);
  if (user?.onboardingCompleted && !completionStarted && !restartingForLanguage) return <Navigate to={destination} replace />;
  const initial: OnboardingDraft = {
    name: learner.name,
    languageCode: restartingForLanguage ? languageChangeCode! : learner.languageCode || defaultDraft.languageCode,
    goal: learner.goal || defaultDraft.goal,
    minutes: learner.dailyMinutes ?? 10,
    microphoneEnabled: learner.micOn,
    cameraEnabled: learner.cameraOn,
    avatar: savedPastaAvatar() ?? user?.avatar ?? "farfalle",
    proficiencyLevel: "A0",
  };
  return <OnboardingSteps initial={initial} userId={user?.id ?? "pending"} restartingForLanguage={restartingForLanguage} saving={profileSaving} error={profileError} onFinish={() => navigate(destination)} onComplete={async values => {
    setCompletionStarted(true);
    const saved = await completeOnboarding(values.languageCode, values.minutes, values.proficiencyLevel ?? "A0", {
      displayName: values.name || learner.name,
      learningGoal: values.goal,
      microphoneEnabled: values.microphoneEnabled,
      cameraEnabled: values.cameraEnabled,
      avatar: values.avatar,
      onboardingCompleted: true,
    });
    if (saved) {
      trackAction(restartingForLanguage ? "language_onboarding_completed" : "onboarding_completed", {
        language: values.languageCode,
        minutes: values.minutes,
        level: values.proficiencyLevel ?? "A0",
      });
      localStorage.setItem("linguini-avatar", values.avatar);
    } else {
      setCompletionStarted(false);
    }
    return saved;
  }} />;
}

/** Finishing onboarding activates the chosen language; remounting here would restart the flow. */
export function OnboardingPage() {
  return <AppStateProvider resetOnLanguageChange={false}><Onboarding /></AppStateProvider>;
}

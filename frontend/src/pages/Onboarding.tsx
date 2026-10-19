import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { OnboardingSteps } from "../components/OnboardingSteps";
import { trackAction } from "../lib/analytics.ts";
import { savedPastaAvatar, type OnboardingDraft } from "../lib/onboardingDraft";
import { languages } from "../config/languages";
import { useAppState } from "../state/useAppState";

const defaultDraft: OnboardingDraft = {
  name: "", languageCode: languages[0].code, goal: "", minutes: 10,
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
  const languageChangeCode = navigationState?.languageChangeCode;
  const restartingForLanguage = Boolean(languageChangeCode && languages.some(language => language.code === languageChangeCode));
  if (user?.onboardingCompleted && !completionStarted && !restartingForLanguage) return <Navigate to={destination} replace />;
  const initial: OnboardingDraft = {
    name: learner.name,
    languageCode: restartingForLanguage ? languageChangeCode! : learner.languageCode || languages[0].code,
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

import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { OnboardingSteps } from "../components/OnboardingSteps";
import { ErrorNotice } from "../components/ErrorState";
import { InlineLoader } from "../components/LoadingScreen";
import type { OnboardingDraft } from "../lib/onboardingDraft";
import { learnableLanguages } from "../lib/languages";
import { queryError } from "../lib/queryKeys";
import { useAppState } from "../state/useAppState";
import { useLanguages } from "../state/useLanguages";

/** Collect preferences once, after a learner has created their account. */
export function Onboarding() {
  const navigate = useNavigate();
  const location = useLocation();
  const { learner, user, completeOnboarding, profileSaving, profileError } = useAppState();
  const languagesQuery = useLanguages();
  const languages = learnableLanguages(languagesQuery.data ?? []);
  const [completionStarted, setCompletionStarted] = useState(false);
  const destination = (location.state as { from?: string } | null)?.from ?? "/home";
  if (user?.onboardingCompleted && !completionStarted) return <Navigate to={destination} replace />;
  if (languagesQuery.isPending) return <InlineLoader compact label="Loading languages…" />;
  if (languagesQuery.isError) {
    return (
      <ErrorNotice
        compact
        message={queryError(languagesQuery.error) ?? "We couldn't load languages. Please try again."}
        retry={() => void languagesQuery.refetch()}
        retryLabel="Retry"
      />
    );
  }
  if (languages.length === 0) {
    return (
      <ErrorNotice
        compact
        message="No learning languages are available right now."
        retry={() => void languagesQuery.refetch()}
        retryLabel="Retry"
      />
    );
  }
  const selectedLanguage = languages.find(option =>
    option.code.toLowerCase() === learner.languageCode.toLowerCase()
  ) ?? languages[0];
  const initial: OnboardingDraft = {
    name: learner.name,
    languageCode: selectedLanguage.code,
    goal: learner.goal || "",
    minutes: learner.dailyMinutes ?? 10,
    microphoneEnabled: learner.micOn,
    cameraEnabled: learner.cameraOn,
    avatar: localStorage.getItem("linguini-avatar") ?? "farfalle",
    proficiencyLevel: "A0",
  };
  return <OnboardingSteps initial={initial} saving={profileSaving} error={profileError} onFinish={() => navigate(destination)} onComplete={async values => {
    setCompletionStarted(true);
    const saved = await completeOnboarding(values.languageCode, values.minutes, values.proficiencyLevel ?? "A0", {
      displayName: values.name || learner.name,
      learningGoal: values.goal,
      microphoneEnabled: values.microphoneEnabled,
      cameraEnabled: values.cameraEnabled,
      onboardingCompleted: true,
    });
    if (saved) {
      localStorage.setItem("linguini-avatar", values.avatar);
    } else {
      setCompletionStarted(false);
    }
    return saved;
  }} />;
}

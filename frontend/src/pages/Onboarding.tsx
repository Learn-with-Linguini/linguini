import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { OnboardingSteps } from "../components/OnboardingSteps";
import type { OnboardingDraft } from "../lib/onboardingDraft";
import { languages } from "../config/languages";
import { useAppState } from "../state/useAppState";

const defaultDraft: OnboardingDraft = {
  name: "", languageCode: languages[0].code, goal: "", minutes: 10,
  microphoneEnabled: false, cameraEnabled: false, avatar: "farfalle",
};

/** Collect preferences once, after a learner has created their account. */
export function Onboarding() {
  const navigate = useNavigate();
  const location = useLocation();
  const { learner, user, completeOnboarding, profileSaving, profileError } = useAppState();
  const destination = (location.state as { from?: string } | null)?.from ?? "/home";
  if (user?.onboardingCompleted) return <Navigate to={destination} replace />;
  const initial: OnboardingDraft = {
    name: learner.name,
    languageCode: learner.languageCode || languages[0].code,
    goal: learner.goal || defaultDraft.goal,
    minutes: learner.dailyMinutes ?? 10,
    microphoneEnabled: learner.micOn,
    cameraEnabled: learner.cameraOn,
    avatar: localStorage.getItem("linguini-avatar") ?? "farfalle",
  };
  return <OnboardingSteps initial={initial} saving={profileSaving} error={profileError} onComplete={async values => {
    const saved = await completeOnboarding(values.languageCode, values.minutes, {
      displayName: values.name || learner.name,
      learningGoal: values.goal,
      microphoneEnabled: values.microphoneEnabled,
      cameraEnabled: values.cameraEnabled,
      onboardingCompleted: true,
    });
    if (saved) {
      localStorage.setItem("linguini-avatar", values.avatar);
      navigate(destination);
    }
  }} />;
}

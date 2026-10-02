export type OnboardingDraft = {
  name: string;
  languageCode: string;
  goal: string;
  minutes: number;
  microphoneEnabled: boolean;
  cameraEnabled: boolean;
  avatar: string;
};

const storageKey = "linguini-onboarding-draft";

// Goals are multi-select in the UI but persist as one comma-joined
// `learningGoal` string, which the backend already accepts.
const goalSeparator = ", ";

export function parseGoals(goal: string): string[] {
  return goal.split(",").map(value => value.trim()).filter(Boolean);
}

export function joinGoals(goals: string[]): string {
  return goals.join(goalSeparator);
}

export function readOnboardingDraft(): OnboardingDraft | null {
  try {
    // Email confirmation opens a new tab, so this must survive beyond one tab's session.
    const value = localStorage.getItem(storageKey);
    if (!value) return null;
    const parsed = JSON.parse(value) as Partial<OnboardingDraft>;
    if (typeof parsed.name !== "string" || typeof parsed.languageCode !== "string" || typeof parsed.goal !== "string" || typeof parsed.minutes !== "number") return null;
    return { name: parsed.name, languageCode: parsed.languageCode, goal: parsed.goal, minutes: parsed.minutes, microphoneEnabled: Boolean(parsed.microphoneEnabled), cameraEnabled: Boolean(parsed.cameraEnabled), avatar: typeof parsed.avatar === "string" ? parsed.avatar : "farfalle" };
  } catch { return null; }
}

export function saveOnboardingDraft(draft: OnboardingDraft): void { localStorage.setItem(storageKey, JSON.stringify(draft)); }
export function clearOnboardingDraft(): void { localStorage.removeItem(storageKey); }

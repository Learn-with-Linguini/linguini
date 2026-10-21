import type { PastaAvatar } from "../data/types";

export const PASTA_AVATARS = ["farfalle", "fusilli", "penne", "macaroni"] as const;

export type OnboardingDraft = {
  name: string;
  languageCode: string;
  goal: string;
  minutes: number;
  microphoneEnabled: boolean;
  cameraEnabled: boolean;
  avatar: PastaAvatar;
  proficiencyLevel?: "A0" | "A1" | "A2";
};

export type OnboardingStage = "profile" | "language" | "experience" | "goals" | "permissions";

export type OnboardingProgress = {
  draft: OnboardingDraft;
  stage: OnboardingStage;
  restartingForLanguage: boolean;
};

const storageKey = (userId: string) => `linguini-onboarding-draft-${userId}`;

// Goals are multi-select in the UI but persist as one comma-joined
// `learningGoal` string, which the backend already accepts.
const goalSeparator = ", ";

export function parseGoals(goal: string): string[] {
  return goal.split(",").map(value => value.trim()).filter(Boolean);
}

export function joinGoals(goals: string[]): string {
  return goals.join(goalSeparator);
}

function parseDraft(value: string | null): OnboardingDraft | null {
  if (!value) return null;
  const parsed = JSON.parse(value) as Partial<OnboardingDraft>;
  if (typeof parsed.name !== "string" || typeof parsed.languageCode !== "string" || typeof parsed.goal !== "string" || typeof parsed.minutes !== "number") return null;
  const proficiencyLevel = ["A0", "A1", "A2"].includes(parsed.proficiencyLevel ?? "") ? parsed.proficiencyLevel as "A0" | "A1" | "A2" : undefined;
  const avatar = PASTA_AVATARS.includes(parsed.avatar as PastaAvatar) ? parsed.avatar as PastaAvatar : "farfalle";
  return { name: parsed.name, languageCode: parsed.languageCode, goal: parsed.goal, minutes: parsed.minutes, microphoneEnabled: Boolean(parsed.microphoneEnabled), cameraEnabled: Boolean(parsed.cameraEnabled), avatar, proficiencyLevel };
}

export function savedPastaAvatar(): PastaAvatar | null {
  const avatar = localStorage.getItem("linguini-avatar");
  return PASTA_AVATARS.includes(avatar as PastaAvatar) ? avatar as PastaAvatar : null;
}

export function readOnboardingProgress(userId: string): OnboardingProgress | null {
  try {
    // Email confirmation opens a new tab, so this must survive beyond one tab's session.
    const value = localStorage.getItem(storageKey(userId));
    if (!value) return null;
    const parsed = JSON.parse(value) as Partial<OnboardingProgress>;
    const draft = parseDraft(JSON.stringify(parsed.draft));
    const stages: OnboardingStage[] = ["profile", "language", "experience", "goals", "permissions"];
    if (!draft || !stages.includes(parsed.stage as OnboardingStage)) return null;
    return { draft, stage: parsed.stage as OnboardingStage, restartingForLanguage: Boolean(parsed.restartingForLanguage) };
  } catch { return null; }
}

export function saveOnboardingProgress(userId: string, progress: OnboardingProgress): void {
  try { localStorage.setItem(storageKey(userId), JSON.stringify(progress)); } catch { /* storage can be unavailable */ }
}

export function clearOnboardingProgress(userId: string): void {
  try { localStorage.removeItem(storageKey(userId)); } catch { /* storage can be unavailable */ }
}

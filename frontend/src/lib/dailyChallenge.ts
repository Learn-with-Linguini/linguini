import { request } from "./api.ts";

export interface DailyChallengeWord { label: string; count: number; foundByYou: boolean }
export interface DailyChallengeResult {
  challengeDay: string; sceneTitle: string; rank: number; participantCount: number; basil: number;
}
export interface DailyChallenge {
  challengeDay: string; sceneKey: string; sceneTitle: string; scenePhrase: string; dayEndsAt: string;
  status: "notStarted" | "inProgress" | "completed"; sessionId: string | null;
  participantCount: number; joinedCount: number; words: DailyChallengeWord[]; yourWordCount: number;
  lastResult: DailyChallengeResult | null;
}

export const dailyChallengeKey = (userId: string) => ["gamification", userId, "daily-challenge"] as const;
export const getDailyChallenge = (signal?: AbortSignal) => request<DailyChallenge>("/api/v1/me/daily-challenge", signal);

/** Matches the backend rank bonus in `daily_challenges.py`. */
export const DAILY_CHALLENGE_PRIZES = [
  { place: "1st", basil: 50 }, { place: "2nd", basil: 30 }, { place: "3rd", basil: 20 }, { place: "Top 10", basil: 10 },
] as const;
export const DAILY_CHALLENGE_FINISHER_BASIL = 5;
const DAY_MS = 24 * 60 * 60 * 1000;
/** The final stretch of the day, when the countdown turns urgent. */
export const FINAL_HOURS_MS = 3 * 60 * 60 * 1000;

export function timeLeft(dayEndsAt: string, now: number) {
  const remaining = Math.max(0, new Date(dayEndsAt).getTime() - now);
  return { remaining, fraction: Math.min(1, remaining / DAY_MS), urgent: remaining > 0 && remaining <= FINAL_HOURS_MS };
}

export function countdownText(remaining: number): string {
  if (remaining <= 0) return "Ended";
  if (remaining < 60_000) return "Ends in under a minute";
  const minutes = Math.floor(remaining / 60_000);
  const hours = Math.floor(minutes / 60);
  return hours ? `Ends in ${hours}h ${String(minutes % 60).padStart(2, "0")}m` : `Ends in ${minutes}m`;
}

/** Splits "at the library" so the place itself can be emphasised. */
export function splitScenePhrase(phrase: string, title: string): [string, string] {
  const at = phrase.toLowerCase().lastIndexOf(title.toLowerCase());
  return at > 0 ? [phrase.slice(0, at), phrase.slice(at)] : [phrase, ""];
}

export function wordShare(word: DailyChallengeWord, words: DailyChallengeWord[]): number {
  const most = Math.max(0, ...words.map(item => item.count));
  return most ? Math.round((word.count / most) * 100) : 0;
}

export function lastResultText(result: DailyChallengeResult | null): string | null {
  if (!result) return null;
  return `${result.sceneTitle} challenge: you placed #${result.rank} of ${result.participantCount} and earned ${result.basil} Basil.`;
}

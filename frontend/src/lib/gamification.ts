import { request } from "./api.ts";
import type { PastaAvatar } from "../data/types";

export type BadgeLevel = "Taster" | "Cook" | "Chef" | "Head Chef" | "Master";
export interface MissionBadge {
  missionId: string; name: string; skill: string; available: boolean; practiceLevel: string;
  badgeLevel: BadgeLevel | null; successfulBatches: number; distinctPhotos: number; requirements: string[];
}
export interface MissionBatch {
  missionId: string; practiceLevel: string; contentVersion: number; percent: number;
  status: "inProgress" | "review" | "ready"; assessedQuestions: number; correctQuestions: number;
  totalQuestions: number; independentCorrect: number; requirements: string[];
}
export interface GamificationSummary {
  policyVersion: string;
  basil: { today: number; weekly: number; lifetime: number; balance: number; competitionDay: string; dayEndsAt: string };
  missions: MissionBadge[];
}
export interface ChefStandings {
  competitionDay: string; dayEndsAt: string; todayBasil: number;
  personalBest: number; currentRank: number | null; basilToNextRank: number | null;
  top: { rank: number; displayName: string; basil: number; avatar: PastaAvatar }[];
}
export const gamificationKeys = {
  account: (userId: string) => ["gamification", userId] as const,
  summary: (userId: string, profileId: string) => ["gamification", userId, "summary", profileId] as const,
  mission: (userId: string, sessionId: string) => ["gamification", userId, "mission", sessionId] as const,
  chefs: (userId: string) => ["gamification", userId, "chefs"] as const,
};
export const getGamification = (profileId: string, signal?: AbortSignal) =>
  request<GamificationSummary>(`/api/v1/me/gamification?languageProfileId=${encodeURIComponent(profileId)}`, signal);
export const getMissionProgress = (sessionId: string, signal?: AbortSignal) =>
  request<MissionBatch[]>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/mission-progress`, signal);
export const getChefStandings = (signal?: AbortSignal) => request<ChefStandings>("/api/v1/me/chef-of-the-day", signal);
export const basilEarnedText = (amount: number | undefined) => amount && amount > 0 ? `+${amount} Basil earned` : null;

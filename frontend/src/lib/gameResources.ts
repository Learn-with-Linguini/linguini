import { request, write } from "./api.ts";

export type Appearance = "default" | "herb" | "pasta";
export interface GameResourceSnapshot {
  sauce: { remaining: number; capacity: number; refillsAt: string };
  basilLeaves: number;
  appearance: Appearance;
  ownedAppearances: Appearance[];
}

export const gameResourceKeys = (userId: string) => ["game-resources", userId] as const;
export const getGameResources = (signal?: AbortSignal) => request<GameResourceSnapshot>("/api/v1/me/game-resources", signal);
export const selectAppearance = (appearance: Appearance, commandId: string) =>
  write<GameResourceSnapshot>("/api/v1/me/game-resources/appearance", "POST", { appearance, commandId });

export function saucePercent(sauce: GameResourceSnapshot["sauce"]): number {
  return sauce.capacity > 0 ? Math.max(0, Math.min(100, sauce.remaining / sauce.capacity * 100)) : 0;
}

/** Keep the first request identity until its outcome is known, including lost responses. */
export function appearanceCommand(appearance: Appearance, pending: { appearance: Appearance; commandId: string } | null,
  newId: () => string = () => crypto.randomUUID()) {
  return pending ?? { appearance, commandId: newId() };
}

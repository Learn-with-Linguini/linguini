import type { MissionShortfall, SceneShortfall, ShortfallKind } from "./api";
import type { SceneReviewPanel } from "./sceneReview";

export const SHORTFALL_KINDS: ShortfallKind[] = ["objects", "counts", "attributes", "relations"];

/** What each missing kind asks for, and the review panel where the learner adds it. */
export const SHORTFALL_ACTIONS: Record<ShortfallKind, { title: string; hint: string; action: string; panel: SceneReviewPanel }> = {
  objects: {
    title: "More objects",
    hint: "Mark another object you can see in the photo.",
    action: "Add an object",
    panel: "objects",
  },
  counts: {
    title: "A count",
    hint: "Mark each of 2 or 3 matching objects, such as two cups.",
    action: "Add to a count",
    panel: "objects",
  },
  attributes: {
    title: "Adjectives",
    hint: "Give an object a colour, size, shape, material, pattern or state you can see.",
    action: "Add adjectives",
    panel: "attributes",
  },
  relations: {
    title: "Connections",
    hint: "Say where one object is, such as a cup on a table.",
    action: "Add a connection",
    panel: "relations",
  },
};

function isKind(value: unknown): value is ShortfallKind {
  return typeof value === "string" && (SHORTFALL_KINDS as string[]).includes(value);
}

function kinds(value: unknown): ShortfallKind[] {
  return Array.isArray(value) ? SHORTFALL_KINDS.filter(kind => value.some(item => item === kind && isKind(item))) : [];
}

/** A validated shortfall from an API payload, or null when it isn't one. */
export function parseShortfall(value: unknown): SceneShortfall | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as { missing?: unknown; missions?: unknown };
  const missing = kinds(raw.missing);
  if (!missing.length) return null;
  const missions: MissionShortfall[] = Array.isArray(raw.missions)
    ? raw.missions.flatMap(item => {
      if (!item || typeof item !== "object") return [];
      const row = item as Record<string, unknown>;
      if (typeof row.missionId !== "string" || typeof row.title !== "string") return [];
      return [{
        missionId: row.missionId,
        title: row.title,
        missing: kinds(row.missing),
        reasons: Array.isArray(row.reasons) ? row.reasons.filter((reason): reason is string => typeof reason === "string") : [],
      }];
    })
    : [];
  return { missing, missions };
}

/** The shortfall a rejected review reported, or null for any other error. */
export function shortfallFromError(error: unknown): SceneShortfall | null {
  if (!error || typeof error !== "object") return null;
  const apiError = error as { code?: unknown; detail?: unknown };
  return apiError.code === "insufficient_scene" ? parseShortfall(apiError.detail) : null;
}

/** Missions that need only what the learner is asked to add, nearest first. */
export function closestMissions(shortfall: SceneShortfall): MissionShortfall[] {
  return shortfall.missions.filter(mission => mission.missing.length > 0
    && mission.missing.every(kind => shortfall.missing.includes(kind)));
}

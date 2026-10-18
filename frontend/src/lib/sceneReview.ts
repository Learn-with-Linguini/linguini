export type SceneReviewPanel = "objects" | "attributes" | "relations" | "counts" | "choices";
type DetailPanel = "attributes" | "relations";

// Mirrors the fact requirements in the mission definitions.
const MISSION_DETAIL_PANELS: Record<string, Record<string, DetailPanel[]>> = {
  M01: { A0: [], A1: ["attributes", "relations"], A2: ["attributes", "relations"] },
  M02: { A0: [], A1: ["relations"], A2: ["attributes", "relations"] },
  M03: { A0: [], A1: [], A2: [] },
  M04: { A0: [], A1: [], A2: ["attributes", "relations"] },
  M05: { A0: [], A1: [] },
  M06: { A2: [] },
  M13: { A0: [] },
};

export function initiallyHiddenObjectIds(
  objectIds: string[],
  suggestedObjectIds: string[] | undefined,
): string[] {
  const focused = new Set(suggestedObjectIds ?? []);
  return focused.size ? objectIds.filter(id => !focused.has(id)) : [];
}

export function sceneReviewPanels(
  missionPlan: Array<{ missionId?: unknown; practiceLevel?: unknown }> | undefined,
  hasRepeatedObjects = false,
): SceneReviewPanel[] {
  if (!missionPlan?.length) return ["objects", "attributes", "relations", "counts"];
  const panels = new Set<SceneReviewPanel>(["objects"]);
  for (const item of missionPlan) {
    const missionId = String(item.missionId);
    const levels = MISSION_DETAIL_PANELS[missionId];
    if (!levels) continue;
    const level = String(item.practiceLevel);
    const detailPanels = levels[level] ?? Object.values(levels).flat();
    detailPanels.forEach(panel => panels.add(panel));
    if (level === "A0" && ["M04", "M05"].includes(missionId)) panels.add("choices");
  }
  if (missionPlan.some(item => String(item.missionId) === "M03") || hasRepeatedObjects) panels.add("counts");
  return (["objects", "attributes", "relations", "counts", "choices"] as const)
    .filter(panel => panels.has(panel));
}

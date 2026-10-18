export type SceneReviewPanel = "objects" | "attributes" | "relations" | "choices";
type DetailPanel = "attributes" | "relations";

const MISSION_DETAIL_PANELS: Record<string, Record<string, DetailPanel[]>> = {
  M01: { default: ["attributes"], A0: [], A1: ["attributes", "relations"], A2: ["attributes", "relations"] },
  M02: { default: ["relations"], A0: [], A1: ["relations"], A2: ["attributes", "relations"] },
  M03: { default: [], A0: [], A1: [], A2: [] },
  M04: { default: [], A0: [], A1: [], A2: ["attributes", "relations"] },
  M05: { default: [], A0: [], A1: [] },
  M06: { default: [], A2: [] },
  M13: { default: [], A0: [] },
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
): SceneReviewPanel[] {
  if (!missionPlan?.length) return ["objects", "attributes", "relations"];
  const panels = new Set<SceneReviewPanel>(["objects"]);
  for (const item of missionPlan) {
    const missionId = String(item.missionId);
    const levels = MISSION_DETAIL_PANELS[missionId];
    if (!levels) continue;
    const level = String(item.practiceLevel);
    const detailPanels = levels[level] ?? levels.default;
    detailPanels.forEach(panel => panels.add(panel));
    if (level === "A0" && ["M04", "M05"].includes(missionId)) panels.add("choices");
  }
  return (["objects", "attributes", "relations", "choices"] as const)
    .filter(panel => panels.has(panel));
}

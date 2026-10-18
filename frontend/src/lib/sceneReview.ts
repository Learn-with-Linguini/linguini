export type SceneReviewPanel = "objects" | "attributes" | "relations" | "choices";

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
  const missions = new Set((missionPlan ?? []).map(item => String(item.missionId)));
  if (!missions.size) return ["objects", "attributes", "relations"];
  return [
    "objects",
    ...(missions.has("M01") ? ["attributes" as const] : []),
    ...(missions.has("M02") ? ["relations" as const] : []),
    ...((missionPlan ?? []).some(item =>
      item.practiceLevel === "A0" && ["M04", "M05"].includes(String(item.missionId)),
    ) ? ["choices" as const] : []),
  ];
}

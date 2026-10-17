export type SceneReviewPanel = "objects" | "attributes" | "relations" | "counts";

export function initiallyHiddenObjectIds(
  objectIds: string[],
  suggestedObjectIds: string[] | undefined,
): string[] {
  const focused = new Set(suggestedObjectIds ?? []);
  return focused.size ? objectIds.filter(id => !focused.has(id)) : [];
}

export function sceneReviewPanels(
  missionPlan: Array<{ missionId?: unknown }> | undefined,
  hasRepeatedObjects = false,
): SceneReviewPanel[] {
  const missions = new Set((missionPlan ?? []).map(item => String(item.missionId)));
  if (!missions.size) return ["objects", "attributes", "relations", "counts"];
  return [
    "objects",
    ...(missions.has("M01") ? ["attributes" as const] : []),
    ...(missions.has("M02") ? ["relations" as const] : []),
    ...(missions.has("M03") || hasRepeatedObjects ? ["counts" as const] : []),
  ];
}

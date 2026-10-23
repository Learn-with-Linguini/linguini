export type SceneReviewPanel = "objects" | "attributes" | "relations";

export function initiallyHiddenObjectIds(
  objectIds: string[],
  suggestedObjectIds: string[] | undefined,
): string[] {
  const focused = new Set(suggestedObjectIds ?? []);
  return focused.size ? objectIds.filter(id => !focused.has(id)) : [];
}

export function initialReviewMarkers(
  objectIds: string[],
  suggestedObjectIds: string[] | undefined,
): Record<string, number> {
  const suggested = new Set(suggestedObjectIds ?? []);
  const visible = suggested.size ? objectIds.filter(id => suggested.has(id)) : objectIds;
  return Object.fromEntries(visible.map((id, index) => [id, index + 1]));
}

export function sceneReviewPanels(): SceneReviewPanel[] {
  // Learners can add their own facts, even when analysis did not find one.
  return ["objects", "attributes", "relations"];
}

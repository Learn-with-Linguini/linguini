export type SceneReviewPanel = "objects" | "attributes" | "relations";

export function initiallyHiddenObjectIds(
  objectIds: string[],
  suggestedObjectIds: string[] | undefined,
): string[] {
  const focused = new Set(suggestedObjectIds ?? []);
  return focused.size ? objectIds.filter(id => !focused.has(id)) : [];
}

export function sceneReviewPanels(): SceneReviewPanel[] {
  // Learners can add their own facts, even when analysis did not find one.
  return ["objects", "attributes", "relations"];
}

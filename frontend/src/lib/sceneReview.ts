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
  return sceneMarkerNumbers(visible);
}

/** Keep saved identities; give missing or repeated marker values an unused number. */
export function sceneMarkerNumbers(
  objectIds: string[],
  saved: Record<string, number> = {},
): Record<string, number> {
  const numbers: Record<string, number> = {};
  const used = new Set<number>();
  for (const id of objectIds) {
    const number = saved[id];
    if (Number.isSafeInteger(number) && number > 0 && !used.has(number)) {
      numbers[id] = number;
      used.add(number);
    }
  }
  let next = 1;
  for (const id of objectIds) {
    if (numbers[id] !== undefined) continue;
    while (used.has(next)) next += 1;
    numbers[id] = next;
    used.add(next);
  }
  return numbers;
}

export function sceneReviewPanels(): SceneReviewPanel[] {
  // Learners can add their own facts, even when analysis did not find one.
  return ["objects", "attributes", "relations"];
}

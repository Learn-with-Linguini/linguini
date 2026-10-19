export type PlacementDifficulty = "A0" | "A1" | "A2";

export function nextPlacementDifficulty(
  questionIndex: number,
  currentDifficulty: PlacementDifficulty,
  correct: boolean,
): PlacementDifficulty {
  if (questionIndex === 0) return correct ? "A2" : "A0";
  if (currentDifficulty === "A2") return correct ? "A2" : "A1";
  return correct ? "A1" : "A0";
}

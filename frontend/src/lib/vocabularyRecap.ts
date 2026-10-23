export type VocabularyRecapStep = { kind: "quiz" | "typing"; index: number };

/** Alternate recognition and recall, avoiding immediate recall of the word just shown. */
export function vocabularyRecapSteps(questionCount: number, wordCount: number): VocabularyRecapStep[] {
  const steps: VocabularyRecapStep[] = [];
  for (let index = 0; index < Math.max(questionCount, wordCount); index += 1) {
    if (index < questionCount) steps.push({ kind: "quiz", index });
    if (index < wordCount) steps.push({ kind: "typing", index: (index + 1) % wordCount });
  }
  return steps;
}

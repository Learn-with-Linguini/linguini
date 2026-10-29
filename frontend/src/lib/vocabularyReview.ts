import type { VocabularyLearningWord } from "./api";

export const VOCABULARY_SECTIONS = {
  object: "Objects",
  attribute: "Adjectives",
  relationship: "Relations",
} as const;

/** Group only the teaching cards; saved quizzes and typing retain their original order. */
export function vocabularyReviewWords(words: VocabularyLearningWord[]) {
  // Older saved noun cards predate the explicit termType field.
  const normalized = words.map(word => word.termType ? word : { ...word, termType: "object" as const });
  return (["object", "attribute", "relationship"] as const)
    .flatMap(type => normalized.filter(word => word.termType === type));
}

export function wordMatchesMarker(word: VocabularyLearningWord, objectId: string) {
  return word.termType === "object" && (word.sceneObjectId === objectId
    || Boolean(word.relatedSceneObjectIds?.includes(objectId)));
}

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

/** Pair only explicitly linked adjectives with an object; keep unlinked words visible. */
export function vocabularyReviewGroups(words: VocabularyLearningWord[]) {
  const ordered = vocabularyReviewWords(words);
  const attributes = ordered.filter(word => word.termType === "attribute");
  const paired = new Set<VocabularyLearningWord>();
  const objects = ordered.filter(word => word.termType === "object").map(object => {
    const adjectives = attributes.filter(attribute => {
      const ids = [attribute.sceneObjectId, ...(attribute.relatedSceneObjectIds ?? [])];
      return ids.some(id => id && wordMatchesMarker(object, id));
    });
    adjectives.forEach(word => paired.add(word));
    return [object, ...adjectives];
  });
  return [
    ...objects,
    ...attributes.filter(word => !paired.has(word)).map(word => [word]),
    ...ordered.filter(word => word.termType === "relationship").map(word => [word]),
  ];
}

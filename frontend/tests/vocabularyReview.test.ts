import assert from "node:assert/strict";
import test from "node:test";
import type { VocabularyLearningWord } from "../src/lib/api.ts";
import { vocabularyReviewGroups } from "../src/lib/vocabularyReview.ts";

function word(termType: VocabularyLearningWord["termType"], targetText: string, sceneObjectId: string | null, relatedSceneObjectIds: string[] = []): VocabularyLearningWord {
  return { termType, targetText, sceneObjectId, relatedSceneObjectIds, learningKey: targetText,
    translation: targetText, vocabularyItemId: null, partOfSpeech: "noun", gender: null,
    pluralForm: null, phoneticText: null, pronunciationAudioAssetId: null, exampleSentence: null };
}

test("objects pair with their own adjectives without dropping unlinked words or relations", () => {
  const words = [word("attribute", "green", "apple"), word("object", "apple", "apple"),
    word("object", "table", "table"), word("attribute", "wooden", "table"),
    word("attribute", "small", "apple"), word("attribute", "unknown", null),
    word("relationship", "on", "apple", ["table"])];
  assert.deepEqual(vocabularyReviewGroups(words).map(group => group.map(item => item.targetText)),
    [["apple", "green", "small"], ["table", "wooden"], ["unknown"], ["on"]]);
  assert.equal(words[0].targetText, "green", "Saved quiz and typing order must stay unchanged");
});

test("shared adjectives pair with each explicitly linked object and repeated instances", () => {
  const words = [word("object", "apple", "apple1", ["apple2"]), word("object", "cup", "cup"),
    word("attribute", "green", null, ["apple2", "cup"])];
  assert.deepEqual(vocabularyReviewGroups(words).map(group => group.map(item => item.targetText)),
    [["apple", "green"], ["cup", "green"]]);
});

test("older noun cards remain visible when termType is absent", () => {
  const old = word("object", "apple", "apple");
  delete (old as Partial<VocabularyLearningWord>).termType;
  assert.equal(vocabularyReviewGroups([old])[0][0].termType, "object");
});

import { GENDER_ARTICLES } from "../data/types.ts";
import type { Gender, Scene } from "../data/types";
import type { PracticeDetail } from "./api";

/** Join accepted objects to catalog vocabulary by ID; labels are only a fallback. */
export function practiceScene(detail: PracticeDetail, imageUrl: string, language: string): Scene {
  return {
      sessionId: detail.session.id, isUploaded: detail.mediaAsset.source !== "preloaded", id: detail.sceneId ?? detail.session.id,
      mediaAssetId: detail.mediaAsset.id, imageUrl, title: detail.title,
      languageCode: detail.vocabulary[0]?.languageCode ?? "", language,
      blurb: "",
      items: detail.sceneObjects.map((object, i) => {
        const word = detail.vocabulary.find(w => w.id === object.vocabularyItemId);
        const translation = detail.translations.find(t => t.vocabularyItemId === object.vocabularyItemId);
        const width = Number(object.boundingBox?.width ?? 0);
        const height = Number(object.boundingBox?.height ?? 0);
        const anchorX = object.anchorPoint ? Number(object.anchorPoint.x) : Number(object.boundingBox?.x ?? 0.5) + width / 2;
        const anchorY = object.anchorPoint ? Number(object.anchorPoint.y) : Number(object.boundingBox?.y ?? 0.5) + height / 2;
        return { id: object.id, word: word?.displayText ?? object.label,
          translation: translation?.translatedText ?? object.label, wordClass: word?.partOfSpeech ?? "noun",
          gender: word?.gender != null && GENDER_ARTICLES.has(word.gender) ? word.gender as Gender : null,
          marker: i + 1,
          x: anchorX * 100,
          y: anchorY * 100,
          attributes: Object.fromEntries(Object.entries(object.attributes ?? {}).filter((entry): entry is [string, string] => typeof entry[1] === "string")),
          example: word?.exampleSentence ?? word?.displayText ?? "", exampleTranslation: "" };
      }),
    };
}

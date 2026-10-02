import type { SceneSummary, VocabRecord } from "../data/types";

type VocabularyGroup = {
  scene: { id: string; title: string; imageUrl: string | null };
  words: VocabRecord[];
};

function vocabularySources(word: VocabRecord, scenes: SceneSummary[]) {
  const readyScene = scenes.find(scene => scene.id === word.sceneId);
  return word.scenes?.length ? word.scenes : readyScene ? [{
    mediaAssetId: readyScene.mediaAssetId, title: readyScene.title, sceneId: readyScene.id,
  }] : [];
}

export function vocabularyCategories(word: VocabRecord, scenes: SceneSummary[]): string[] {
  return [...new Set(vocabularySources(word, scenes).map(source => source.title))];
}

export function groupVocabularyByPhoto(
  vocabulary: VocabRecord[],
  scenes: SceneSummary[],
  imageUrl: (assetId: string) => string,
) {
  const groups = new Map<string, VocabularyGroup>();
  const ungrouped: VocabRecord[] = [];
  for (const word of vocabulary) {
    const sources = vocabularySources(word, scenes);
    if (!sources.length) ungrouped.push(word);
    for (const source of sources) {
      let group = groups.get(source.mediaAssetId);
      if (!group) {
        const ready = scenes.find(scene => scene.mediaAssetId === source.mediaAssetId);
        group = {
          scene: {
            id: source.mediaAssetId,
            title: source.title,
            imageUrl: ready?.imageUrl ?? imageUrl(source.mediaAssetId),
          },
          words: [],
        };
        groups.set(source.mediaAssetId, group);
      }
      if (!group.words.some(item => item.id === word.id)) group.words.push(word);
    }
  }
  return { sceneGroups: [...groups.values()], ungrouped };
}

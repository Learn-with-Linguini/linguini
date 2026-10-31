import type { ScenarioProgress, VocabRecord } from "../data/types.ts";

export type HomeRevisitPhoto = {
  mediaAssetId: string;
  sessionId: string;
  title: string;
  wordCount: number;
};

/** Only saved, completed lessons can open the read-only vocabulary review. */
export function homeRevisitPhotos(scenarios: ScenarioProgress[], vocabulary: VocabRecord[]): HomeRevisitPhoto[] {
  const completed = new Map<string, ScenarioProgress>();
  for (const scenario of scenarios) {
    if (scenario.status !== "completed" && scenario.status !== "mastered") continue;
    if (!scenario.sessionId || !scenario.mediaAssetId) continue;
    completed.set(scenario.mediaAssetId, scenario);
  }

  const wordsByPhoto = new Map<string, Set<string>>();
  for (const word of vocabulary) {
    const sources = word.scenes?.length ? word.scenes.map(scene => scene.mediaAssetId)
      : scenarios.filter(scene => scene.sceneId === word.sceneId).map(scene => scene.mediaAssetId);
    for (const assetId of sources) {
      if (!completed.has(assetId)) continue;
      const words = wordsByPhoto.get(assetId) ?? new Set<string>();
      words.add(word.id);
      wordsByPhoto.set(assetId, words);
    }
  }

  return [...completed.values()].map(scene => ({
    mediaAssetId: scene.mediaAssetId, sessionId: scene.sessionId, title: scene.title,
    wordCount: wordsByPhoto.get(scene.mediaAssetId)?.size ?? 0,
  })).filter(scene => scene.wordCount > 0)
    .sort((a, b) => b.wordCount - a.wordCount)
    .slice(0, 3);
}

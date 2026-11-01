import { getISpyPhotos } from "./api";
import type { ISpyPhoto } from "./api";
import { queryKeys } from "./queryKeys";

export const quickPlayKeys = {
  photos: (owner: string, profileId: string) => [...queryKeys.ispyPhotos(profileId), "quick-play", owner] as const,
  active: (owner: string, profileId: string) => [...queryKeys.activeGame(profileId), "quick-play", owner] as const,
};

/** The personal-photo endpoint enforces ownership; choose only reviewed uploads. */
export async function getQuickPlayPhoto(signal?: AbortSignal): Promise<ISpyPhoto | null> {
  const photos = new Map<string, ISpyPhoto>();
  const cursors = new Set<string>();
  let cursor: string | null = null;
  do {
    const page = await getISpyPhotos(cursor, signal);
    for (const photo of page.photos) {
      if (photo.playable && photo.mediaAsset.id && ["camera", "userUpload"].includes(photo.mediaAsset.source)) photos.set(photo.mediaAsset.id, photo);
    }
    if (photos.size) {
      const playable = [...photos.values()];
      return playable[Math.floor(Math.random() * playable.length)];
    }
    cursor = page.nextCursor;
    if (cursor && cursors.has(cursor)) throw new Error("The photo list changed. Try loading your photos again.");
    if (cursor) cursors.add(cursor);
  } while (cursor);
  return null;
}

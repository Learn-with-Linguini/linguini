import { mediaImageUrl } from "../lib/api";
import { SceneImage } from "./SceneImage";

export function MediaImage({ assetId, title, width = 640, lazy }: { assetId: string; title: string; width?: 320 | 640 | 1280; lazy?: boolean }) {
  return <SceneImage scene={{ title, imageUrl: mediaImageUrl(assetId, width) }} lazy={lazy} />;
}

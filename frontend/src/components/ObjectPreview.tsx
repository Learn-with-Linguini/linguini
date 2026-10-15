import { useState } from "react";
import type { Scene } from "../data/types";
import type { SceneObject } from "../lib/api";
import { SceneVisual } from "./SceneVisual";

const box = (object?: SceneObject) => {
  const value = object?.boundingBox;
  if (!value) return null;
  const [x, y, width, height] = [value.x, value.y, value.width, value.height].map(Number);
  const valid = [x, y, width, height].every(Number.isFinite) && width > 0 && height > 0
    && x >= 0 && y >= 0 && x + width <= 1.001 && y + height <= 1.001;
  return valid ? { x, y, width, height } : null;
};

/** One photo object cropped from its bounding box, or the photo with the object ringed. */
export function ObjectPreview({ scene, object, label }: { scene: Scene; object?: SceneObject; label: string }) {
  const [failed, setFailed] = useState(false);
  const [ratio, setRatio] = useState<number | null>(null);
  const crop = scene.imageUrl && !failed ? box(object) : null;
  const anchor = object?.anchorPoint;
  return <figure className="object-preview">
    {crop ? <div className="object-preview__crop" style={{ aspectRatio: ratio ? String((crop.width * ratio) / crop.height) : "1" }}>
      <img src={scene.imageUrl!} alt={label} onError={() => setFailed(true)}
        onLoad={event => setRatio(event.currentTarget.naturalWidth / event.currentTarget.naturalHeight)}
        style={{ width: `${100 / crop.width}%`, height: `${100 / crop.height}%`, left: `${(-crop.x / crop.width) * 100}%`, top: `${(-crop.y / crop.height) * 100}%` }} />
    </div> : <div className="object-preview__scene">
      <SceneVisual scene={scene} />
      {anchor ? <span className="object-preview__ring" aria-hidden="true"
        style={{ left: `${Number(anchor.x) * 100}%`, top: `${Number(anchor.y) * 100}%` }} /> : null}
    </div>}
    <figcaption><strong>{label}</strong></figcaption>
  </figure>;
}

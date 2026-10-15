import type { Scene } from "../data/types";
import type { SceneObject } from "../lib/api";
import { SceneVisual } from "./SceneVisual";

const marker = (object?: SceneObject) => {
  if (object?.anchorPoint) return { x: Number(object.anchorPoint.x), y: Number(object.anchorPoint.y) };
  const box = object?.boundingBox;
  if (!box) return null;
  return { x: Number(box.x) + Number(box.width) / 2, y: Number(box.y) + Number(box.height) / 2 };
};

/** The whole photo with a marker on one object, and the object's English label. */
export function ObjectPreview({ scene, object, label }: { scene: Scene; object?: SceneObject; label: string }) {
  const point = marker(object);
  const usable = point && Number.isFinite(point.x) && Number.isFinite(point.y);
  return <figure className="object-preview">
    <div className="object-preview__scene">
      <SceneVisual scene={scene} />
      {usable ? <span className="object-preview__ring" aria-hidden="true"
        style={{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }} /> : null}
    </div>
    <figcaption><strong>{label}</strong></figcaption>
  </figure>;
}

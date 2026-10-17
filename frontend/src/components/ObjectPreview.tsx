import type { Scene } from "../data/types";
import type { SceneObject } from "../lib/api";
import { ScenePhoto } from "./ScenePhoto";

/** The whole photo with scene-analysis markers on one object, a counted group, or an
 * object (selected marker) and its reference, with English labels. */
export function ObjectPreview({ scene, object, label, reference, referenceLabel, group }: {
  scene: Scene; object?: SceneObject; label: string; reference?: SceneObject;
  referenceLabel?: string | null; group?: SceneObject[];
}) {
  const shown = group ? group.map(item => item.id) : [object?.id, referenceLabel ? reference?.id : undefined];
  const items = scene.items.filter(item => shown.includes(item.id));
  const number = (target?: SceneObject) => scene.items.find(item => item.id === target?.id)?.marker;
  return <figure className="object-preview">
    <div className="object-preview__scene mission-markers">
      <ScenePhoto scene={scene} items={items} activeItemId={group ? null : object?.id ?? null} />
    </div>
    {label || referenceLabel ? <figcaption className="object-preview__legend">
      {referenceLabel ? <>
        <span><span className="object-preview__key object-preview__key--target" aria-hidden="true">{number(object)}</span><strong>{label}</strong></span>
        <span><span className="object-preview__key object-preview__key--reference" aria-hidden="true">{number(reference)}</span><strong>{referenceLabel}</strong></span>
      </> : <strong>{label}</strong>}
    </figcaption> : null}
  </figure>;
}

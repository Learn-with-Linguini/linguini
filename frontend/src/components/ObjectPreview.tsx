import type { Scene } from "../data/types";
import type { SceneObject } from "../lib/api";
import type { MissionMarker } from "../lib/missionMarkers";
import { SceneVisual } from "./SceneVisual";

const marker = (object?: SceneObject) => {
  if (object?.anchorPoint) return { x: Number(object.anchorPoint.x), y: Number(object.anchorPoint.y) };
  const box = object?.boundingBox;
  if (!box) return null;
  return { x: Number(box.x) + Number(box.width) / 2, y: Number(box.y) + Number(box.height) / 2 };
};

function Ring({ object, tone }: { object?: SceneObject; tone: "target" | "reference" }) {
  const point = marker(object);
  if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
  return <span className={`object-preview__ring object-preview__ring--${tone}`} aria-hidden="true"
    style={{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }} />;
}

function NumberedMarker({ object, number }: MissionMarker) {
  const point = marker(object);
  if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
  return <span className="analysis-word-row__marker object-preview__marker" aria-hidden="true"
    style={{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }}>{number}</span>;
}

/** The whole photo with a marker on one object, a counted group, or two, and English labels. */
export function ObjectPreview({ scene, object, label, reference, referenceLabel, group, markers }: {
  scene: Scene; object?: SceneObject; label: string; reference?: SceneObject;
  referenceLabel?: string | null; group?: SceneObject[]; markers?: MissionMarker[];
}) {
  return <figure className="object-preview">
    <div className="object-preview__scene">
      <SceneVisual scene={scene} />
      {markers ? markers.map(item => <NumberedMarker key={item.object.id} {...item} />) : <>
        {group ? group.map(item => <Ring key={item.id} object={item} tone="target" />)
          : <Ring object={object} tone="target" />}
        {referenceLabel ? <Ring object={reference} tone="reference" /> : null}
      </>}
    </div>
    <figcaption className="object-preview__legend">
      {markers ? <>
        {label.trim() ? <strong>{label}</strong> : null}
        <span className="object-preview__marker-note">
          Numbered markers match your scene review.
        </span>
      </> : referenceLabel ? <>
        <span><span className="object-preview__key object-preview__key--target" aria-hidden="true" /><strong>{label}</strong></span>
        <span><span className="object-preview__key object-preview__key--reference" aria-hidden="true" /><strong>{referenceLabel}</strong></span>
      </> : <strong>{label}</strong>}
    </figcaption>
  </figure>;
}

import type { LanguageItem } from "../data/types";
import type { SceneObject } from "./api";

export interface MissionMarker {
  object: SceneObject;
  number: number;
}

export function questionMarkerObjects(
  markerObjectIds: Record<string, string> | null | undefined,
  sceneObjectId: string | null | undefined,
  sceneObjects: readonly SceneObject[],
  sceneItems: readonly LanguageItem[],
): MissionMarker[] {
  const ids = markerObjectIds
    ? Object.values(markerObjectIds)
    : sceneObjectId ? [sceneObjectId] : [];
  const objectsById = new Map(sceneObjects.map(object => [object.id, object]));
  const itemsById = new Map(sceneItems.map(item => [item.id, item]));
  return [...new Set(ids)]
    .flatMap(id => {
      const object = objectsById.get(id);
      const number = itemsById.get(id)?.marker;
      return object && typeof number === "number" && Number.isInteger(number) && number > 0
        ? [{ object, number }]
        : [];
    })
    .sort((left, right) => left.number - right.number || left.object.id.localeCompare(right.object.id));
}

export function optionMarkerNumber(
  optionId: string,
  markerObjectIds: Record<string, string> | null | undefined,
  sceneItems: readonly LanguageItem[],
): number | null {
  const objectId = markerObjectIds?.[optionId];
  const number = objectId
    ? sceneItems.find(item => item.id === objectId)?.marker
    : undefined;
  return typeof number === "number" && Number.isInteger(number) && number > 0 ? number : null;
}

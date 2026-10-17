import type { SceneObject } from "./api";

export interface MissionMarker {
  object: SceneObject;
  number: number;
}

export function questionMarkerObjects(
  markers: Record<string, number> | null | undefined,
  sceneObjects: readonly SceneObject[],
): MissionMarker[] {
  if (!markers) return [];
  const objectsById = new Map(sceneObjects.map(object => [object.id, object]));
  return Object.entries(markers)
    .flatMap(([objectId, number]) => {
      const object = objectsById.get(objectId);
      return object && Number.isInteger(number) && number > 0 ? [{ object, number }] : [];
    })
    .sort((left, right) => left.number - right.number || left.object.id.localeCompare(right.object.id));
}

export function optionMarkerNumber(
  optionId: string,
  optionObjectIds: Record<string, string> | null | undefined,
  markers: Record<string, number> | null | undefined,
): number | null {
  const objectId = optionObjectIds?.[optionId];
  const number = objectId ? markers?.[objectId] : undefined;
  return typeof number === "number" && Number.isInteger(number) && number > 0 ? number : null;
}

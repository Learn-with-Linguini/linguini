/** Practice-board geometry for M03's match-quantity question. */

import type { SceneObject } from "./api";

export interface BoardBox {
  x: number | string;
  y: number | string;
  width: number | string;
  height: number | string;
}

export interface SquareCrop {
  x: number;
  y: number;
  size: number;
}

/** Split a tile count into rows of at most ten, e.g. 12 -> [10, 2]. */
export function boardRows(count: number): number[] {
  const rows: number[] = [];
  let remaining = Math.max(0, Math.floor(count));
  while (remaining > 10) {
    rows.push(10);
    remaining -= 10;
  }
  if (remaining > 0) rows.push(remaining);
  return rows;
}

/**
 * A centred square crop of a normalized bounding box, in image pixels.
 * The side covers the box's longer edge without cutting off any of the object.
 */
export function squareCrop(
  box: BoardBox | null | undefined,
  imageWidth: number,
  imageHeight: number,
): SquareCrop | null {
  if (!box || !Number.isFinite(imageWidth) || !Number.isFinite(imageHeight)
    || imageWidth <= 0 || imageHeight <= 0) return null;
  const [x0, y0, width, height] = [box.x, box.y, box.width, box.height].map(Number);
  if (![x0, y0, width, height].every(Number.isFinite) || x0 < 0 || y0 < 0
    || width <= 0 || height <= 0 || x0 + width > 1 || y0 + height > 1) return null;
  const bx = x0 * imageWidth;
  const by = y0 * imageHeight;
  const bw = width * imageWidth;
  const bh = height * imageHeight;
  const size = Math.max(bw, bh);
  if (size > imageWidth || size > imageHeight) return null;
  const x = Math.min(Math.max(bx + bw / 2 - size / 2, 0), imageWidth - size);
  const y = Math.min(Math.max(by + bh / 2 - size / 2, 0), imageHeight - size);
  return { x, y, size };
}

/** A marker records a location, not the object's bounds. */
export function practiceBoardCrop(
  object: Pick<SceneObject, "boundingBox" | "anchorPoint" | "confidenceScore" | "sourceObjectKey"> | null | undefined,
  imageWidth: number,
  imageHeight: number,
): SquareCrop | null {
  const box = object?.boundingBox;
  // Older manual additions stored a 1% square at the click, without detection provenance.
  if (box && Number(box.width) === 0.01 && Number(box.height) === 0.01
    && !object.anchorPoint && object.confidenceScore == null && !object.sourceObjectKey) return null;
  return squareCrop(box, imageWidth, imageHeight);
}

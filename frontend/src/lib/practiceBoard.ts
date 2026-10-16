/** Practice-board geometry for M03's match-quantity question. */

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
 * The side covers the box's longer edge and is clamped inside the image.
 */
export function squareCrop(
  box: BoardBox | null | undefined,
  imageWidth: number,
  imageHeight: number,
): SquareCrop | null {
  if (!box || imageWidth <= 0 || imageHeight <= 0) return null;
  const bx = Number(box.x) * imageWidth;
  const by = Number(box.y) * imageHeight;
  const bw = Number(box.width) * imageWidth;
  const bh = Number(box.height) * imageHeight;
  if (![bx, by, bw, bh].every(Number.isFinite) || bw <= 0 || bh <= 0) return null;
  const size = Math.min(Math.max(bw, bh), imageWidth, imageHeight);
  const x = Math.min(Math.max(bx + bw / 2 - size / 2, 0), imageWidth - size);
  const y = Math.min(Math.max(by + bh / 2 - size / 2, 0), imageHeight - size);
  return { x, y, size };
}

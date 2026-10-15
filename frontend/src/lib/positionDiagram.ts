/** Where a diagram draws the target object for each confirmed relation; the reference never moves. */
export type DiagramPosition = "on" | "under" | "next_to" | "in_front_of" | "behind";

export const DIAGRAM_TARGETS: Record<DiagramPosition, { x: number; y: number; size: number; front: boolean }> = {
  on: { x: 58, y: 18, size: 24, front: true },
  under: { x: 58, y: 58, size: 24, front: true },
  next_to: { x: 118, y: 58, size: 24, front: true },
  in_front_of: { x: 53, y: 46, size: 34, front: true },
  behind: { x: 55, y: 10, size: 30, front: false },
};

export const isDiagramPosition = (value: string): value is DiagramPosition => value in DIAGRAM_TARGETS;

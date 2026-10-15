import { DIAGRAM_TARGETS, type DiagramPosition } from "../lib/positionDiagram";

export { isDiagramPosition } from "../lib/positionDiagram";

/** An illustration of a target object placed relative to a reference table-like shape. */
export function PositionDiagram({ position, target, reference }: { position: DiagramPosition; target: string; reference: string }) {
  const placed = DIAGRAM_TARGETS[position];
  const object = <g className="position-diagram__target">
    <rect x={placed.x} y={placed.y} width={placed.size} height={placed.size} rx="5" />
  </g>;
  return <svg className="position-diagram" viewBox="0 0 150 100" role="img" aria-hidden="true" focusable="false">
    <line className="position-diagram__ground" x1="6" y1="84" x2="144" y2="84" />
    {placed.front ? null : object}
    <g className="position-diagram__reference">
      <rect x="30" y="42" width="80" height="10" rx="3" />
      <rect x="36" y="52" width="8" height="32" rx="2" />
      <rect x="96" y="52" width="8" height="32" rx="2" />
    </g>
    {placed.front ? object : null}
    <text className="position-diagram__label" x="70" y="96" textAnchor="middle">{reference}</text>
    <text className="position-diagram__label position-diagram__label--target" x="6" y="12">{target}</text>
  </svg>;
}

import type { Scene } from "../data/types";
import { ScenePhoto } from "./ScenePhoto";

/** A playful, non-interactive treatment while a scene is being prepared. */
export function AnalysisScan({ scene }: { scene: Scene }) {
  return (
    <div className="analysis-scan" aria-hidden="true">
      <ScenePhoto scene={scene} items={[]} />
      <span className="analysis-scan__noodle" />
    </div>
  );
}

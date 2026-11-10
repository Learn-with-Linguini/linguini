import type { Scene, SceneSummary } from "../data/types";
import { ScenePhoto } from "./ScenePhoto";
import "./AnalysisScan.css";

/** A playful, non-interactive treatment while a scene is being prepared. */
export function AnalysisScan({ scene }: { scene: Scene | SceneSummary }) {
  return (
    <div className="analysis-scan" aria-hidden="true">
      <ScenePhoto scene={scene} items={[]} />
      <span className="analysis-scan__sweep" />
    </div>
  );
}

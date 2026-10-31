import type { Scene } from "../data/types";
import { ScenePhoto } from "./ScenePhoto";
import "./AnalysisScan.css";

/** A playful, non-interactive treatment while a scene is being prepared. */
export function AnalysisScan({ scene }: { scene: Scene }) {
  return (
    <div className="analysis-scan" aria-hidden="true">
      <ScenePhoto scene={scene} items={[]} />
      <svg className="analysis-scan__trail" viewBox="0 0 1000 600" preserveAspectRatio="none">
        <rect className="analysis-scan__trail-track" x="13" y="13" width="974" height="574" rx="30" pathLength="100" />
        <rect className="analysis-scan__trail-outline" x="13" y="13" width="974" height="574" rx="30" pathLength="100" />
        <rect className="analysis-scan__trail-pasta" x="13" y="13" width="974" height="574" rx="30" pathLength="100" />
        <rect className="analysis-scan__trail-shine" x="13" y="13" width="974" height="574" rx="30" pathLength="100" />
      </svg>
      <span className="analysis-scan__caption">
        <span>Taking a look around</span>
        <span>Spotting useful words</span>
        <span>Getting your scene ready</span>
      </span>
    </div>
  );
}

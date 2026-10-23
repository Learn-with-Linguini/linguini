import type { SceneShortfall, ShortfallKind } from "../lib/api";
import { SHORTFALL_ACTIONS, closestMissions, stepsFor } from "../lib/sceneShortfall";
import { Button } from "./ui";

/** Explains why a lesson can't be built yet and offers each way to add what is short. */
export function SceneShortfallNotice({ shortfall, busy, onAdd, onTryAnotherPhoto }: {
  shortfall: SceneShortfall;
  busy?: boolean;
  onAdd: (kind: ShortfallKind) => void;
  onTryAnotherPhoto: () => void;
}) {
  const missions = closestMissions(shortfall);
  return <section className="scene-shortfall" role="alert" aria-labelledby="scene-shortfall-title">
    <h2 id="scene-shortfall-title">Add a little more to this photo</h2>
    <p>Linguini needs more it can check before it builds your lesson. Add {shortfall.missing.length > 1 ? "any of these" : "this"}, then confirm again.</p>
    <ul className="scene-shortfall__list">
      {shortfall.missing.map(kind => {
        // Specific steps come from the confirmed review; the general hint covers the rest.
        const steps = stepsFor(shortfall, kind);
        return <li key={kind}>
        <span><strong>{SHORTFALL_ACTIONS[kind].title}</strong>{steps.length
          ? steps.map(step => <small key={step} className="scene-shortfall__step">{step}</small>)
          : <small>{SHORTFALL_ACTIONS[kind].hint}</small>}</span>
        <Button variant="secondary" disabled={busy} onClick={() => onAdd(kind)}>{SHORTFALL_ACTIONS[kind].action}</Button>
      </li>;
      })}
    </ul>
    {missions.length ? <details className="scene-shortfall__missions">
      <summary>What each lesson needs</summary>
      <ul>
        {missions.map(mission => <li key={mission.missionId}><strong>{mission.title}:</strong> {(mission.steps.length ? mission.steps.map(step => step.text) : mission.reasons).join(" ")}</li>)}
      </ul>
    </details> : null}
    <p className="small muted">Not much else in this photo? Take or choose another one with more to talk about.</p>
    <Button variant="quiet" disabled={busy} onClick={onTryAnotherPhoto}>Try another photo</Button>
  </section>;
}

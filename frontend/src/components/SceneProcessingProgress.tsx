import { useEffect, useRef, useState } from "react";
import type { PracticeDetail } from "../lib/api";
import { trackAction } from "../lib/analytics";
import "./SceneProcessingProgress.css";

const ANALYSIS_STAGES = [
  ["loadingImage", "Loading your photo"],
  ["findingObjects", "Finding objects in your photo"],
  ["checkingResults", "Checking the objects and details"],
  ["savingResults", "Getting your review ready"],
] as const;

export function SceneProcessingProgress({ detail, stalled = false }: { detail: PracticeDetail; stalled?: boolean }) {
  const { status, id } = detail.session;
  const generation = status === "generatingTasks";
  const progress = detail.sceneAnalysisProgress;
  const stage = generation
    ? detail.tasks.some(task => task.kind === "vocabularyIntroduction") ? "ready"
      : detail.translationPreview ? "preparingTask" : "translating"
    : status === "awaitingObjectReview" ? "ready" : progress?.stage ?? "unknown";
  const stages = generation
    ? [["translating", "Translating your words"], ["preparingTask", "Preparing your first task"]]
    : ANALYSIS_STAGES;
  const complete = stage === "ready";
  const index = complete ? stages.length : stages.findIndex(([key]) => key === stage);
  const label = complete ? generation ? "Your first task is ready" : "Your scene is ready to review"
    : index < 0 ? "Finding objects in your photo" : stages[index][1];
  const startedAt = !generation && progress?.startedAt ? Date.parse(progress.startedAt) : NaN;
  const [now, setNow] = useState(Date.now);
  const lastEvent = useRef("");

  useEffect(() => {
    const key = `${id}:${progress?.startedAt}:${generation}:${stage}:${stalled}`;
    if (lastEvent.current === key) return;
    lastEvent.current = key;
    trackAction("scene_processing_progress_shown", { sessionId: id, phase: generation ? "lesson" : "analysis", stage, stalled });
  }, [id, progress?.startedAt, generation, stage, stalled]);

  useEffect(() => {
    if (complete || !Number.isFinite(startedAt)) return;
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [startedAt, complete]);

  const elapsed = Math.max(0, Math.floor((now - startedAt) / 1000));
  const elapsedLabel = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;
  return <div className="scene-processing-progress">
    <div className="scene-processing-progress__heading">
      <p className="scene-processing-progress__label" role="status">{stalled ? "Updates paused — check again" : label}</p>
      {!complete && Number.isFinite(startedAt) ? <span className="small muted" aria-hidden="true">Elapsed {elapsedLabel}</span> : null}
    </div>
    <div className="scene-processing-progress__bar" role="progressbar"
      aria-label={generation ? "Lesson preparation stages" : "Scene analysis stages"}
      aria-valuemin={index >= 0 ? 0 : undefined} aria-valuemax={index >= 0 ? stages.length : undefined}
      aria-valuenow={index >= 0 ? index : undefined}
      aria-valuetext={`${label}${index >= 0 ? `. ${index} of ${stages.length} stages complete.` : ". Waiting for progress updates."}`}>
      {stages.map(([key], position) => <span key={key} aria-hidden="true"
        className={`scene-processing-progress__segment${position < index ? " is-complete" : ""}${!complete && !stalled && (index === position || index < 0 && position === 0) ? " is-active" : ""}`} />)}
    </div>
  </div>;
}

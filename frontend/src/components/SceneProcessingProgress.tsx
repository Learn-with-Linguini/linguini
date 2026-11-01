import { useEffect, useRef } from "react";
import type { PracticeDetail } from "../lib/api";
import { trackAction } from "../lib/analytics";
import { CheckIcon } from "./icons";
import "./SceneProcessingProgress.css";

const ANALYSIS_STAGES = [
  ["loadingImage", "Loading your photo", "Photo"],
  ["findingObjects", "Finding objects in your photo", "Objects"],
  ["checkingResults", "Checking the objects and details", "Details"],
  ["savingResults", "Getting your review ready", "Review"],
] as const;

const GENERATION_STAGES = [
  ["translating", "Translating your words", "Words"],
  ["preparingTask", "Preparing your first task", "First task"],
] as const;

export function SceneProcessingProgress({ detail, stalled = false }: { detail: PracticeDetail; stalled?: boolean }) {
  const { status, id } = detail.session;
  const generation = status === "generatingTasks";
  const progress = detail.sceneAnalysisProgress;
  const stage = generation
    ? detail.tasks.some(task => task.kind === "vocabularyIntroduction") ? "ready"
      : detail.translationPreview ? "preparingTask" : "translating"
    : status === "awaitingObjectReview" ? "ready" : progress?.stage ?? "unknown";
  const stages = generation ? GENERATION_STAGES : ANALYSIS_STAGES;
  const complete = stage === "ready";
  const index = complete ? stages.length : stages.findIndex(([key]) => key === stage);
  const label = complete ? generation ? "Your first task is ready" : "Your scene is ready to review"
    : index < 0 ? "Finding objects in your photo" : stages[index][1];
  const lastEvent = useRef("");

  useEffect(() => {
    const key = `${id}:${progress?.startedAt}:${generation}:${stage}:${stalled}`;
    if (lastEvent.current === key) return;
    lastEvent.current = key;
    trackAction("scene_processing_progress_shown", { sessionId: id, phase: generation ? "lesson" : "analysis", stage, stalled });
  }, [id, progress?.startedAt, generation, stage, stalled]);

  return <div className="scene-processing-progress">
    <div className="scene-processing-progress__steps" role="progressbar"
      aria-label={generation ? "Lesson preparation stages" : "Scene analysis stages"}
      aria-valuemin={index >= 0 ? 0 : undefined} aria-valuemax={index >= 0 ? stages.length : undefined}
      aria-valuenow={index >= 0 ? index : undefined}
      aria-valuetext={`${label}${index >= 0 ? `. ${index} of ${stages.length} stages complete.` : ". Waiting for progress updates."}`}>
      {stages.map(([key, , name], position) => {
        // Once processing is done the last step is where the learner picks up, so it stays current rather than ticked.
        const ready = complete && position === stages.length - 1;
        const current = !complete && (index === position || index < 0 && position === 0);
        const state = ready ? "ready" : position < index ? "complete" : current ? stalled ? "paused" : "active" : "upcoming";
        return <div key={key} className="scene-processing-progress__step" data-state={state} aria-hidden="true">
          <span className="scene-processing-progress__node">
            {state === "complete" ? <CheckIcon size={20} /> : position + 1}
          </span>
          <span className="scene-processing-progress__name">{name}</span>
        </div>;
      })}
    </div>
    <p className="scene-processing-progress__status" data-stalled={stalled || undefined}>
      <span role="status">{stalled ? "Updates paused. Check again" : label}</span>
    </p>
  </div>;
}

import type { PracticeDetail, SessionStatus, TaskActionResult } from "./api";

// Statuses the backend walks through before any task exists. The client
// advances through them optimistically, so a reply that is still behind must
// not move the session backwards; anything later (ready, completion, failure)
// always wins. A review the backend reopened with a scene shortfall also wins:
// generation found nothing it could check and needs more from the learner.
const EARLY_STAGES: SessionStatus[] = ["created", "analyzingScene", "awaitingObjectReview", "generatingTasks"];

export function keepClientProgress(current: PracticeDetail | null, incoming: PracticeDetail): PracticeDetail {
  if (current?.session.id !== incoming.session.id) return incoming;
  if (incoming.session.status === "awaitingObjectReview" && incoming.sceneShortfall) return incoming;
  const incomingStage = EARLY_STAGES.indexOf(incoming.session.status);
  const currentStage = EARLY_STAGES.indexOf(current.session.status);
  if (incomingStage === -1 || currentStage === -1 || incomingStage >= currentStage) return incoming;
  return { ...incoming, session: { ...incoming.session, status: current.session.status } };
}

// A saved action may arrive after the user has opened another session.
export function applyTaskResult(current: PracticeDetail | null, sessionId: string, result: TaskActionResult): PracticeDetail | null {
  if (!current || current.session.id !== sessionId) return current;
  return {
    ...current,
    tasks: current.tasks.map(task => task.id === result.task.id ? result.task : task),
    nextTaskId: result.nextTaskId,
    progress: result.sessionProgress,
  };
}

import type { PracticeDetail, SessionStatus } from "./api";
import { practiceStages, taskDone } from "./practiceTasks.ts";

export interface SessionDestination {
  /** Canonical path for this session's current state. */
  path: string;
  /** Learner-facing notice to surface at the destination, or null. */
  notice: string | null;
}

const failureNotices: Record<string, string> = {
  imageUploadFailed: "We couldn't save your photo. Start a new practice when you are ready.",
  sceneAnalysisFailed: "We still couldn't analyse that photo. Please try again in a moment, or choose another photo.",
  imageModerationFailed: "That photo can't be used for practice. Choose a different photo and try again.",
  noValidObjects: "We couldn't find anything to learn in that photo. Try a busier scene.",
  vocabularyMappingFailed: "We couldn't turn that scene into words. Start a new practice when you are ready.",
  taskGenerationFailed: "We couldn't build your lesson. Start a new practice when you are ready.",
};

const fallbackNotice = "That practice couldn't continue. Start a new one when you are ready.";

export interface SessionPaths {
  clues: string;
  describe: string;
  done: string;
  /** Where an I-Spy page sends a learner whose session can't play its rounds. */
  exit: string;
}

export function sessionPaths(detail: PracticeDetail): SessionPaths {
  const id = detail.session.id;
  if (detail.session.mode === "ispy") {
    const base = `/ispy/games/${id}`;
    return { clues: `${base}/clues`, describe: `${base}/describe`, done: `${base}/results`, exit: "/ispy/play" };
  }
  const base = `/practice/sessions/${id}`;
  return { clues: `${base}/ispy-1`, describe: `${base}/ispy-2`, done: `${base}/summary`, exit: `${base}/learn` };
}

function gameDestination(detail: PracticeDetail): SessionDestination {
  const paths = sessionPaths(detail);
  switch (detail.session.status) {
    case "inProgress":
      return { path: practiceStages(detail.tasks).clues.some(task => !taskDone(task)) ? paths.clues : paths.describe, notice: null };
    case "completed":
      return { path: paths.done, notice: null };
    case "abandoned":
      return { path: paths.exit, notice: "That game was ended. Choose a photo to play again." };
    case "failed":
      return { path: paths.exit, notice: "Linguini couldn't set up a game with that photo. Try it again or choose another photo." };
    default:
      return { path: paths.clues, notice: null };
  }
}

export function sessionDestination(detail: PracticeDetail): SessionDestination {
  if (detail.session.mode === "ispy") return gameDestination(detail);
  const base = `/practice/sessions/${detail.session.id}`;
  switch (detail.session.status) {
    case "created":
    case "analyzingScene":
    case "awaitingObjectReview":
      return { path: `${base}/analysis`, notice: null };
    case "generatingTasks":
      return { path: `${base}/analysis`, notice: null };
    case "ready":
      return { path: `${base}/mic-test`, notice: null };
    case "inProgress": {
      const stages = practiceStages(detail.tasks);
      if (!detail.tasks.length || stages.learning.some(task => !taskDone(task))) return { path: `${base}/learn`, notice: null };
      if (stages.clues.some(task => !taskDone(task))) return { path: `${base}/ispy-1`, notice: null };
      return { path: `${base}/ispy-2`, notice: null };
    }
    case "completed":
      return { path: `${base}/summary`, notice: null };
    case "abandoned":
      return { path: "/practice", notice: "That practice was discarded. Start a new one when you are ready." };
    case "failed":
      if (detail.analysisRetryable || detail.generationRetryable) return { path: `${base}/analysis`, notice: null };
      return { path: "/practice", notice: (detail.session.failureCode && failureNotices[detail.session.failureCode]) || fallbackNotice };
    default:
      return { path: "/practice", notice: fallbackNotice };
  }
}

export function isSessionRouteAllowed(detail: PracticeDetail, pathname: string): boolean {
  const canonical = sessionDestination(detail).path;
  if (pathname === canonical) return true;
  if (detail.session.status === "generatingTasks"
    && detail.tasks.some(task => task.kind === "vocabularyIntroduction")
    && pathname.startsWith(`${canonical.slice(0, -"/analysis".length)}/learn`)) return true;
  if (!canonical.endsWith("/learn")) return false;
  return pathname.startsWith(`${canonical}/`) || pathname === `${canonical.slice(0, -"/learn".length)}/mic-test`;
}

export interface SessionLoadingCopy {
  title: string;
  heading: string;
  /** Supporting line under the heading, when the default doesn't fit the step. */
  support?: string;
  scan: boolean;
}

const loadingCopy: Record<string, SessionLoadingCopy> = {
  analysis: { title: "Scene analysis", heading: "Finding objects in your image...", scan: true },
  "mic-test": { title: "Mic check", heading: "Getting your microphone ready...", scan: false },
  learn: { title: "Learning", heading: "Loading your words...", scan: false },
  "ispy-1": { title: "I-Spy", heading: "Setting up your I-Spy clue...", scan: false },
  "ispy-2": { title: "I-Spy", heading: "Setting up your turn to describe...", scan: false },
  summary: { title: "Practice summary", heading: "Gathering your results...", scan: false },
  clues: { title: "I-Spy", heading: "Linguini is choosing objects to spy...", support: "Clues come from the scene you confirmed.", scan: false },
  describe: { title: "I-Spy", heading: "Setting up your turn to describe...", scan: false },
  results: { title: "Game results", heading: "Gathering your results...", scan: false },
};

const sessionStep = (pathname: string) => /^\/(?:practice\/sessions|ispy\/games)\/[^/]+\/([^/]+)/.exec(pathname)?.[1] ?? null;

/** Steps before the learner starts tasks: forwarding them when the session advances strands nobody. */
export function isPreTaskStep(pathname: string): boolean {
  const step = sessionStep(pathname);
  return step === "analysis" || step === "mic-test";
}

const translatingCopy: SessionLoadingCopy = {
  title: "Scene analysis",
  heading: "Translating your scene...",
  support: "Turning your confirmed words into your learning language.",
  scan: true,
};

export function sessionLoadingCopy(pathname: string, status?: SessionStatus): SessionLoadingCopy {
  const step = sessionStep(pathname);
  if (step === "analysis" && status === "generatingTasks") return translatingCopy;
  return (step && loadingCopy[step]) || { title: "Practice", heading: "Loading your practice...", scan: false };
}

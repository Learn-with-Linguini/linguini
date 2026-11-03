import { playAnswerSound, playFinishSound } from "./answerSound";

export type PastaShowerVariant = "answer" | "perfect" | "partial";
export type FinishScore = "perfect" | "partial";
export const PASTA_SHOWER_EVENT = "linguini:pasta-shower";

/** Asks the mounted `PastaShowerHost` to drop a shower of pasta over the page. */
export function showPastaShower(variant: PastaShowerVariant) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new window.CustomEvent<PastaShowerVariant>(PASTA_SHOWER_EVENT, { detail: variant }));
}

/** Feedback for a graded answer: a sound either way, and a light pasta shower when it is right. */
export function celebrateAnswer(correct: boolean) {
  playAnswerSound(correct);
  if (correct) showPastaShower("answer");
}

/** The finish screen's celebration; a perfect score gets the full shower and fanfare. */
export function celebrateFinish(score: FinishScore) {
  playFinishSound(score === "perfect");
  showPastaShower(score);
}

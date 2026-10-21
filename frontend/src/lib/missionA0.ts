import type { GrammarLessonQuestion } from "./api";

/** The chunk with its missing word filled in: `___ tasse` + `la` → `la tasse`, `책___` + `이에요` → `책이에요`. */
export function completeSlot(template: string, word: string) {
  return template.replace("___", word).replace(/(['’]) +/u, "$1");
}

/** Whether the browser can read target-language text aloud. */
export const speechAvailable = () => typeof window !== "undefined" && Boolean(window.speechSynthesis);

/** Listening questions keep their written prompt hidden until revealed, graded or audio is unavailable. */
export function writtenPromptShown(
  question: Pick<GrammarLessonQuestion, "listenFirst">,
  state: { revealed: boolean; graded: boolean; audio: boolean },
) {
  return !question.listenFirst || state.revealed || state.graded || !state.audio;
}

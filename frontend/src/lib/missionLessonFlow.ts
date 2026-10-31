import type { GrammarLessonQuestion, LessonAnswerCheck } from "./api";

export function mergeLessonChecks(
  saved: readonly LessonAnswerCheck[],
  local: Readonly<Record<string, LessonAnswerCheck>>,
): Record<string, LessonAnswerCheck> {
  return {
    ...Object.fromEntries(saved.map(check => [check.questionId, check])),
    ...local,
  };
}

export function visibleLessonQuestionIndex(
  questionIds: readonly string[],
  checks: Readonly<Record<string, LessonAnswerCheck>>,
): number {
  if (!questionIds.length) return 0;
  const next = questionIds.findIndex(questionId => !checks[questionId]);
  return next === -1 ? questionIds.length - 1 : next;
}

/** A2 construction questions build on the checked question in their own activity section. */
export function previousLessonContext(
  questions: readonly GrammarLessonQuestion[],
  currentIndex: number,
  checks: Readonly<Record<string, LessonAnswerCheck>>,
  practiceLevel: string | undefined,
) {
  const current = questions[currentIndex];
  const previous = questions[currentIndex - 1];
  if (practiceLevel !== "A2" || current?.interactionType !== "sentenceBuilding"
    || !current.section || previous?.section !== current.section) return null;
  const check = checks[previous.questionId];
  if (!check || check.outcome.outcome === "unassessed" || (check.attemptsLeft ?? 0) > 0) return null;

  let sentence: string | null = null;
  if (previous.markerObjectIds && Object.keys(previous.markerObjectIds).length) {
    // The prompt contains the source sentence; the checked answer names a photo marker.
    sentence = previous.audioText ?? null;
  } else if (previous.interactionType === "multipleChoice") {
    const correct = previous.options.find(option => option.optionId === check.correctAnswer || option.label === check.correctAnswer);
    const accepted = previous.options.find(option => option.optionId === check.answer || option.label === check.answer);
    sentence = (check.isCorrect ? accepted?.label ?? correct?.label : correct?.label) ?? null;
  } else {
    sentence = check.isCorrect ? check.answer : check.correctAnswer;
  }
  // Numeric choices are counts or markers, not a previous sentence.
  if (sentence && (Number.isFinite(Number(sentence)) || previous.prompt.includes(sentence))) sentence = null;
  return {
    questionId: previous.questionId, prompt: previous.prompt,
    promptTranslation: previous.translation ?? previous.promptTranslation ?? null,
    sentence, sentenceTranslation: sentence ? previous.completeTranslation ?? null : null,
  };
}

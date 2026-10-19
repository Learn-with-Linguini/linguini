import type { LessonAnswerCheck } from "./api";

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

import type { GrammarLessonQuestion, LessonAnswerCheck } from "./api";

export function isM06ScenarioVisible(
  missionId: string | undefined,
  scenario: { accepted: boolean } | null | undefined,
): boolean {
  return missionId === "M06" && Boolean(scenario && !scenario.accepted);
}

export function retryTokens(
  tokens: readonly string[],
  wrongField: string | null | undefined,
  tokenFields: Readonly<Record<string, string>>,
): string[] {
  if (!wrongField) return [...tokens];
  return tokens.filter(token => tokenFields[token] !== wrongField);
}

export function nextAssistanceStep(
  steps: readonly string[] | null | undefined,
  used: readonly string[],
): string | null {
  return steps?.[used.length] ?? null;
}

export function lessonCheckFinished(
  check: Pick<LessonAnswerCheck, "isCorrect" | "attemptsLeft"> | undefined,
  allowRetry: boolean | null = true,
): boolean {
  return Boolean(check && (!allowRetry || check.isCorrect || check.attemptsLeft === 0));
}

export function unlockedRetryResumeIndex(
  questions: readonly Pick<GrammarLessonQuestion, "questionId">[],
  checks: Readonly<Record<string, LessonAnswerCheck>>,
): number {
  const next = questions.findIndex(question => {
    const check = checks[question.questionId];
    return !lessonCheckFinished(check);
  });
  return next === -1 ? Math.max(0, questions.length - 1) : next;
}

export const FIRST_LESSON_WALKTHROUGH_VERSION = 1;

export function needsFirstLessonWalkthrough(versionSeen: number | undefined): boolean {
  return (versionSeen ?? 0) < FIRST_LESSON_WALKTHROUGH_VERSION;
}

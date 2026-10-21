import type { LanguageItem, Scene } from "../data/types";
import type { GrammarLessonQuestion, SessionTask } from "./api";

export const taskDone = (task: SessionTask) => task.status === "completed" || task.status === "skipped";

export function taskXp(task: SessionTask): { xp: number; bonus: number } | null {
  return task.xpReward === 0 && task.xpBonus === 0
    ? null
    : { xp: task.xpReward, bonus: task.xpBonus };
}

export function xpEarnedText(xp: number | undefined): string | null {
  return xp && xp > 0 ? `+${xp} Basil earned` : null;
}

/** Keep answer choices stable for a task while varying their position between questions. */
export function choiceOrder<T>(options: readonly T[], seed: string, value: (option: T) => string): T[] {
  const rank = (input: string) => {
    let hash = 2166136261;
    for (const character of `${seed}:${input}`) {
      hash ^= character.charCodeAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  };
  return options
    .map((option, index) => ({ option, index, rank: rank(value(option)) }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map(({ option }) => option);
}

export function practiceStages(tasks: SessionTask[]) {
  const ordered = [...tasks].sort((a, b) => a.orderIndex - b.orderIndex);
  return {
    learning: ordered.filter(task => task.kind !== "ispyRound" && task.kind !== "reflection"),
    clues: ordered.filter(task => task.kind === "ispyRound"),
    reflection: ordered.filter(task => task.kind === "reflection"),
  };
}

/** Progress for the required learning path. I-Spy and reflection are optional extras. */
export function learningProgress(tasks: SessionTask[]) {
  const learning = practiceStages(tasks).learning;
  return {
    completed: learning.filter(taskDone).length,
    total: learning.length,
  };
}

export function taskTitle(task: SessionTask) {
  const content = task.publicContent;
  if ("title" in content) return content.title;
  const labels: Partial<Record<SessionTask["kind"], string>> = {
    grammarPractice: "Practise grammar",
    sentenceBuilding: "Build a sentence", ispyRound: "Linguini clues", reflection: "Your reflection",
  };
  return labels[task.kind] ?? "Practise";
}

export function taskDescription(task: SessionTask) {
  const content = task.publicContent;
  if ("prompt" in content) return content.prompt;
  if (content.kind === "grammarLesson") return content.explanation ?? `${content.questions.length} questions`;
  if ("explanation" in content) return content.explanation;
  if (content.kind === "vocabularyIntroduction") {
    if (content.words?.length) return `${content.words.length} words from your scene`;
    return `${content.targetText ?? "Vocabulary"} · ${content.translation ?? "Review"}`;
  }
  return content.clue;
}

export const isMissionSession = (tasks: SessionTask[]) =>
  tasks.some(task => task.publicContent.missionId);

/** Missions finish after learning; I-Spy is a separate, optional game. */
export const finishesAfterLearning = (tasks: SessionTask[]) => isMissionSession(tasks);

export type LearningStep = { to: "task"; taskId: string } | { to: "tasks" } | { to: "ispy" } | { to: "finish" };

/**
 * Where Next leads after a learning task. Tasks can be opened in any order, so the
 * last one only finishes the lesson (or opens I-Spy) once every learning task is done;
 * otherwise the learner returns to the task list instead of a completion the server rejects.
 */
export function nextLearningStep(tasks: SessionTask[], currentId: string, generating: boolean,
  done: (task: SessionTask) => boolean = taskDone): LearningStep {
  const learning = practiceStages(tasks).learning;
  const index = learning.findIndex(task => task.id === currentId);
  const next = index < 0 ? undefined : learning[index + 1];
  if (next) return { to: "task", taskId: next.id };
  if (index < 0 || generating || !learning.every(task => task.id === currentId || done(task))) return { to: "tasks" };
  return finishesAfterLearning(tasks) ? { to: "finish" } : { to: "ispy" };
}

/** Saved mission order when the backend persisted it; otherwise a stable per-question shuffle. */
export function questionOptions(question: Pick<GrammarLessonQuestion, "options" | "keepOptionOrder">, seed: string) {
  return question.keepOptionOrder ? [...question.options] : choiceOrder(question.options, seed, option => option.optionId);
}

/** The photo markers a marker question offers, numbered as on the review screen. */
export function markerChoices(question: Pick<GrammarLessonQuestion, "options" | "markerObjectIds">, scene: Pick<Scene, "items">) {
  const objects = question.markerObjectIds ?? {};
  return question.options.flatMap(option => {
    const item = scene.items.find(candidate => candidate.id === objects[option.optionId]);
    // The saved label is the object's number on the review screen.
    return item ? [{ option, item: { ...item, marker: Number(option.label) || item.marker } }] : [];
  }) satisfies { option: GrammarLessonQuestion["options"][number]; item: LanguageItem }[];
}

/** How an option reads on screen: marker options name their photo marker. */
export const optionText = (question: Pick<GrammarLessonQuestion, "markerObjectIds">, label: string) =>
  question.markerObjectIds ? `Marker ${label}` : label;

/** The learner's sentence from word tiles: punctuation and elided words join their neighbour. */
export const builtSentence = (tokens: readonly string[], joinModes?: readonly ("space" | "none")[] | null) => tokens.reduce((value, token, index) => {
  if (joinModes) return value + (index && joinModes[index] === "space" ? " " : "") + token;
  const joinsPrevious = /^[,.;:!?…]$/.test(token) || value.endsWith("'");
  return value ? `${value}${joinsPrevious ? "" : " "}${token}` : token;
}, "");

export const sentenceEnding = (answer: string) => /[.!?]$/.test(answer) ? "" : ".";

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

/** A mission session with no I-Spy rounds finishes after its last learning task. */
export const finishesWithoutISpy = (tasks: SessionTask[]) =>
  tasks.some(task => task.publicContent.missionId) && !tasks.some(task => task.kind === "ispyRound" || task.kind === "reflection");

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
export const builtSentence = (tokens: readonly string[]) => tokens.reduce((value, token) => {
  const joinsPrevious = /^[,.;:!?…]$/.test(token) || value.endsWith("'");
  return value ? `${value}${joinsPrevious ? "" : " "}${token}` : token;
}, "");

import type { SessionTask } from "./api";

export const taskDone = (task: SessionTask) => task.status === "completed" || task.status === "skipped";

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
  if ("explanation" in content) return content.explanation;
  if (content.kind === "vocabularyIntroduction") {
    if (content.words?.length) return `${content.words.length} words from your scene`;
    return `${content.targetText ?? "Vocabulary"} · ${content.translation ?? "Review"}`;
  }
  return content.clue;
}

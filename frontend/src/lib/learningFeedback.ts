export type LearningFeedbackEvent = "correct" | "incorrect" | "saved" | "start" | "completed" | "preparing";

const phrases: Record<LearningFeedbackEvent, readonly string[]> = {
  correct: ["Perfectly cooked!", "Al dente!", "Chef’s kiss!"],
  incorrect: ["Every chef adjusts the recipe.", "No worries, mistakes add flavor.", "A small slip, a useful lesson."],
  saved: ["Every try adds flavor.", "Practice makes pasta."],
  start: ["Let’s get cooking!", "Your next dish awaits.", "Time to add a new flavor."],
  completed: ["Dish complete!", "That’s one for the recipe book.", "Come back hungry for more."],
  preparing: ["Preparing your next course…", "Warming up the kitchen…"],
};

/** Keep the same wording when a saved result is restored or a request is retried. */
export function learningFeedback(event: LearningFeedbackEvent, identity: string): string {
  let hash = 0;
  for (const character of `${event}:${identity}`) hash = (Math.imul(hash, 31) + character.charCodeAt(0)) >>> 0;
  const options = phrases[event];
  return options[hash % options.length];
}

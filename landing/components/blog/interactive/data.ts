/**
 * Numbers behind the interactive charts. They come from marketing/business-model/model/cost_model.py
 * and its unit-economics.json (OpenRouter prices and the measured tokens from MODEL_COMPARISON.md);
 * rerun that model and update these together.
 */

export type Pipeline = "chosen" | "fallback" | "budget";

export const pipelineLabels: Record<Pipeline, string> = {
  chosen: "Chosen models",
  fallback: "If a provider fails",
  budget: "Cheapest alternatives",
};

export type LessonStep = { id: string; name: string; tokens: string; model: Record<Pipeline, string>; cost: Record<Pipeline, number> };

/** One own-photo lesson: expected cost per call, retries included. Tokens are the chosen model's measured means. */
export const lessonSteps: LessonStep[] = [
  {
    id: "moderation", name: "Moderation", tokens: "one image",
    model: { chosen: "omni-moderation", fallback: "omni-moderation", budget: "omni-moderation" },
    cost: { chosen: 0, fallback: 0, budget: 0 },
  },
  {
    id: "scene", name: "Scene analysis", tokens: "3,375 in · 664 out",
    model: { chosen: "claude-haiku-4.5", fallback: "gpt-4o", budget: "gpt-4.1-mini" },
    cost: { chosen: 0.00736, fallback: 0.01102, budget: 0.00229 },
  },
  {
    id: "translation", name: "Translation", tokens: "648 in · 216 out",
    model: { chosen: "gpt-4o-mini", fallback: "mistral-small", budget: "gpt-4o-mini" },
    cost: { chosen: 0.00025, fallback: 0.00026, budget: 0.00025 },
  },
  {
    id: "tasks", name: "Learning tasks", tokens: "2,831 in · 1,597 out",
    model: { chosen: "gpt-5.4-mini", fallback: "gpt-4.1-mini", budget: "gpt-4.1-mini" },
    cost: { chosen: 0.01024, fallback: 0.00454, budget: 0.00454 },
  },
  {
    id: "clues", name: "I-Spy clues", tokens: "938 in · 124 out",
    model: { chosen: "gemini-3.1-flash-lite", fallback: "gpt-4o-mini", budget: "gpt-4o-mini" },
    cost: { chosen: 0.00046, fallback: 0.00022, budget: 0.00022 },
  },
  {
    id: "guess", name: "I-Spy guesses", tokens: "3 × 1,025 in · 70 out",
    model: { chosen: "gpt-4.1-mini", fallback: "gemini-3.5-flash-lite", budget: "gpt-4o-mini" },
    cost: { chosen: 0.00172, fallback: 0.00178, budget: 0.00063 },
  },
];

/** Blended monthly AI and storage cost per learner (free mix 50/35/15, Plus mix 80/20). */
export const learnerCost: Record<Pipeline, { free: number; plus: number; casual: number; cap: number; typical: number }> = {
  chosen: { free: 0.18, plus: 1.028, casual: 0.17, cap: 0.64, typical: 0.74 },
  fallback: { free: 0.162, plus: 0.936, casual: 0.16, cap: 0.58, typical: 0.68 },
  budget: { free: 0.075, plus: 0.506, casual: 0.07, cap: 0.27, typical: 0.37 },
};

/** Net monthly revenue per payer after Stripe fees, 59% annual ($49.99) and 41% monthly ($7.99). */
export const NET_ARPU = 5.2404;

export function fixedCost(monthlyUsers: number): number {
  return monthlyUsers > 10_000 ? 70 : 52;
}

export function monthlyResult(users: number, conversion: number, pipeline: Pipeline) {
  const payers = users * conversion;
  const revenue = payers * NET_ARPU;
  const ai = (users - payers) * learnerCost[pipeline].free + payers * learnerCost[pipeline].plus;
  const fixed = fixedCost(users);
  return { payers, revenue, ai, fixed, result: revenue - ai - fixed };
}

export function breakEvenConversion(users: number, pipeline: Pipeline): number {
  const { free, plus } = learnerCost[pipeline];
  // c·u·(arpu − plus) = (1 − c)·u·free + fixed
  return (users * free + fixedCost(users)) / (users * (NET_ARPU - plus + free));
}

export const usd = (value: number, digits = 0) =>
  `${value < 0 ? "−" : ""}$${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

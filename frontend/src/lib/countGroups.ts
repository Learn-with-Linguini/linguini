import type { CountedGroup } from "./api";

export const MIN_COUNT = 1;
export const MAX_COUNT = 10;
const NUMBER_WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];

export interface CountGroup { key: string; label: string; objectIds: string[]; suggested: number | null }
interface CountableObject { id: string; label: string; attributes?: Record<string, unknown> | null }

const groupKey = (label: string) => label.trim().toLowerCase();

/** A scene-analysis quantity read as 1–10; it is only ever offered for the learner to confirm. */
export function suggestedCount(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const word = value.trim().toLowerCase().split(/\s+/)[0] ?? "";
  const number = /^\d+$/.test(word) ? Number(word) : NUMBER_WORDS.indexOf(word) + 1;
  return number >= MIN_COUNT && number <= MAX_COUNT ? number : null;
}

/** One group per object name, so matching objects are counted once together. */
export function countGroups(objects: CountableObject[]): CountGroup[] {
  const groups = new Map<string, CountGroup>();
  for (const object of objects) {
    const key = groupKey(object.label);
    if (!key) continue;
    const group = groups.get(key) ?? { key, label: object.label.trim(), objectIds: [], suggested: null };
    group.objectIds.push(object.id);
    group.suggested ??= suggestedCount(object.attributes?.quantity);
    groups.set(key, group);
  }
  return [...groups.values()];
}

export function savedCounts(saved: CountedGroup[] | undefined): Record<string, string> {
  return Object.fromEntries((saved ?? []).map(group => [groupKey(group.label), String(group.quantity)]));
}

export function countError(value: string | undefined): string | null {
  if (!value?.trim()) return null;
  const number = Number(value);
  return Number.isInteger(number) && number >= MIN_COUNT && number <= MAX_COUNT
    ? null : `Counts go from ${MIN_COUNT} to ${MAX_COUNT}.`;
}

/** The review's counts, keyed by the first object of each counted group. */
export function objectCounts(groups: CountGroup[], counts: Record<string, string>): Record<string, number> {
  return Object.fromEntries(groups
    .filter(group => counts[group.key]?.trim() && !countError(counts[group.key]))
    .map(group => [group.objectIds[0], Number(counts[group.key])]));
}

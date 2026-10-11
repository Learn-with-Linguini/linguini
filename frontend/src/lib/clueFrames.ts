import type { ClueAssistance, ClueFrame, ClueFrameId } from "./api";

const fold = (text: string) => text.toLocaleLowerCase().normalize("NFKD").replace(/\p{M}/gu, "");
const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const squeeze = (word: string) => word.replace(/(\p{L})\1+/gu, "$1");

function oneEdit(a: string, b: string): boolean {
  if (Math.abs(a.length - b.length) > 1) return false;
  if (a.length > b.length) [a, b] = [b, a];
  let i = 0;
  while (i < a.length && a[i] === b[i]) i += 1;
  return a.slice(i + (a.length === b.length ? 1 : 0)) === b.slice(i + 1);
}

/** Mirrors the backend precheck: whole words ignoring case and accents, plus one-letter misspellings of 4+ letter words. */
export function mentionsTarget(text: string, avoidWords: string[]): boolean {
  const folded = fold(text);
  const tokens = (folded.match(/[\p{L}\p{N}_]+/gu) ?? []).map(squeeze);
  return avoidWords.some(word => {
    const parts = fold(word).split(/\s+/).filter(Boolean);
    if (!parts.length) return false;
    if (new RegExp(`(?<![\\p{L}\\p{N}_])${parts.map(escape).join("\\s+")}(?![\\p{L}\\p{N}_])`, "u").test(folded)) return true;
    if (parts.length !== 1 || parts[0].length < 4) return false;
    const form = squeeze(parts[0]);
    return tokens.some(token => token.length >= 4 && oneEdit(form, token));
  });
}

/** The sentence each frame last wrote, so frames sharing a prefix ("Elle est") stay separate. */
export type FrameSentences = Partial<Record<ClueFrameId, string>>;
export interface Composition { text: string; sentences: FrameSentences }

/** Start of the last whole sentence equal to ``sentence``, or -1 once the learner edited it. */
function sentenceStart(text: string, sentence: string | undefined): number {
  if (!sentence) return -1;
  const matches = [...text.matchAll(new RegExp(`(^|[.!?]\\s+)(${escape(sentence)})(?=\\s*(?:[.!?]|$))`, "gu"))];
  const last = matches.at(-1);
  return last ? (last.index ?? 0) + last[1].length : -1;
}

function append(text: string, sentence: string): string {
  const base = text.trimEnd();
  const separator = !base ? "" : /[.!?]$/.test(base) ? " " : ". ";
  return `${base}${separator}${sentence}`;
}

/** Starts this frame's sentence once; other frames and free-typed text are untouched. */
export function applyFrame({ text, sentences }: Composition, frame: ClueFrame): Composition {
  if (sentenceStart(text, sentences[frame.frameId]) >= 0) return { text, sentences };
  return { text: `${append(text, frame.prefix)} `, sentences: { ...sentences, [frame.frameId]: frame.prefix } };
}

/** Fills this frame's own sentence with a chip, replacing only what that frame wrote before. */
export function fillSlot({ text, sentences }: Composition, frame: ClueFrame, chip: string): Composition {
  const sentence = `${frame.prefix} ${chip}`;
  const previous = sentences[frame.frameId];
  const start = sentenceStart(text, previous);
  const next = start < 0 ? append(text, sentence)
    : `${text.slice(0, start)}${sentence}${text.slice(start + (previous ?? "").length).replace(/^\s+$/, "")}`;
  return { text: next, sentences: { ...sentences, [frame.frameId]: sentence } };
}

/** Finds each frame's sentence again in a restored clue, using the chips it saved. */
export function restoreSentences(text: string, frames: ClueFrame[], chips: string[]): FrameSentences {
  const sentences: FrameSentences = {};
  for (const frame of frames) {
    const found = frame.chips.filter(chip => chips.includes(chip)).map(chip => `${frame.prefix} ${chip}`)
      .find(sentence => sentenceStart(text, sentence) >= 0);
    if (found) sentences[frame.frameId] = found;
  }
  return sentences;
}

/** Frames shown to the learner; saved Name frames from older tasks are no longer offered. */
export const visibleFrames = (frames: ClueFrame[] | undefined) => (frames ?? []).filter(frame => frame.frameId !== "name");

const FRAME_IDS: ClueFrameId[] = ["name", "colour", "location"];
const frameIds = (value: unknown) => Array.isArray(value) ? value.filter((id): id is ClueFrameId => FRAME_IDS.includes(id)) : [];
const strings = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

/** Reads the assistance saved in an attempt's responsePayload (stored with snake_case keys). */
export function savedAssistance(payload: Record<string, unknown> | null | undefined): Pick<ClueAssistance, "selectedFrameIds" | "insertedChips"> | null {
  const saved = payload?.assistance;
  if (!saved || typeof saved !== "object") return null;
  const record = saved as Record<string, unknown>;
  return {
    selectedFrameIds: frameIds(record.selected_frame_ids ?? record.selectedFrameIds),
    insertedChips: strings(record.inserted_chips ?? record.insertedChips),
  };
}

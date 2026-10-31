import type { ClueAssistance, ClueFrame, ClueFrameId, ClueSlotChoice, ClueSlotId } from "./api";

const fold = (text: string) => text.toLocaleLowerCase().normalize("NFKD").replace(/\p{M}/gu, "");
const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const squeeze = (word: string) => word.replace(/(\p{L})\1+/gu, "$1");
const wholePhrase = (parts: string[]) => new RegExp(`(?<![\\p{L}\\p{N}_])${parts.map(escape).join("\\s+")}(?![\\p{L}\\p{N}_])`, "u");
const formParts = (word: string) => fold(word).split(/\s+/).filter(Boolean);

function oneEdit(a: string, b: string): boolean {
  if (Math.abs(a.length - b.length) > 1) return false;
  if (a.length > b.length) [a, b] = [b, a];
  let i = 0;
  while (i < a.length && a[i] === b[i]) i += 1;
  return a.slice(i + (a.length === b.length ? 1 : 0)) === b.slice(i + 1);
}

/** Mirrors the backend precheck: whole target forms ignoring case and accents. Blocks sending. */
export function mentionsTarget(text: string, avoidWords: string[]): boolean {
  const folded = fold(text);
  return avoidWords.some(word => {
    const parts = formParts(word);
    return parts.length > 0 && wholePhrase(parts).test(folded);
  });
}

/** A word one letter off (or with repeated letters) from a 4+ letter target form: only a soft warning. */
export function nearTarget(text: string, avoidWords: string[]): boolean {
  const exact = new Set(avoidWords.map(fold));
  const tokens = (fold(text).match(/[\p{L}\p{N}_]+/gu) ?? []).filter(token => !exact.has(token));
  return avoidWords.some(word => {
    const parts = formParts(word);
    if (parts.length !== 1 || parts[0].length < 4) return false;
    return tokens.some(token => token.length >= 4
      && (oneEdit(parts[0], token) || squeeze(token) === squeeze(parts[0])));
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

/** Replaces only what this frame wrote before; other frames and free-typed text are untouched. */
export function writeSentence({ text, sentences }: Composition, frameId: ClueFrameId, sentence: string): Composition {
  const previous = sentences[frameId];
  const start = sentenceStart(text, previous);
  const next = start < 0 ? append(text, sentence)
    : `${text.slice(0, start)}${sentence}${text.slice(start + (previous ?? "").length).replace(/^\s+$/, "")}`;
  return { text: next, sentences: { ...sentences, [frameId]: sentence } };
}

/** Writes a complete phrase (legacy chip or revealed help) as this frame's sentence. */
export const fillSlot = (composition: Composition, frame: ClueFrame, chip: string) =>
  writeSentence(composition, frame.frameId, `${frame.prefix} ${chip}`);

export type SlotPicks = Partial<Record<ClueSlotId, string>>;
export type SlotChoices = Partial<Record<ClueFrameId, SlotPicks>>;

/** The frame's sentence from its slot picks, using the server's composed phrase so contractions stay right. */
export function slotSentence(frame: ClueFrame, picks: SlotPicks): string {
  const { position, reference, colour } = picks;
  const body = colour ?? (position && reference
    ? frame.phrases?.[`${position}|${reference}`] ?? `${position} ${reference}`
    : [position, reference].filter(Boolean).join(" "));
  return body ? `${frame.prefix} ${body}` : frame.prefix;
}

export const choicesFromSlots = (slots: ClueSlotChoice[]): SlotChoices =>
  slots.reduce<SlotChoices>((all, { frameId, slotId, chip }) => ({ ...all, [frameId]: { ...all[frameId], [slotId]: chip } }), {});

export const slotsFromChoices = (choices: SlotChoices): ClueSlotChoice[] =>
  (Object.entries(choices) as [ClueFrameId, SlotPicks | undefined][]).flatMap(([frameId, picks]) =>
    (Object.entries(picks ?? {}) as [ClueSlotId, string][]).map(([slotId, chip]) => ({ frameId, slotId, chip })));

/** Finds each frame's sentence again in a restored clue, from its saved phrases or slot picks. */
export function restoreSentences(text: string, frames: ClueFrame[], chips: string[], choices: SlotChoices = {}): FrameSentences {
  const sentences: FrameSentences = {};
  for (const frame of frames) {
    const candidates = [...frame.chips, ...(frame.help ?? [])].filter(chip => chips.includes(chip)).map(chip => `${frame.prefix} ${chip}`);
    if (choices[frame.frameId]) candidates.unshift(slotSentence(frame, choices[frame.frameId] ?? {}));
    const found = candidates.find(sentence => sentenceStart(text, sentence) >= 0);
    if (found) sentences[frame.frameId] = found;
  }
  return sentences;
}

/** Frames shown to the learner; saved Name frames from older tasks are no longer offered. */
export const visibleFrames = (frames: ClueFrame[] | undefined) => (frames ?? []).filter(frame => frame.frameId !== "name");

const FRAME_IDS: ClueFrameId[] = ["name", "colour", "location"];
const frameIds = (value: unknown) => Array.isArray(value) ? value.filter((id): id is ClueFrameId => FRAME_IDS.includes(id)) : [];
const strings = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

const SLOT_IDS: ClueSlotId[] = ["position", "reference", "colour"];
const slotChoices = (value: unknown): ClueSlotChoice[] => Array.isArray(value) ? value.flatMap(item => {
  const record = (item ?? {}) as Record<string, unknown>;
  const frameId = record.frame_id ?? record.frameId, slotId = record.slot_id ?? record.slotId, chip = record.chip;
  return FRAME_IDS.includes(frameId as ClueFrameId) && SLOT_IDS.includes(slotId as ClueSlotId) && typeof chip === "string"
    ? [{ frameId: frameId as ClueFrameId, slotId: slotId as ClueSlotId, chip }] : [];
}) : [];

type SavedAssistance = Pick<ClueAssistance, "selectedFrameIds" | "insertedChips"> & Required<Pick<ClueAssistance, "selectedSlots" | "revealedHelpFrameIds" | "revealedMeaningFrameIds" | "wordBankShown" | "cheatSheetOpened">>;

/** Reads the assistance saved in an attempt's responsePayload (stored with snake_case keys). */
export function savedAssistance(payload: Record<string, unknown> | null | undefined): SavedAssistance | null {
  const saved = payload?.assistance;
  if (!saved || typeof saved !== "object") return null;
  const record = saved as Record<string, unknown>;
  return {
    selectedFrameIds: frameIds(record.selected_frame_ids ?? record.selectedFrameIds),
    insertedChips: strings(record.inserted_chips ?? record.insertedChips),
    selectedSlots: slotChoices(record.selected_slots ?? record.selectedSlots),
    revealedHelpFrameIds: frameIds(record.revealed_help_frame_ids ?? record.revealedHelpFrameIds),
    revealedMeaningFrameIds: frameIds(record.revealed_meaning_frame_ids ?? record.revealedMeaningFrameIds),
    wordBankShown: (record.word_bank_shown ?? record.wordBankShown) === true,
    cheatSheetOpened: (record.cheat_sheet_opened ?? record.cheatSheetOpened) === true,
  };
}

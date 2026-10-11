import type { ClueAssistance, ClueFrame, ClueFrameId } from "./api";

const fold = (text: string) => text.toLocaleLowerCase().normalize("NFKD").replace(/\p{M}/gu, "");
const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Mirrors the backend precheck: whole words, ignoring case and accents. */
export function mentionsTarget(text: string, avoidWords: string[]): boolean {
  const folded = fold(text);
  return avoidWords.some(word => {
    const parts = fold(word).split(/\s+/).filter(Boolean);
    return parts.length > 0
      && new RegExp(`(?<![\\p{L}\\p{N}_])${parts.map(escape).join("\\s+")}(?![\\p{L}\\p{N}_])`, "u").test(folded);
  });
}

function prefixStart(text: string, prefix: string): number {
  const matches = [...text.matchAll(new RegExp(`(^|[.!?]\\s+)(${escape(prefix)})(?=\\s|$)`, "giu"))];
  const last = matches.at(-1);
  return last ? (last.index ?? 0) + last[1].length : -1;
}

/** Starts a sentence with the frame prefix unless the clue already has one. */
export function applyFrame(text: string, frame: ClueFrame): string {
  if (prefixStart(text, frame.prefix) >= 0) return text;
  const base = text.trimEnd();
  const separator = !base ? "" : /[.!?]$/.test(base) ? " " : ". ";
  return `${base}${separator}${frame.prefix} `;
}

/** Puts a chip into the frame's slot, replacing whatever filled that slot before. */
export function fillSlot(text: string, frame: ClueFrame, chip: string): string {
  const framed = applyFrame(text, frame);
  const slot = prefixStart(framed, frame.prefix) + frame.prefix.length;
  const rest = framed.slice(slot);
  const end = rest.search(/[.!?]/);
  return `${framed.slice(0, slot)} ${chip}${end < 0 ? "" : rest.slice(end)}`;
}

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

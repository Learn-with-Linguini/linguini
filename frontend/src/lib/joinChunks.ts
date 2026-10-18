import type { SentenceChunk } from "./api";

export function joinChunks(chunks: readonly SentenceChunk[]): string {
  if (!chunks.length) return "";
  return chunks[0].text + chunks.slice(1).map(chunk =>
    `${chunk.join === "space" ? " " : ""}${chunk.text}`,
  ).join("");
}

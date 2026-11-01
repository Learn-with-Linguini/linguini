import type { ClueFrame, WordBankKind } from "../lib/api";
import "./ISpyLevelHelp.css";

// The clue frame templates name their slots in brackets ("C'est [colour]",
// "Il est [position] [reference object]"); each slot reads as a word-bank kind.
const SLOT_KINDS: Record<string, { kind: WordBankKind; label: string }> = {
  colour: { kind: "adjective", label: "adjective" },
  position: { kind: "preposition", label: "preposition" },
  "reference object": { kind: "noun", label: "object" },
};

/** A cheatsheet of where the adjective and preposition go in this language's clue sentences. */
export function ClueFramePatterns({ frames, languageCode }: { frames: ClueFrame[]; languageCode: string }) {
  const patterns = frames.filter(frame => frame.template && frame.frameId !== "name");
  if (!patterns.length) return null;
  return <section className="clue-patterns" aria-labelledby="clue-patterns-title">
    <h3 id="clue-patterns-title" className="ispy-help__title">How to build your clue</h3>
    <ul className="clue-patterns__list">
      {patterns.map(frame => <li key={frame.frameId} className="clue-patterns__item">
        <p className="clue-patterns__sentence">{frame.template!.split(/(\[[^\]]+\])/).filter(Boolean).map((part, index) => {
          const slot = SLOT_KINDS[part.replace(/^\[|\]$/g, "")];
          return slot && part.startsWith("[")
            ? <span key={index} className={`clue-patterns__pill ispy-help__word--${slot.kind}`}>{slot.label}</span>
            : <span key={index} lang={languageCode}>{part.trim()}</span>;
        })}</p>
        <p className="small muted">Example: <span lang={languageCode}>{frame.example}</span></p>
      </li>)}
    </ul>
  </section>;
}

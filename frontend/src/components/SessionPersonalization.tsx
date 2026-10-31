import { useId } from "react";
import type { PracticeFocus, SessionPersonalization as Personalization } from "../lib/api";
import { Card } from "./ui";

const focusLabels: Record<PracticeFocus, string> = {
  genderNumberAgreement: "matching word endings",
  pluralNounForm: "talking about more than one",
  sceneDescription: "describing what you see",
  chainedDescription: "joining short descriptions",
};

export function SessionPersonalization({ personalization, languageCode }: { personalization?: Personalization | null; languageCode?: string }) {
  const titleId = useId();
  if (!personalization || (!personalization.returningWords.length && !personalization.practiceFocuses.length)) return null;

  return <aside aria-labelledby={titleId}>
    <Card plain className="stack-2">
      <h2 id={titleId} className="small">Building on earlier practice</h2>
      {personalization.previousSessions > 0
        ? <p className="small muted">Based on {personalization.previousSessions} completed {personalization.previousSessions === 1 ? "session" : "sessions"}.</p>
        : null}
      {personalization.returningWords.length ? <div className="stack-2">
        <div className="translation-preview__terms" role="list" aria-label="Words saved from earlier photos">
          {personalization.returningWords.map((item, index) => <span className="translation-preview__term" role="listitem" key={`${item.word}:${index}`}>
            <strong lang={languageCode}>{item.word}</strong><span className="small">{item.needsReview ? "Review again" : "Saved before"}</span>
          </span>)}
        </div>
      </div> : null}
      {personalization.practiceFocuses.length ? <p className="small">Revisiting: {personalization.practiceFocuses.map(focus => focusLabels[focus]).join(", ")}.</p> : null}
    </Card>
  </aside>;
}

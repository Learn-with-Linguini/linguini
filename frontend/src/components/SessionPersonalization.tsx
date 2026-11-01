import { useId } from "react";
import type { SessionPersonalization as Personalization } from "../lib/api";
import { Card } from "./ui";

/** Words from earlier photos, shown as target-language pills. */
export function SessionPersonalization({ personalization, languageCode }: { personalization?: Personalization | null; languageCode?: string }) {
  const titleId = useId();
  if (!personalization?.returningWords.length) return null;

  return <aside aria-labelledby={titleId}>
    <Card plain className="stack-2">
      <h2 id={titleId} className="known-words__title">Words you already know</h2>
      <ul className="known-words" aria-labelledby={titleId}>
        {personalization.returningWords.map((item, index) => <li className="known-words__pill" key={`${item.word}:${index}`} lang={languageCode}>{item.word}</li>)}
      </ul>
    </Card>
  </aside>;
}

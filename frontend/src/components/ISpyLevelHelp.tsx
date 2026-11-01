import { useId, useRef, useState } from "react";
import type { ISpyLevelSupport } from "../lib/api";
import { trackAction } from "../lib/analytics";
import { MissionCheatSheetLauncher } from "./MissionCheatSheet";
import { Button } from "./ui";
import "./ISpyLevelHelp.css";

/** Scene vocabulary for every learner; A1/A2 may reveal it when they need support. */
export function ISpyLevelHelp({ support, languageCode }: { support: ISpyLevelSupport; languageCode: string }) {
  const words = support.wordBank ?? [];
  const sheet = support.cheatSheet;
  const collapsible = support.learnerLevel === "A1" || support.learnerLevel === "A2";
  const [wordsShown, setWordsShown] = useState(!collapsible);
  const viewed = useRef(new Set<string>());
  const idPrefix = useId();
  // Hovering, focusing or tapping a word shows its English; each word is logged once.
  const showMeaning = (text: string) => {
    if (viewed.current.has(text)) return;
    viewed.current.add(text);
    trackAction("ispy_word_bank_translation_viewed", { learnerLevel: support.learnerLevel });
  };
  if (!words.length && !sheet) return null;
  return <section className="ispy-help" aria-label="Word help">
    {/* Collapsed, only the centred "Show word bank" action shows; the title appears with the words. */}
    <div className={`ispy-help__heading${wordsShown && words.length ? "" : " ispy-help__heading--collapsed"}`}>
      {wordsShown && words.length ? <span className="ispy-help__title">Word bank</span> : null}
      <div className="ispy-help__actions">
        {words.length && collapsible ? <Button variant="quiet" aria-expanded={wordsShown} onClick={() => {
          const next = !wordsShown;
          setWordsShown(next);
          trackAction("ispy_word_bank_toggled", { learnerLevel: support.learnerLevel, shown: next });
        }}>{wordsShown ? "Hide word bank" : "Show word bank"}</Button> : null}
        {sheet ? <MissionCheatSheetLauncher missionId={sheet.missionId} practiceLevel={sheet.practiceLevel}
          contentVersion={sheet.contentVersion} languageCode={languageCode} /> : null}
      </div>
    </div>
    {words.length && wordsShown ? <ul className="ispy-help__words">
      {words.map((word, index) => <li key={word.text}>
        <button type="button" className="ispy-help__word" aria-describedby={`${idPrefix}-${index}`}
          onMouseEnter={() => showMeaning(word.text)} onFocus={() => showMeaning(word.text)}>
          <strong lang={languageCode}>{word.text}</strong>
          <span id={`${idPrefix}-${index}`} className="ispy-help__meaning" role="tooltip">{word.translation}</span>
        </button>
      </li>)}
    </ul> : null}
  </section>;
}

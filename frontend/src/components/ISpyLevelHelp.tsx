import { useState } from "react";
import type { ISpyLevelSupport } from "../lib/api";
import { trackAction } from "../lib/analytics";
import { MissionCheatSheetLauncher } from "./MissionCheatSheet";
import { Button } from "./ui";
import "./ISpyLevelHelp.css";

/** Scene vocabulary for every learner; A1/A2 may reveal it when they need support. */
export function ISpyLevelHelp({ support, languageCode, wordsShown: controlledWordsShown, onWordsShownChange, onAssistance }: {
  support: ISpyLevelSupport; languageCode: string; wordsShown?: boolean;
  onWordsShownChange?: (shown: boolean) => void;
  onAssistance?: (kind: "wordBank" | "cheatSheet") => void;
}) {
  const words = support.wordBank ?? [];
  const sheet = support.cheatSheet;
  const collapsible = support.learnerLevel === "A1" || support.learnerLevel === "A2";
  const [localWordsShown, setLocalWordsShown] = useState(!collapsible);
  const wordsShown = controlledWordsShown ?? localWordsShown;
  if (!words.length && !sheet) return null;
  return <section className="ispy-help" aria-label="Word help">
    <div className="ispy-help__heading">
      <span className="label muted">Word bank</span>
      <div className="ispy-help__actions">
        {words.length && collapsible ? <Button variant="quiet" aria-expanded={wordsShown} onClick={() => {
          const next = !wordsShown;
          if (onWordsShownChange) onWordsShownChange(next);
          else setLocalWordsShown(next);
          if (next) onAssistance?.("wordBank");
          trackAction("ispy_word_bank_toggled", { learnerLevel: support.learnerLevel, shown: next });
        }}>{wordsShown ? "Hide word bank" : "Show word bank"}</Button> : null}
        {sheet ? <MissionCheatSheetLauncher missionId={sheet.missionId} practiceLevel={sheet.practiceLevel}
          contentVersion={sheet.contentVersion} languageCode={languageCode}
          onOpen={() => onAssistance?.("cheatSheet")} /> : null}
      </div>
    </div>
    {words.length && wordsShown ? <ul className="ispy-help__words">
      {words.map(word => <li key={word.text}>
        <strong lang={languageCode}>{word.text}</strong>
        <span>{word.translation}</span>
      </li>)}
    </ul> : null}
  </section>;
}

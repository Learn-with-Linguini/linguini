import type { ISpyLevelSupport } from "../lib/api";
import { MissionCheatSheetLauncher } from "./MissionCheatSheet";
import "./ISpyLevelHelp.css";

/** A0 help beside an I-Spy round: the scene's words with their meanings, and the cheatsheet. */
export function ISpyLevelHelp({ support, languageCode }: { support: ISpyLevelSupport; languageCode: string }) {
  const words = support.wordBank ?? [];
  const sheet = support.cheatSheet;
  if (!words.length && !sheet) return null;
  return <section className="ispy-help" aria-label="Word help">
    <div className="ispy-help__heading">
      <span className="label muted">Word bank</span>
      {sheet ? <MissionCheatSheetLauncher missionId={sheet.missionId} practiceLevel={sheet.practiceLevel}
        contentVersion={sheet.contentVersion} languageCode={languageCode} /> : null}
    </div>
    {words.length ? <ul className="ispy-help__words">
      {words.map(word => <li key={word.text}>
        <strong lang={languageCode}>{word.text}</strong>
        <span>{word.translation}</span>
      </li>)}
    </ul> : null}
  </section>;
}

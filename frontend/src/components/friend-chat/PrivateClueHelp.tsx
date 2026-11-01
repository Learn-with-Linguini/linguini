import { useState } from "react";
import { getChatHelp } from "../../lib/friendChats";
import type { ChatHelp, ChatRound, ChatSnapshot } from "../../lib/friendChats";
import { trackAction } from "../../lib/analytics";
import { friendlyError } from "../../lib/queryKeys";
import { speak } from "../../lib/speech";
import { Button, Card } from "../ui";
import { InlineLoader } from "../LoadingScreen";
import { MissionCheatSheetLauncher } from "../MissionCheatSheet";

export function PrivateClueHelp({ chat, round }: { chat: ChatSnapshot; round: ChatRound }) {
  const [help, setHelp] = useState<ChatHelp | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [words, setWords] = useState<string[]>([]);
  const load = async () => {
    setOpen(true); if (help || busy) return;
    setBusy(true); setError(null); trackAction("ispy_friend_private_help_opened");
    try { setHelp(await getChatHelp(chat.id, round.id)); }
    catch (reason) { setError(friendlyError(reason)); }
    finally { setBusy(false); }
  };
  return <section className="stack-2 friend-private-help"><Button variant="quiet" aria-expanded={open} onClick={() => open ? setOpen(false) : void load()}>Linguini help · just for you</Button>
    {open ? <Card className="stack"><p className="small muted">Your friend can’t see which help you use.</p>
      {busy ? <InlineLoader compact label="Opening your private help…" /> : null}
      {error ? <><p role="alert">{error}</p><Button variant="secondary" onClick={() => void load()}>Retry private help</Button></> : null}
      {help ? <><p>{help.explanation}</p>{help.hint ? <p>{help.hint}</p> : null}
        <div className="friend-help__words">{help.vocabulary.map(word => <button type="button" key={word.word} aria-expanded={words.includes(word.word)} onClick={() => {
          const shown = !words.includes(word.word);
          setWords(current => current.includes(word.word) ? current.filter(item => item !== word.word) : [...current, word.word]);
          speak(word.word, chat.targetLanguageCode);
          trackAction("ispy_friend_private_word_opened", { shown });
          trackAction("ispy_friend_audio_played", { kind: "word" });
        }}><strong lang={chat.targetLanguageCode}>{word.word}</strong>{words.includes(word.word) ? <span>{word.meaning}</span> : <span className="small muted">Tap for meaning</span>}</button>)}</div>
        {help.cheatsheetRefs.filter(ref => Boolean(ref.contentVersion)).map(ref => <MissionCheatSheetLauncher key={`${ref.missionCode}:${ref.level}:${ref.contentVersion}`}
          missionId={ref.missionCode} practiceLevel={ref.level} contentVersion={ref.contentVersion} languageCode={chat.targetLanguageCode}
          onOpen={() => trackAction("ispy_friend_cheatsheet_opened")} />)}
      </> : null}
    </Card> : null}
  </section>;
}

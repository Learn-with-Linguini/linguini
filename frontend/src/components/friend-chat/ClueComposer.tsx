import { useEffect, useRef, useState } from "react";
import type { ChatClueOption, ChatRound, ChatSnapshot } from "../../lib/friendChats";
import { chatDraftKey, chatRoundIntent, readChatDraft, saveChatDraft } from "../../lib/friendChats";
import { mentionsTarget, nearTarget } from "../../lib/clueFrames";
import { trackAction } from "../../lib/analytics";
import { speak, speechLocale } from "../../lib/speech";
import { Button, Card } from "../ui";
import { MicIcon, SpeakerIcon } from "../icons";
import { MissionCheatSheetLauncher } from "../MissionCheatSheet";

interface ComposerDraft { text: string; selected: string[]; stage: number }
type Command = <T = ChatSnapshot>(intent: string, payload?: Record<string, unknown>) => Promise<T | null>;
const conceptLabels = { adjective: "What does it look like?", position: "Where is it?", quantity: "How many are there?", identity: "Another detail" };
export function composeCluePhrases(options: ChatClueOption[]): string {
  return options.map(option => /[.!?。！？]$/.test(option.text.trim()) ? option.text.trim() : `${option.text.trim()}.`).join(" ");
}

export function ClueComposer({ chat, round, disabled, command, microphoneEnabled, onChangeTarget }: {
  chat: ChatSnapshot; round: ChatRound; disabled: boolean; command: Command; microphoneEnabled: boolean; onChangeTarget?: () => void;
}) {
  const key = chatDraftKey(chat.meId, chat.id, `${round.id}:${round.status}:clue`);
  const [draft, setDraft] = useState<ComposerDraft>(() => readChatDraft(key, { text: "", selected: [], stage: 0 }));
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const beginner = chat.viewerLevel === "A0";
  const followUp = round.status === "awaitingFollowUp";
  const friend = chat.partner?.displayName ?? "Your friend";
  const supported = round.clueOptions.filter(option => option.concept !== "identity");
  const concepts = [...new Set(supported.map(option => option.concept))];
  const groups = beginner ? concepts.map(concept => ({ label: conceptLabels[concept], options: supported.filter(option => option.concept === concept) }))
    : supported.length ? [{ label: "Suggested phrases", options: supported }] : [];
  const selected = draft.selected.map(id => supported.find(option => option.id === id)).filter((option): option is ChatClueOption => Boolean(option));
  const activeSheet = selected.at(-1)?.cheatSheet ?? supported[0]?.cheatSheet;
  const avoid = round.target ? [round.target.word, round.target.translation, round.target.label].filter(Boolean) : [];
  const namesTarget = mentionsTarget(draft.text, avoid);
  const similar = !namesTarget && nearTarget(draft.text, avoid);
  useEffect(() => { saveChatDraft(key, draft); }, [key, draft]);
  useEffect(() => { trackAction("ispy_friend_clue_builder_opened", { level: chat.viewerLevel }); }, [round.id, round.status, chat.viewerLevel]);
  const updatePhrases = (ids: string[]) => {
    const phrases = (keys: string[]) => keys.map(id => supported.find(item => item.id === id)).filter((value): value is ChatClueOption => Boolean(value));
    setDraft(current => {
      const before = composeCluePhrases(phrases(current.selected));
      const after = composeCluePhrases(phrases(ids));
      const added = composeCluePhrases(phrases(ids.filter(id => !current.selected.includes(id))));
      const text = before && current.text.includes(before) ? current.text.replace(before, after).trim()
        : current.text.trim() ? `${current.text.trim()} ${added}`.trim() : after;
      return { ...current, selected: ids, text };
    });
    setReviewing(false);
  };
  const choose = (option: ChatClueOption) => updatePhrases(draft.selected.includes(option.id)
    ? draft.selected.filter(id => id !== option.id) : [...draft.selected, option.id]);
  const move = (index: number, direction: number) => {
    const next = [...draft.selected];
    [next[index], next[index + direction]] = [next[index + direction], next[index]];
    updatePhrases(next);
  };
  const suggest = async () => {
    const result = await command<{ text: string }>(chatRoundIntent(round.id, "suggest"));
    if (result) { setSuggestion(result.text); trackAction("ispy_friend_clue_suggested"); }
  };
  const send = async () => {
    const result = await command(chatRoundIntent(round.id, "clue"), { text: draft.text.trim() });
    if (result) { saveChatDraft(key, null); trackAction(followUp ? "ispy_friend_followup_clue_sent" : "ispy_friend_clue_sent"); }
  };
  const ready = Boolean(draft.text.trim()) && !namesTarget;
  return <Card className="stack friend-composer"><div className="friend-composer__heading"><h2>{followUp ? "Add another clue" : "Build your clue"}</h2>
    {activeSheet ? <MissionCheatSheetLauncher {...activeSheet} languageCode={chat.targetLanguageCode} onOpen={() => trackAction("ispy_friend_cheatsheet_opened")} /> : null}</div>
    <p className="friend-composer__intro">{followUp ? `${friend} hasn’t found it yet. Add a detail that helps them.`
      : `${friend} will see your photo and this clue, then tap the object they think you mean.`}</p>
    {round.target ? <div className="friend-composer__target"><span className="small muted">Your secret object</span>
      <span className="friend-composer__target-word"><strong lang={chat.targetLanguageCode}>{round.target.word}</strong> <span className="small">· {round.target.translation}</span></span>
      {onChangeTarget ? <Button variant="quiet" disabled={disabled} onClick={onChangeTarget}>Change</Button> : null}
      <span className="small muted friend-composer__target-note">Don’t say its name in your clue — that gives it away.</span></div> : null}
    <ol className="friend-composer__steps">
      <li className="stack-2"><h3 className="friend-composer__step"><span aria-hidden="true">1</span>Pick details</h3>
        {groups.length ? <p className="small muted">{beginner ? "Tap one or more phrases. Tap again to remove one." : "Tap a phrase to add it, or write your own in step 2."}</p> : null}
        {groups.map(group => <div key={group.label} className="stack-2"><h4 className="friend-composer__group">{group.label}</h4>
          <div className="friend-composer__choices" role="group" aria-label={group.label}>
            {group.options.map(option => <div key={option.id} className="friend-clue-option"><button type="button" className="friend-clue-option__choice"
              disabled={disabled} aria-pressed={draft.selected.includes(option.id)} onClick={() => choose(option)}>
              <strong lang={chat.targetLanguageCode}>{draft.selected.includes(option.id) ? "✓ " : ""}{option.text}</strong><span className="small">{option.translation}</span></button>
              <Button variant="quiet" aria-label="Hear this phrase" onClick={() => { speak(option.text, chat.targetLanguageCode); trackAction("ispy_friend_audio_played", { kind: "option" }); }}><SpeakerIcon size={18} /></Button></div>)}
          </div></div>)}
        {chat.viewerLevel === "A1" && selected.length > 1 ? <div className="stack-2"><h4 className="friend-composer__group">Put them in order</h4>
          <ul className="friend-composer__selected" aria-label="Your selected details">{selected.map((option, index) => <li key={option.id}><span lang={chat.targetLanguageCode}>{option.text}</span>
            <span className="friend-composer__reorder"><Button variant="quiet" disabled={disabled || index === 0} aria-label={`Move detail ${index + 1} earlier`} onClick={() => move(index, -1)}>↑</Button>
              <Button variant="quiet" disabled={disabled || index + 1 === selected.length} aria-label={`Move detail ${index + 1} later`} onClick={() => move(index, 1)}>↓</Button></span></li>)}</ul></div> : null}
        {suggestion ? <div className="stack-2 friend-composer__suggestion"><span className="small muted">Suggested clue</span><p lang={chat.targetLanguageCode}>{suggestion}</p>
          <Button variant="secondary" disabled={disabled} onClick={() => { setDraft(current => ({ ...current, text: suggestion, selected: [] })); setSuggestion(null); setReviewing(false); }}>Use this suggestion</Button>
          <Button variant="quiet" onClick={() => setSuggestion(null)}>Dismiss suggestion</Button></div> :
          <Button variant="quiet" disabled={disabled} onClick={() => void suggest()}>Stuck? Suggest a clue</Button>}
      </li>
      <li className="stack-2"><h3 className="friend-composer__step"><span aria-hidden="true">2</span>Check your clue</h3>
        <label className="field">{beginner ? "Your clue" : "Your clue (you can edit it)"}<textarea className="input" rows={3} maxLength={500}
          lang={chat.targetLanguageCode} value={draft.text} disabled={disabled || reviewing} readOnly={beginner}
          placeholder={beginner ? "Pick a phrase above to start your clue." : "Pick a phrase above or write your clue here."}
          onChange={event => { setDraft(current => ({ ...current, text: event.target.value })); setReviewing(false); }} /></label>
        <div className="friend-composer__actions"><Button variant="quiet" disabled={!draft.text.trim()} onClick={() => { speak(draft.text, chat.targetLanguageCode); trackAction("ispy_friend_audio_played", { kind: "preview" }); }}><SpeakerIcon size={18} /> Hear your clue</Button></div>
        {!beginner && !["A0", "A1"].includes(chat.viewerLevel) ? <ClueSpeech language={chat.targetLanguageCode} enabled={microphoneEnabled && !disabled && !reviewing}
          onText={text => setDraft(current => ({ ...current, text: `${current.text.trim()} ${text}`.trim().slice(0, 500), selected: [] }))} /> : null}
        {namesTarget ? <p role="alert">This clue includes the object’s name. Describe a different detail before sending.</p> : similar ? <p role="status">Check this wording: it looks similar to the hidden object’s name.</p> : null}
      </li>
      <li className="stack-2"><h3 className="friend-composer__step"><span aria-hidden="true">3</span>Send it</h3>
        {reviewing ? <div className="stack-2 friend-composer__confirm"><p>Send this clue to {friend}? They’ll see it straight away.</p>
          <Button disabled={disabled || !ready} onClick={() => void send()}>Send clue</Button>
          <Button variant="quiet" disabled={disabled} onClick={() => setReviewing(false)}>Keep editing</Button></div> : <>
          {!draft.text.trim() ? <p className="small muted">{beginner ? "Your clue is empty. Pick at least one detail first." : "Your clue is empty. Pick a phrase or write one first."}</p> : null}
          <Button disabled={disabled || !ready} onClick={() => setReviewing(true)}>Review clue</Button></>}
      </li>
    </ol>
  </Card>;
}

interface RecognitionResult { isFinal: boolean; 0: { transcript: string } }
interface Recognition {
  lang: string; continuous: boolean; interimResults: boolean;
  onresult: ((event: { results: ArrayLike<RecognitionResult> }) => void) | null;
  onerror: (() => void) | null; onend: (() => void) | null; start: () => void; stop: () => void;
}
type RecognitionWindow = Window & { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
function ClueSpeech({ language, enabled, onText }: { language: string; enabled: boolean; onText: (text: string) => void }) {
  const recognition = useRef<Recognition | null>(null);
  const canReceive = useRef(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const constructor = (window as RecognitionWindow).SpeechRecognition ?? (window as RecognitionWindow).webkitSpeechRecognition;
  useEffect(() => {
    canReceive.current = enabled;
    if (!enabled && recognition.current) { recognition.current.stop(); setListening(false); }
    return () => { canReceive.current = false; const current = recognition.current; recognition.current = null; current?.stop(); };
  }, [enabled]);
  if (!constructor) return null;
  const start = () => {
    setError(null);
    if (listening) { recognition.current?.stop(); return; }
    const next = new constructor(); recognition.current = next; next.lang = speechLocale(language); next.continuous = false; next.interimResults = false;
    next.onresult = event => { const result = event.results[event.results.length - 1]; if (canReceive.current && recognition.current === next && result?.isFinal) onText(result[0].transcript); };
    next.onerror = () => { if (canReceive.current && recognition.current === next) { setListening(false); setError("We couldn’t hear that. You can try again or type your clue."); } };
    next.onend = () => { if (recognition.current === next) setListening(false); };
    try { next.start(); setListening(true); trackAction("ispy_friend_speech_started"); }
    catch { setError("Microphone input is unavailable. Type your clue instead."); }
  };
  return <div className="stack-2"><Button variant="quiet" disabled={!enabled} onClick={start}><MicIcon size={18} /> {listening ? "Stop listening" : "Speak your clue"}</Button>
    {!enabled ? <p className="small muted">Microphone access can be enabled in Profile.</p> : null}{error ? <p role="alert">{error}</p> : null}</div>;
}

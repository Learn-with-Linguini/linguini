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
const conceptLabels = { adjective: "Choose a description", position: "Choose its position", quantity: "Add a quantity", identity: "Add a detail" };
export function composeCluePhrases(options: ChatClueOption[]): string {
  return options.map(option => /[.!?。！？]$/.test(option.text.trim()) ? option.text.trim() : `${option.text.trim()}.`).join(" ");
}

export function ClueComposer({ chat, round, disabled, command, microphoneEnabled }: {
  chat: ChatSnapshot; round: ChatRound; disabled: boolean; command: Command; microphoneEnabled: boolean;
}) {
  const key = chatDraftKey(chat.meId, chat.id, `${round.id}:${round.status}:clue`);
  const [draft, setDraft] = useState<ComposerDraft>(() => readChatDraft(key, { text: "", selected: [], stage: 0 }));
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const beginner = chat.viewerLevel === "A0";
  const supported = round.clueOptions.filter(option => option.concept !== "identity");
  const concepts = [...new Set(supported.map(option => option.concept))];
  const stage = concepts[Math.min(draft.stage, Math.max(0, concepts.length - 1))];
  const selected = draft.selected.map(id => supported.find(option => option.id === id)).filter((option): option is ChatClueOption => Boolean(option));
  const options = beginner ? supported.filter(option => option.concept === stage) : supported;
  const activeSheet = options[0]?.cheatSheet ?? selected.at(-1)?.cheatSheet;
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
    if (result) { saveChatDraft(key, null); trackAction(round.status === "awaitingFollowUp" ? "ispy_friend_followup_clue_sent" : "ispy_friend_clue_sent"); }
  };
  return <Card className="stack friend-composer"><div className="friend-composer__heading"><h2>{round.status === "awaitingFollowUp" ? "Add another clue" : "Build your clue"}</h2>
    {activeSheet ? <MissionCheatSheetLauncher {...activeSheet} languageCode={chat.targetLanguageCode} onOpen={() => trackAction("ispy_friend_cheatsheet_opened")} /> : null}</div>
    {round.target ? <p className="small muted">Describe {round.target.word} without using its name or translation.</p> : null}
    {beginner && stage ? <h3>{conceptLabels[stage]}</h3> : null}
    {options.length ? <div className="friend-composer__choices" role="group" aria-label={beginner && stage ? conceptLabels[stage] : "Suggested clue phrases"}>
      {options.map(option => <div key={option.id} className="friend-clue-option"><button type="button" className="friend-clue-option__choice"
        disabled={disabled} aria-pressed={draft.selected.includes(option.id)} onClick={() => choose(option)}><strong lang={chat.targetLanguageCode}>{option.text}</strong><span className="small">{option.translation}</span></button>
        <Button variant="quiet" aria-label="Hear this phrase" onClick={() => { speak(option.text, chat.targetLanguageCode); trackAction("ispy_friend_audio_played", { kind: "option" }); }}><SpeakerIcon size={18} /></Button></div>)}</div> : null}
    {selected.length ? <ul className="friend-composer__selected" aria-label="Your selected details">{selected.map((option, index) => <li key={option.id}><span lang={chat.targetLanguageCode}>{option.text}</span>
      {chat.viewerLevel === "A1" ? <span className="friend-composer__reorder"><Button variant="quiet" disabled={disabled || index === 0} aria-label={`Move detail ${index + 1} earlier`} onClick={() => move(index, -1)}>↑</Button>
        <Button variant="quiet" disabled={disabled || index + 1 === selected.length} aria-label={`Move detail ${index + 1} later`} onClick={() => move(index, 1)}>↓</Button></span> : null}
      <Button variant="quiet" disabled={disabled} aria-label={`Remove ${option.concept} detail`} onClick={() => choose(option)}>Remove</Button></li>)}</ul> : null}
    {beginner && draft.stage + 1 < concepts.length ? <Button variant="secondary" disabled={disabled} onClick={() => setDraft(current => ({ ...current, stage: current.stage + 1 }))}>Add another detail</Button> : null}
    {beginner && draft.stage > 0 ? <Button variant="quiet" disabled={disabled} onClick={() => setDraft(current => ({ ...current, stage: current.stage - 1 }))}>Change an earlier detail</Button> : null}
    <label className="field">{beginner ? "Your complete clue" : "Write your clue"}<textarea className="input" rows={3} maxLength={500}
      lang={chat.targetLanguageCode} value={draft.text} disabled={disabled || reviewing} readOnly={beginner}
      onChange={event => { setDraft(current => ({ ...current, text: event.target.value })); setReviewing(false); }} /></label>
    {!beginner && !["A0", "A1"].includes(chat.viewerLevel) ? <ClueSpeech language={chat.targetLanguageCode} enabled={microphoneEnabled && !disabled && !reviewing}
      onText={text => setDraft(current => ({ ...current, text: `${current.text.trim()} ${text}`.trim().slice(0, 500), selected: [] }))} /> : null}
    {namesTarget ? <p role="alert">This clue includes the object’s name. Describe a different detail before sending.</p> : similar ? <p role="status">Check this wording: it looks similar to the hidden object’s name.</p> : null}
    {suggestion ? <div className="stack-2 friend-composer__suggestion"><p lang={chat.targetLanguageCode}>{suggestion}</p>
      <Button variant="secondary" disabled={disabled} onClick={() => { setDraft(current => ({ ...current, text: suggestion, selected: [] })); setSuggestion(null); setReviewing(false); }}>Use this suggestion</Button>
      <Button variant="quiet" onClick={() => setSuggestion(null)}>Dismiss suggestion</Button></div> : null}
    <div className="friend-composer__actions"><Button variant="quiet" disabled={!draft.text.trim()} onClick={() => { speak(draft.text, chat.targetLanguageCode); trackAction("ispy_friend_audio_played", { kind: "preview" }); }}><SpeakerIcon size={18} /> Play audio</Button>
      <Button variant="quiet" disabled={disabled} onClick={() => void suggest()}>Suggest a clue</Button></div>
    {reviewing ? <><p className="small muted">Review the complete clue above, then send it to your friend.</p><Button disabled={disabled || !draft.text.trim() || namesTarget} onClick={() => void send()}>Send clue</Button>
      <Button variant="quiet" disabled={disabled} onClick={() => setReviewing(false)}>Edit clue</Button></> :
      <Button disabled={disabled || !draft.text.trim() || namesTarget} onClick={() => setReviewing(true)}>Review clue</Button>}
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

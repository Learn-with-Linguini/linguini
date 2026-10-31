import { useEffect, useState } from "react";
import { chatDraftKey, chatRoundIntent, readChatDraft, saveChatDraft } from "../../lib/friendChats";
import type { ChatObject, ChatPoint, ChatRound, ChatSnapshot } from "../../lib/friendChats";
import { trackAction } from "../../lib/analytics";
import { speak } from "../../lib/speech";
import { Button, Card } from "../ui";
import { SpeakerIcon } from "../icons";
import { ChatPhoto } from "./ChatPhoto";

interface TargetDraft { custom: boolean; point: ChatPoint | null; label: string; candidate: ChatObject | null }
export type ChatAction = (intent: string, payload?: Record<string, unknown>) => Promise<ChatSnapshot | null>;

export function TargetPicker({ chat, round, disabled, command }: { chat: ChatSnapshot; round: ChatRound; disabled: boolean; command: ChatAction }) {
  const key = chatDraftKey(chat.meId, chat.id, `${round.id}:target`);
  const [draft, setDraft] = useState<TargetDraft>(() => readChatDraft(key, { custom: Boolean(round.target && !round.objects.some(item => item.key === round.target?.key)),
    point: round.target ? { x: round.target.x, y: round.target.y } : null, label: "", candidate: round.target ?? null }));
  const [typing, setTyping] = useState(false);
  useEffect(() => { saveChatDraft(key, draft); }, [key, draft]);
  const propose = async (point: ChatPoint, label?: string) => {
    setDraft(current => ({ ...current, point, candidate: null }));
    const next = await command(chatRoundIntent(round.id, "target"), { ...point, ...(label?.trim() ? { label: label.trim() } : {}), confirm: false });
    if (next?.activeRound?.target) setDraft(current => ({ ...current, candidate: next.activeRound!.target! }));
  };
  const confirmTarget = async () => {
    if (!draft.candidate) return;
    const next = await command(chatRoundIntent(round.id, "target"), { objectKey: draft.candidate.key, confirm: true });
    if (next) { saveChatDraft(key, null); trackAction(draft.custom ? "ispy_friend_custom_object_confirmed" : "ispy_friend_detected_object_confirmed"); }
  };
  return <section className="stack" aria-label="Choose the hidden object"><h2>Choose something for your friend to find.</h2>
    <ChatPhoto chatId={chat.id} roundId={round.id} objects={draft.custom ? [] : round.objects} disabled={disabled}
      selected={draft.point} onObject={object => { setTyping(false); setDraft({ custom: false, point: object, label: "", candidate: object }); trackAction("ispy_friend_detected_object_selected"); }}
      onPoint={draft.custom ? point => void propose(point) : undefined} label={draft.custom ? "Tap the object in the photo" : "Choose a suggested object"} />
    {!draft.custom ? <Button variant="secondary" disabled={disabled} onClick={() => {
      setDraft({ custom: true, point: null, label: "", candidate: null }); setTyping(false); trackAction("ispy_friend_custom_object_started");
    }}>Add another object</Button> : <p>Tap the object in the photo. Linguini will suggest a name for you to check.</p>}
    {draft.candidate ? <Card className="stack friend-target"><h3>Is this your object?</h3>
      <ChatPhoto chatId={chat.id} roundId={round.id} crop={draft.candidate} label="Selected object preview" />
      <strong lang={chat.targetLanguageCode}>{draft.candidate.word}</strong><span>{draft.candidate.translation}</span>
      <Button variant="quiet" onClick={() => { speak(draft.candidate!.word, chat.targetLanguageCode); trackAction("ispy_friend_audio_played", { kind: "object" }); }}><SpeakerIcon size={18} /> Hear the word</Button>
      <Button disabled={disabled} onClick={() => void confirmTarget()}>Use this object</Button>
      {draft.custom ? <Button variant="quiet" disabled={disabled} onClick={() => setTyping(true)}>Choose a different name</Button> : null}
    </Card> : null}
    {draft.custom && draft.point ? <div className="stack-2">
      {!typing ? <Button variant="quiet" disabled={disabled} onClick={() => setTyping(true)}>Type what it is</Button> : <form className="stack-2" onSubmit={event => { event.preventDefault(); void propose(draft.point!, draft.label); }}>
        <label className="field">Object name<input className="input" maxLength={100} disabled={disabled} value={draft.label} onChange={event => setDraft(current => ({ ...current, label: event.target.value }))} /></label>
        <Button type="submit" variant="secondary" disabled={disabled || !draft.label.trim()}>Check this name</Button></form>}
      <Button variant="quiet" disabled={disabled} onClick={() => { setTyping(false); void propose(draft.point!); }}>I don’t know · suggest a name</Button>
    </div> : null}
    {draft.point || draft.candidate ? <Button variant="quiet" disabled={disabled} onClick={() => { setTyping(false); setDraft({ custom: false, point: null, label: "", candidate: null }); }}>Choose another object</Button> : null}
  </section>;
}

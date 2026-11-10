import { useEffect, useState } from "react";
import { chatDraftKey, chatRoundIntent, readChatDraft, saveChatDraft } from "../../lib/friendChats";
import type { ChatObject, ChatRound, ChatSnapshot } from "../../lib/friendChats";
import { trackAction } from "../../lib/analytics";
import { speak } from "../../lib/speech";
import { Button, Card } from "../ui";
import { SpeakerIcon } from "../icons";
import { ChatPhoto } from "./ChatPhoto";

interface TargetDraft { candidate: ChatObject | null }
export type ChatAction = (intent: string, payload?: Record<string, unknown>) => Promise<ChatSnapshot | null>;

/** Choose the secret object from the objects the sender confirmed. */
export function TargetPicker({ chat, round, disabled, command }: { chat: ChatSnapshot; round: ChatRound; disabled: boolean; command: ChatAction }) {
  const key = chatDraftKey(chat.meId, chat.id, `${round.id}:target`);
  const [draft, setDraft] = useState<TargetDraft>(() => {
    const saved = readChatDraft<TargetDraft>(key, { candidate: round.target ?? null });
    return { candidate: saved.candidate && round.objects.some(item => item.key === saved.candidate!.key) ? saved.candidate : null };
  });
  useEffect(() => { saveChatDraft(key, draft); }, [key, draft]);
  const confirmTarget = async () => {
    if (!draft.candidate) return;
    const next = await command(chatRoundIntent(round.id, "target"), { objectKey: draft.candidate.key, confirm: true });
    if (next) { saveChatDraft(key, null); trackAction("ispy_friend_detected_object_confirmed"); }
  };
  const unready = round.objects.some(item => item.clueReady === false);
  const noClue = draft.candidate?.clueReady === false;
  return <section className="stack" aria-label="Choose the hidden object"><div><h2>Choose something for your friend to find.</h2>
    {unready ? <p className="small muted">Faded markers don’t have enough detail for a beginner clue.</p> : null}</div>
    <ChatPhoto chatId={chat.id} roundId={round.id} objects={round.objects} disabled={disabled} selected={draft.candidate}
      onObject={object => { setDraft({ candidate: object }); trackAction("ispy_friend_detected_object_selected"); }} label="Choose one of your objects" />
    {draft.candidate ? <Card className="stack friend-target"><h3>Is this your object?</h3>
      <ChatPhoto chatId={chat.id} roundId={round.id} crop={draft.candidate} label="Selected object preview" />
      <strong lang={chat.targetLanguageCode}>{draft.candidate.word}</strong><span>{draft.candidate.translation}</span>
      <Button variant="quiet" onClick={() => { speak(draft.candidate!.word, chat.targetLanguageCode); trackAction("ispy_friend_audio_played", { kind: "object" }); }}><SpeakerIcon size={18} /> Hear the word</Button>
      {noClue ? <p role="status" className="small">Beginner clues need a colour, size, position or a nearby object, and this one has none yet. Choose another object.</p>
        : <Button disabled={disabled} onClick={() => void confirmTarget()}>Use this object</Button>}
      <Button variant="quiet" disabled={disabled} onClick={() => setDraft({ candidate: null })}>Choose another object</Button>
    </Card> : null}
  </section>;
}

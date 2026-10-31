import { useState } from "react";
import type { ChatPoint, ChatRound, ChatSnapshot } from "../../lib/friendChats";
import { chatDraftKey, chatRoundIntent, clearChatDrafts, readChatDraft, saveChatDraft } from "../../lib/friendChats";
import { trackAction } from "../../lib/analytics";
import { Button, Card } from "../ui";
import { InlineLoader } from "../LoadingScreen";
import { TargetPicker } from "./TargetPicker";
import { ClueComposer } from "./ClueComposer";
import { ChatPhoto } from "./ChatPhoto";
import { ChatMessages } from "./ChatTimeline";
import { PrivateClueHelp } from "./PrivateClueHelp";

type Command = <T = ChatSnapshot>(intent: string, payload?: Record<string, unknown>) => Promise<T | null>;
export function ActiveChatRound({ chat, round, command, disabled, microphoneEnabled }: {
  chat: ChatSnapshot; round: ChatRound; command: Command; disabled: boolean; microphoneEnabled: boolean;
}) {
  const [changingTarget, setChangingTarget] = useState(false);
  const key = chatDraftKey(chat.meId, chat.id, `${round.id}:guess`);
  const [guess, setGuess] = useState<ChatPoint | null>(() => readChatDraft(key, null));
  const [confirming, setConfirming] = useState(false);
  const own = round.senderId === chat.meId;
  const draftTarget = own && (round.status === "selectingTarget" || changingTarget);
  const lastGuess = [...round.messages].reverse().find(message => message.type === "guess" && message.senderId === chat.meId && message.x != null && message.y != null);
  const lastPoint = lastGuess ? { x: lastGuess.x!, y: lastGuess.y! } : null;
  const cancel = async () => {
    if (await command(chatRoundIntent(round.id, "cancel"))) { clearChatDrafts(chat.meId, chat.id, round.id); trackAction("ispy_friend_round_cancelled"); }
  };
  const submit = async () => {
    if (!guess) return;
    const next = await command(chatRoundIntent(round.id, "guess"), guess);
    if (next) { setGuess(null); setConfirming(false); saveChatDraft(key, null); trackAction("ispy_friend_guess_submitted"); }
  };
  return <section className="stack friend-round friend-round--active" aria-label="Current I-Spy">
    <p className="small muted">{own ? "Your photo" : `${chat.partner?.displayName ?? "Your friend"}’s photo`} · {round.photoStatus === "analyzing" ? "Preparing" : "In progress"}</p>
    {round.photoStatus === "analyzing" ? <InlineLoader label={own ? "Checking and analyzing your photo…" : "Your friend is preparing a photo…"} /> : round.photoStatus === "failed" ?
      <Card className="stack-2"><h2>This photo needs another try.</h2><p role="alert">{round.error ?? "We couldn’t finish checking this photo."}</p>
        {own && round.retryable ? <Button disabled={disabled} onClick={async () => { if (await command(chatRoundIntent(round.id, "retry"))) trackAction("ispy_friend_photo_retried"); }}>Retry photo analysis</Button> : null}</Card> : draftTarget ?
      <TargetPicker key={`${round.id}:target`} chat={chat} round={round} disabled={disabled} command={async (intent, payload) => {
        const next = await command(intent, payload); if (next?.activeRound?.status === "composingClue" && payload?.confirm) setChangingTarget(false); return next;
      }} /> : <>
        {round.imageUrl && (own || round.status !== "awaitingGuess") ? <ChatPhoto chatId={chat.id} roundId={round.id} selected={own ? round.target : lastPoint} /> : null}
        <ChatMessages chat={chat} round={round} />
        {own && ["composingClue", "awaitingFollowUp"].includes(round.status) ? <>
          <ClueComposer key={`${round.id}:${round.status}`} chat={chat} round={round} disabled={disabled} command={command} microphoneEnabled={microphoneEnabled} />
          {round.status === "composingClue" ? <Button variant="quiet" disabled={disabled} onClick={() => setChangingTarget(true)}>Choose a different object</Button> :
            <Button variant="secondary" disabled={disabled} onClick={async () => { if (await command(chatRoundIntent(round.id, "reveal"))) { clearChatDrafts(chat.meId, chat.id, round.id); trackAction("ispy_friend_answer_revealed"); } }}>Reveal the answer</Button>}
        </> : own ? <p role="status">Your clue is sent. Your friend can guess whenever they’re ready.</p> : round.status === "awaitingGuess" ? <>
          <h2>Tap the object you think they chose.</h2>
          {round.imageUrl ? <ChatPhoto chatId={chat.id} roundId={round.id} selected={guess ?? lastPoint} disabled={disabled || confirming} onPoint={point => {
            setGuess(point); saveChatDraft(key, point); trackAction("ispy_friend_guess_selected");
          }} label="Choose the object your friend described" /> : <p role="status">This photo is unavailable. Ask your friend to start a new round.</p>}
          {guess ? confirming ? <Card className="stack-2"><h3>Guess this object?</h3><Button disabled={disabled} onClick={() => void submit()}>Submit guess</Button>
            <Button variant="quiet" disabled={disabled} onClick={() => setConfirming(false)}>Choose again</Button></Card> : <Button disabled={disabled} onClick={() => setConfirming(true)}>Confirm this object</Button> : null}
          <PrivateClueHelp key={`${round.id}:${round.messages.length}`} chat={chat} round={round} />
        </> : <p role="status">{round.status === "awaitingFollowUp" ? "Not quite. Your friend can send another clue or reveal the answer." : "Your friend is choosing an object and composing a clue."}</p>}
    </>}
    {own ? <Button variant="quiet" disabled={disabled} onClick={() => void cancel()}>Cancel round</Button> : null}
    <p className="small muted">Finish this I-Spy before starting another.</p>
  </section>;
}

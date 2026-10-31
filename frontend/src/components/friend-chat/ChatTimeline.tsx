import type { ChatRound, ChatSnapshot } from "../../lib/friendChats";
import { trackAction } from "../../lib/analytics";
import { speak } from "../../lib/speech";
import { ChatPhoto } from "./ChatPhoto";
import { Button, Card } from "../ui";
import { SpeakerIcon } from "../icons";

export function ChatTimeline({ chat }: { chat: ChatSnapshot }) {
  return <section className="stack friend-timeline" aria-label="Conversation history">
    <p className="friend-timeline__system">{chat.partner ? `${chat.partner.displayName} joined your I-Spy chat.` : "Your private chat is ready."}</p>
    {!chat.rounds.length && !chat.activeRound && chat.partner ? <p className="muted">Share a photo to start your first I-Spy. Either of you can go first.</p> : null}
    {chat.rounds.map(round => <ChatRoundHistory key={round.id} chat={chat} round={round} />)}
  </section>;
}

export function ChatMessages({ chat, round }: { chat: ChatSnapshot; round: ChatRound }) {
  return <ol className="friend-timeline__messages" aria-label="Round messages">{round.messages.map(message =>
    <li key={message.id} className={`friend-message${message.senderId === chat.meId ? " friend-message--own" : ""}${["clue", "followUpClue"].includes(message.type) ? " friend-message--clue" : " friend-message--system"}`}>
      {message.type === "guess" ? <span>{message.senderId === chat.meId ? "You made a guess." : `${chat.partner?.displayName ?? "Your friend"} made a guess.`}</span> : <span lang={["clue", "followUpClue"].includes(message.type) ? chat.targetLanguageCode : undefined}>{message.text ?? "Round updated."}</span>}
      {["clue", "followUpClue"].includes(message.type) && message.text ? <Button variant="quiet" aria-label="Play clue audio" onClick={() => {
        speak(message.text!, chat.targetLanguageCode); trackAction("ispy_friend_audio_played", { kind: "clue" });
      }}><SpeakerIcon size={18} /> Hear clue</Button> : null}
    </li>)}</ol>;
}

function ChatRoundHistory({ chat, round }: { chat: ChatSnapshot; round: ChatRound }) {
  return <Card className="stack friend-round"><span className="small muted">{round.senderId === chat.meId ? "Your photo" : `${chat.partner?.displayName ?? "Your friend"}’s photo`} · {round.status === "cancelled" ? "Cancelled" : "Completed"}</span>
    {round.photoStatus === "ready" && round.imageUrl ? <ChatPhoto chatId={chat.id} roundId={round.id} selected={round.status === "completed" && round.target ? round.target : null} /> : null}
    <ChatMessages chat={chat} round={round} />
    {round.status === "completed" && round.target ? <div className="friend-round__answer"><strong lang={chat.targetLanguageCode}>{round.target.word}</strong><span>{round.target.translation}</span>
      <Button variant="quiet" aria-label="Hear the answer" onClick={() => { speak(round.target!.word, chat.targetLanguageCode); trackAction("ispy_friend_audio_played", { kind: "answer" }); }}><SpeakerIcon size={18} /></Button></div> : null}
  </Card>;
}

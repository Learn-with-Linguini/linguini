import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { useAppState } from "../state/useAppState";
import { useFriendChat } from "../state/useFriendChat";
import { useBackAction } from "../components/BackAction";
import { Button, Card } from "../components/ui";
import { InlineLoader, LoadingScreen } from "../components/LoadingScreen";
import { ImageUpload } from "../components/ImageUpload";
import { ChatAvatar } from "../components/friend-chat/ChatAvatar";
import { ChatTimeline } from "../components/friend-chat/ChatTimeline";
import { InviteControls } from "../components/friend-chat/InviteControls";
import { ActiveChatRound } from "../components/friend-chat/ActiveChatRound";
import { trackAction } from "../lib/analytics";
import { clearChatDrafts } from "../lib/friendChats";
import type { ChatSnapshot } from "../lib/friendChats";
import { languageDisplayName } from "../lib/languageChoices";
import { friendlyError } from "../lib/queryKeys";
import "../components/friend-chat/friendChat.css";

export function FriendChat() {
  const { chatId } = useParams();
  const { user, activeProfile } = useAppState();
  return chatId ? <FriendChatSession key={`${user?.id}:${activeProfile?.id}:${chatId}`} chatId={chatId} /> : <Navigate to="/ispy/friends" replace />;
}

function FriendChatSession({ chatId }: { chatId: string }) {
  const { user, activeProfile } = useAppState();
  const owner = user?.id ?? "";
  const { query, command, retry, busy, offline, error, hasPending, blocked } = useFriendChat(owner, activeProfile?.id ?? "", chatId);
  const navigate = useNavigate();
  const [uploading, setUploading] = useState(false);
  const [picking, setPicking] = useState(false);
  const [menuAction, setMenuAction] = useState<"leave" | "block" | "report" | null>(null);
  const [reason, setReason] = useState("");
  const [reported, setReported] = useState(false);
  const previousMessages = useRef<Set<string> | null>(null);
  useBackAction(() => navigate("/ispy/friends"), "Back to photo chats");
  useEffect(() => {
    if (!query.data) return;
    const messages = [...query.data.rounds, ...(query.data.activeRound ? [query.data.activeRound] : [])].flatMap(round => round.messages);
    if (previousMessages.current) for (const message of messages) {
      if (previousMessages.current.has(message.id)) continue;
      if (message.type === "correctResult") { trackAction("ispy_friend_guess_correct"); trackAction("ispy_friend_round_completed"); }
      if (message.type === "incorrectResult") trackAction("ispy_friend_guess_incorrect");
      if (message.type === "reveal") trackAction("ispy_friend_round_completed");
    }
    previousMessages.current = new Set(messages.map(message => message.id));
  }, [query.data]);
  if (query.isPending) return <LoadingScreen label="Opening your photo chat…" />;
  if (!query.data) return <div className="stack"><h1>Chat unavailable</h1><p role="alert">{friendlyError(query.error)}</p>
    <Button onClick={() => void query.refetch()}>Try again</Button><Button variant="quiet" onClick={() => navigate("/ispy/friends")}>Your chats</Button></div>;
  const chat = query.data;
  const language = languageDisplayName(chat.targetLanguageCode);
  const terminal = ["left", "blocked"].includes(chat.status);
  const compatible = activeProfile?.targetLanguageCode.toLowerCase().split("-")[0] === chat.targetLanguageCode.toLowerCase().split("-")[0];
  const disabled = blocked || uploading;
  const performMenu = async () => {
    if (!menuAction) return;
    const next = await command(menuAction, menuAction === "report" ? { reason: reason.trim() } : {});
    if (next) {
      trackAction(`ispy_friend_chat_${menuAction === "report" ? "reported" : menuAction === "leave" ? "left" : "blocked"}`);
      if (menuAction !== "report") clearChatDrafts(owner, chatId);
      else { setReported(true); setReason(""); }
      setMenuAction(null);
    }
  };
  return <div className="stack friend-chat" data-cs-mask>
    <header className="friend-chat__header"><div className="friend-chat__person"><ChatAvatar person={chat.partner} />
      <div><h1>{chat.partner?.displayName ?? "Your I-Spy chat"}</h1><p className="small muted">{language}</p></div></div>
      <details className="friend-chat__menu"><summary aria-label="Conversation options">•••</summary><div className="stack-2">
        {!terminal ? <Button variant="quiet" disabled={disabled} onClick={() => setMenuAction("leave")}>Leave conversation</Button> : null}
        {chat.partner ? <><Button variant="quiet" disabled={disabled} onClick={() => { setMenuAction("report"); setReported(false); }}>Report user</Button>
          {!terminal ? <Button variant="quiet" disabled={disabled} onClick={() => setMenuAction("block")}>Block user</Button> : null}</> : null}
      </div></details>
    </header>
    {menuAction ? <Card className="stack"><h2>{menuAction === "leave" ? "Leave this conversation?" : menuAction === "block" ? "Block this person?" : "Report this person"}</h2>
      <p>{menuAction === "leave" ? "This closes the conversation and its invitation." : menuAction === "block" ? "This closes your chats together and prevents new invitations between you." : "Tell us what happened. Your report is private."}</p>
      {menuAction === "report" ? <label className="field">Reason<textarea className="input" rows={3} value={reason} minLength={3} maxLength={500} onChange={event => setReason(event.target.value)} /></label> : null}
      <Button disabled={disabled || (menuAction === "report" && reason.trim().length < 3)} onClick={() => void performMenu()}>{menuAction === "report" ? "Submit report" : menuAction === "leave" ? "Leave conversation" : "Block user"}</Button>
      <Button variant="quiet" disabled={busy} onClick={() => setMenuAction(null)}>Keep chatting</Button></Card> : null}
    {reported ? <p role="status">Your report has been saved.</p> : null}
    {offline ? <p role="status">You’re offline. Your saved conversation is shown. Reconnect to send a clue or guess.</p> : query.error ? <div className="stack-2"><p role="alert">Connection interrupted. Your saved conversation is shown.</p>
      <Button variant="secondary" onClick={() => void query.refetch()}>Reconnect</Button></div> : null}
    {error ? <p role="alert">{error}</p> : null}
    {hasPending && !busy ? <Card className="stack-2"><p>We couldn’t confirm your last action. Retry it to check whether it was saved.</p>
      <Button variant="secondary" disabled={offline} onClick={() => { trackAction("ispy_friend_action_retried"); void retry(); }}>Retry last action</Button></Card> : null}
    {busy ? <InlineLoader compact label="Saving your action…" /> : null}
    {!compatible && !terminal ? <Card className="stack-2"><p>This chat is in {language}. Switch to a matching profile or create one to play.</p><Button variant="secondary" onClick={() => navigate("/profile")}>Choose a language profile</Button></Card> : null}
    {chat.status === "waiting" && chat.creator.id === owner ? <InviteControls key={chat.inviteStatus} chat={chat} command={command} disabled={disabled} /> : null}
    <ChatTimeline chat={chat} />
    {terminal ? <Card><p>{chat.status === "blocked" ? "This conversation is blocked." : "A participant left this conversation."}</p><Button variant="quiet" onClick={() => navigate("/ispy/friends")}>Back to your chats</Button></Card> : chat.activeRound ?
      <ActiveChatRound key={chat.activeRound.id} chat={chat} round={chat.activeRound} command={command} disabled={disabled || !compatible}
        microphoneEnabled={user?.microphoneEnabled ?? false} /> : chat.partner && chat.status === "active" ? <section className="stack friend-chat__new-round" aria-label="Start another round">
        {!picking ? <Button disabled={disabled || !compatible} onClick={() => setPicking(true)}>{chat.rounds.length ? "Start another I-Spy" : "Start an I-Spy"}</Button> : <>
          <h2>Choose one photo</h2><p className="small muted">Your friend can see this photo after it’s checked.</p>
          <ImageUpload cameraEnabled={user?.cameraEnabled ?? false} disabled={disabled || !compatible} onBusyChange={setUploading} onUploaded={image => {
            void command<ChatSnapshot>("rounds", { mediaAssetId: image.id }).then(next => { if (next) { setPicking(false); trackAction("ispy_friend_photo_uploaded");
              if (chat.rounds.length) trackAction("ispy_friend_next_round_started"); } });
          }} /><Button variant="quiet" disabled={uploading} onClick={() => setPicking(false)}>Cancel photo selection</Button>
        </>}
      </section> : null}
  </div>;
}

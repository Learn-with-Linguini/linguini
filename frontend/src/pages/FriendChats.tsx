import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import { trackAction } from "../lib/analytics";
import { languageDisplayName } from "../lib/languageChoices";
import { friendlyError } from "../lib/queryKeys";
import { activateChatDraftOwner, chatDraftKey, createFriendChat, friendChatKeys, getFriendChats, joinFriendChat, previewChatInvite, readFriendInvite, rememberFriendInvite, saveChatDraft } from "../lib/friendChats";
import type { ChatInvitePreview, ChatSnapshot } from "../lib/friendChats";
import { useAppState } from "../state/useAppState";
import { Button, Card } from "../components/ui";
import { InlineLoader } from "../components/LoadingScreen";
import { ChatAvatar } from "../components/friend-chat/ChatAvatar";
import { Rooms } from "./Rooms";
import "../components/friend-chat/friendChat.css";

export function FriendChats() {
  const { user, activeProfile } = useAppState();
  const [params] = useSearchParams();
  return params.has("code") ? <Rooms /> : <FriendChatList key={`${user?.id}:${activeProfile?.id}`} />;
}

function FriendChatList() {
  const { user, activeProfile } = useAppState();
  const navigate = useNavigate();
  const client = useQueryClient();
  const owner = user?.id ?? "";
  const profile = activeProfile?.id ?? "";
  const [invite, setInvite] = useState(readFriendInvite);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createPending, setCreatePending] = useState(false);
  const createKey = useRef<string | null>(null);
  const busyRef = useRef(false);
  useEffect(() => { activateChatDraftOwner(owner); }, [owner]);
  const chats = useQuery({ queryKey: friendChatKeys.list(owner, profile), queryFn: ({ signal }) => getFriendChats(signal),
    enabled: Boolean(owner && profile), retry: false, refetchOnWindowFocus: true });
  const open = (chat: ChatSnapshot) => {
    if (chat.meId !== owner) { setError("Your account changed. Refresh this page to open your chats."); return; }
    client.setQueryData(friendChatKeys.chat(owner, profile, chat.id), chat);
    navigate(`/ispy/friends/${encodeURIComponent(chat.id)}`);
  };
  const create = async () => {
    if (!activeProfile || busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(null);
    createKey.current ??= crypto.randomUUID(); setCreatePending(true);
    try {
      const entry = await createFriendChat(activeProfile.id, createKey.current);
      saveChatDraft(chatDraftKey(owner, entry.chat.id, "invite"), entry.inviteToken);
      createKey.current = null; setCreatePending(false);
      trackAction("ispy_friend_chat_created"); open(entry.chat);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500) { createKey.current = null; setCreatePending(false); }
      setError(reason instanceof ApiError ? reason.message : friendlyError(reason));
    } finally { busyRef.current = false; setBusy(false); }
  };
  const pastedInvite = () => {
    let token = input.trim();
    try { token = new URL(token).hash.match(/(?:^#|&)invite=([^&]+)/)?.[1] ?? token; token = decodeURIComponent(token); } catch { /* A raw code is also accepted. */ }
    rememberFriendInvite(token); setInvite(token); setInput("");
  };
  return <div className="stack friend-chats" data-cs-mask>
    <header><span className="label muted">I-Spy with a friend</span><h1>Your photo chats</h1>
      <p>Send a photo and a clue. Your friend can find it whenever they’re ready.</p></header>
    {invite ? <FriendInvite key={`${owner}:${invite}`} token={invite} onJoined={chat => { rememberFriendInvite(""); setInvite(""); open(chat); }}
      onDismiss={() => { rememberFriendInvite(""); setInvite(""); }} /> : null}
    {!activeProfile ? <p role="alert">Choose a learning language in Profile before creating or joining a chat.</p> : null}
    <Button disabled={!activeProfile || busy || createPending} onClick={() => void create()}>Play with a friend</Button>
    {busy ? <InlineLoader compact label="Creating your private chat…" /> : null}
    {error ? <div className="stack-2"><p role="alert">{error}</p>{createPending ? <Button variant="secondary" disabled={busy} onClick={() => void create()}>Retry creating chat</Button> : null}</div> : null}
    <section className="stack" aria-labelledby="friend-chat-list-title"><h2 id="friend-chat-list-title">Your chats</h2>
      {chats.isPending && activeProfile ? <InlineLoader label="Opening your chats…" /> : chats.error ? <Card className="stack-2"><p role="alert">{friendlyError(chats.error)}</p>
        <Button variant="secondary" onClick={() => void chats.refetch()}>Retry chats</Button></Card> : !chats.data?.length ?
        <Card><p>No photo chats yet. Invite one friend to start your first I-Spy.</p></Card> :
        <ul className="friend-chats__list">{chats.data.map(chat => <li key={chat.id}><button type="button" className="friend-chats__item" onClick={() => open(chat)}>
          <ChatAvatar person={chat.partner} /><span><strong>{chat.partner?.displayName ?? "Your invitation"}</strong>
            <span className="small muted">{languageDisplayName(chat.targetLanguageCode)} · {chat.status === "waiting" ? "Waiting for your friend" : chat.status === "left" ? "Conversation ended" : chat.status === "blocked" ? "Blocked" : chat.activeRound ? "An I-Spy is in progress" : "Ready for another photo"}</span></span></button></li>)}</ul>}
    </section>
    <details><summary>Have an invitation link?</summary><div className="stack-2">
      <label className="field">Invitation link or code<input className="input" value={input} maxLength={1000} autoComplete="off" autoCapitalize="none" spellCheck={false} onChange={event => setInput(event.target.value)} /></label>
      <Button variant="secondary" disabled={!input.trim()} onClick={pastedInvite}>Open invitation</Button></div></details>
  </div>;
}

function FriendInvite({ token, onJoined, onDismiss }: { token: string; onJoined: (chat: ChatSnapshot) => void; onDismiss: () => void }) {
  const { activeProfile } = useAppState();
  const navigate = useNavigate();
  const [preview, setPreview] = useState<ChatInvitePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const commandId = useRef<string | null>(null);
  const busyRef = useRef(false);
  useEffect(() => {
    let current = true; setLoading(true); setError(null);
    trackAction("ispy_friend_invite_opened");
    void previewChatInvite(token).then(value => { if (current) setPreview(value); }).catch(reason => {
      if (current) setError(reason instanceof ApiError ? reason.message : friendlyError(reason));
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [token, attempt]);
  const compatible = Boolean(activeProfile && preview?.targetLanguageCode
    && activeProfile.targetLanguageCode.toLowerCase().split("-")[0] === preview.targetLanguageCode.toLowerCase().split("-")[0]);
  const join = async () => {
    if (!activeProfile || !compatible || busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(null); commandId.current ??= crypto.randomUUID();
    try { const chat = await joinFriendChat(activeProfile.id, token, commandId.current); trackAction("ispy_friend_chat_joined"); onJoined(chat); }
    catch (reason) { if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500) commandId.current = null;
      setError(reason instanceof ApiError ? reason.message : friendlyError(reason)); }
    finally { busyRef.current = false; setBusy(false); }
  };
  return <Card className="stack friend-invite"><h2>Your I-Spy invitation</h2>
    {loading ? <InlineLoader compact label="Checking this private invitation…" /> : preview?.status === "open" ? <>
      <div className="friend-chat__person"><ChatAvatar person={preview.creator ?? null} /><strong>{preview.creator?.displayName ?? "Your friend"} invited you</strong></div>
      <p>Play in {languageDisplayName(preview.targetLanguageCode ?? "")}.</p>
      {!compatible ? <><p>This I-Spy chat is in {languageDisplayName(preview.targetLanguageCode ?? "")}. Switch to a matching profile or create one to join.</p>
        <Button variant="secondary" onClick={() => navigate("/profile")}>Choose a language profile</Button></> :
        <Button disabled={busy} onClick={() => void join()}>{busy ? "Joining…" : "Join I-Spy chat"}</Button>}
    </> : preview ? <p>{preview.status === "full" ? "This I-Spy chat already has two players." : preview.status === "expired" ? "This invitation has expired. Ask your friend for a new link." : "This invitation is no longer available. Ask your friend for a new link."}</p> : null}
    {error ? <><p role="alert">{error}</p><Button variant="secondary" disabled={busy} onClick={() => preview?.status === "open" ? void join() : setAttempt(value => value + 1)}>Try again</Button></> : null}
    <Button variant="quiet" disabled={busy} onClick={onDismiss}>Dismiss invitation</Button>
  </Card>;
}

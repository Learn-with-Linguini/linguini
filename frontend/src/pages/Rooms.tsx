import { useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, proficiencyLabel } from "../lib/api";
import { acceptFriend, createRoom, getFriends, getRooms, inviteFriend, joinRoom, removeFriend, roomActionLabel, roomDeadline, roomMatchesProfile, roomQueryKeys } from "../lib/rooms";
import type { FriendInvitation, RoomSnapshot } from "../lib/rooms";
import { friendlyError } from "../lib/queryKeys";
import { useAppState } from "../state/useAppState";
import { Button, Card } from "../components/ui";
import { GameResources } from "../components/GameResources";
import "../components/rooms.css";

type LobbyAction = "create" | "join" | "inviteFriend" | "acceptFriend" | "removeFriend";
interface LobbyCommand { kind: LobbyAction; profileId: string; code: string; commandId: string; friendUserId?: string }

export function Rooms() {
  const { user, activeProfile } = useAppState();
  return <RoomLobby key={`${user?.id}:${activeProfile?.id}`} />;
}

function RoomLobby() {
  const { user, activeProfile } = useAppState();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [code, setCode] = useState(params.get("code") ?? "");
  const [friendCode, setFriendCode] = useState(params.get("friendCode") ?? "");
  const [invitation, setInvitation] = useState<FriendInvitation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<LobbyCommand | null>(null);
  const [pendingKind, setPendingKind] = useState<LobbyAction | null>(null);
  const busyRef = useRef(false);
  const owner = user?.id ?? "";
  const profile = activeProfile?.id ?? "";
  const rooms = useQuery({ queryKey: roomQueryKeys.list(owner, profile), queryFn: async ({ signal }) => {
    const current = await getRooms(signal);
    if (current.some(room => room.meId !== owner)) throw new Error("These challenges belong to another signed-in account.");
    return current;
  }, enabled: Boolean(owner && profile), retry: false,
    refetchInterval: () => document.hidden || busyRef.current ? false : 20_000,
    refetchIntervalInBackground: false, refetchOnWindowFocus: true });
  const friends = useQuery({ queryKey: roomQueryKeys.friends(owner, profile), queryFn: ({ signal }) => getFriends(signal),
    enabled: Boolean(owner && profile), retry: false, refetchOnWindowFocus: true });

  const perform = async (kind: LobbyAction, friendUserId?: string) => {
    if (!activeProfile || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    setNotice(null);
    const command = pending.current ?? { kind, profileId: activeProfile.id,
      code: (kind === "acceptFriend" ? friendCode : code).trim(), friendUserId, commandId: crypto.randomUUID() };
    pending.current = command;
    setPendingKind(command.kind);
    try {
      if (command.kind === "create" || command.kind === "join") {
        const entry = command.kind === "create" ? await createRoom(command.profileId, command.commandId, command.friendUserId)
          : await joinRoom(command.profileId, command.code, command.commandId);
        if (entry.room.meId !== owner) throw new Error("This challenge changed accounts. Open it again from your challenges.");
        client.setQueryData(roomQueryKeys.snapshot(owner, profile, entry.room.id), entry.room);
        void client.invalidateQueries({ queryKey: roomQueryKeys.list(owner, profile) });
        navigate(`/rooms/${encodeURIComponent(entry.room.id)}`, { state: { inviteCode: entry.inviteCode ?? null } });
      } else if (command.kind === "inviteFriend") {
        setInvitation(await inviteFriend(command.commandId));
      } else if (command.kind === "acceptFriend") {
        const friend = await acceptFriend(command.code, command.commandId);
        setFriendCode("");
        setParams(current => { current.delete("friendCode"); return current; }, { replace: true });
        setNotice(`${friend.displayName} is now in your friends.`);
        void client.invalidateQueries({ queryKey: roomQueryKeys.friends(owner, profile) });
      } else {
        await removeFriend(command.friendUserId!);
        setNotice("Friend removed. Your existing challenges are still saved.");
        void client.invalidateQueries({ queryKey: roomQueryKeys.friends(owner, profile) });
      }
      pending.current = null;
      setPendingKind(null);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500) { pending.current = null; setPendingKind(null); }
      setError(reason instanceof ApiError ? reason.message : friendlyError(reason));
    } finally { busyRef.current = false; setBusy(false); }
  };
  const blocked = busy || Boolean(pendingKind);
  const openRooms = rooms.data?.filter(room => !["completed", "ended", "expired"].includes(room.status) || room.actionRequired === "viewResult") ?? [];
  const history = rooms.data?.filter(room => !openRooms.includes(room)) ?? [];
  const challengeRow = (room: RoomSnapshot) => {
    const partner = room.members.find(member => member.userId !== owner);
    return <li key={room.id} className="rooms-challenge"><div className="stack-2">
      <strong>{partner ? `With ${partner.displayName}` : "Private invitation"}</strong>
      <span className="rooms-challenge__status">{roomActionLabel(room)}</span>
      <span className="small muted">{room.targetLanguageCode.toUpperCase()} · {room.proficiencyLevel} · {room.status === "lobby" ? `${room.photos.length} shared photos` : `${room.successfulRounds} of ${room.roundCount} found`}</span>
      {!roomMatchesProfile(room, activeProfile) ? <span className="small muted">Uses a different learning setup.</span> : null}
      {!["completed", "ended", "expired"].includes(room.status) ? <span className="small muted">{room.status === "lobby" ? "Prepare by" : "Play by"} {roomDeadline(room.status === "lobby" ? room.inviteExpiresAt : room.expiresAt)}</span> : null}
    </div><Button variant="secondary" disabled={busy} aria-label={`${room.actionRequired === "finished" ? "View recap" : "Open challenge"} ${partner?.displayName ?? "private invitation"}`}
      onClick={() => navigate(`/rooms/${encodeURIComponent(room.id)}`)}>{room.actionRequired === "finished" ? "View recap" : "Open"}</Button></li>;
  };

  return <div className="stack rooms-page">
    <h1>Challenges with friends</h1>
    <p>Send a clue, come back for a guess. You can play at different times and keep a few challenges going.</p>
    <GameResources />
    {!activeProfile ? <p role="alert">Choose your learning language in Profile before starting a challenge.</p> :
      <p className="small muted">Your challenges use {activeProfile.targetLanguageCode.toUpperCase()} · {proficiencyLabel(activeProfile.proficiencyLevel)}.
        Friends need the same learning language, explanation language, and level to play.</p>}
    {busy ? <p role="status">Saving your request…</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    {error ? <div className="stack-2"><p role="alert">{error}</p>{pendingKind ?
      <Button variant="secondary" disabled={busy} onClick={() => void perform(pendingKind)}>Retry request</Button> : null}</div> : null}
    <section className="stack" aria-labelledby="challenge-inbox-heading"><h2 id="challenge-inbox-heading">Your challenges</h2>
      {rooms.isPending && activeProfile ? <p role="status">Loading your challenges…</p> : rooms.error ?
        <div className="stack-2"><p role="alert">We couldn’t load your challenges.</p><Button variant="secondary" onClick={() => void rooms.refetch()}>Retry challenges</Button></div> :
        openRooms.length ? <ul className="rooms-challenges">{openRooms.map(challengeRow)}</ul> : <p className="small muted">No open challenges. Invite a friend when you’re ready.</p>}
      {history.length ? <details className="rooms-word-bank"><summary>Recent challenges · {history.length}</summary><ul className="rooms-challenges">{history.map(challengeRow)}</ul></details> : null}
    </section>
    <Card className="stack"><h2>Start a private challenge</h2><p>Invite one friend and prepare 2–4 photos. Get ready in your own time; play starts when you’re both ready.</p>
      <Button disabled={!activeProfile || blocked} onClick={() => void perform("create")}>Create a challenge</Button>
      <p className="small muted">Starting the game uses 1 Sauce for each person. You have a week to prepare, then two weeks to play.</p>
    </Card>
    <section className="stack" aria-labelledby="saved-friends-heading"><h2 id="saved-friends-heading">Your friends</h2>
      {friends.isPending && activeProfile ? <p role="status">Loading your friends…</p> : friends.error ? <div className="stack-2">
        <p role="alert">We couldn’t load your friends.</p><Button variant="secondary" onClick={() => void friends.refetch()}>Retry friends</Button></div> :
        friends.data?.length ? <ul className="rooms-friends">{friends.data.map(friend => <li key={friend.userId} className="rooms-friend">
          <div className="stack-2"><strong>{friend.displayName}</strong><span className="small muted">{friend.canChallenge ? "Ready for a challenge" : "Choose the same language and level to play together"}</span></div>
          <div className="rooms-friend__actions"><Button variant="secondary" disabled={!friend.canChallenge || blocked} aria-label={`Challenge ${friend.displayName}`}
            onClick={() => void perform("create", friend.userId)}>Challenge</Button>
            <Button variant="quiet" disabled={blocked} aria-label={`Remove ${friend.displayName} from friends`} onClick={() => void perform("removeFriend", friend.userId)}>Remove</Button></div>
        </li>)}</ul> : <p className="small muted">Save a friend to send them challenges directly. They choose when to get ready.</p>}
      <Button variant="secondary" disabled={!activeProfile || blocked} onClick={() => void perform("inviteFriend")}>Invite a friend</Button>
      {invitation ? <Card className="stack-2"><label className="field">Friend invitation link<input className="input" readOnly
        value={`${window.location.origin}/ispy/friends?friendCode=${encodeURIComponent(invitation.inviteCode)}`} onFocus={event => event.target.select()} /></label>
        <label className="field">Friend code<input className="input" readOnly value={invitation.inviteCode} onFocus={event => event.target.select()} /></label>
        <p className="small muted">Share privately with one person. They must accept to become your friend. Expires {roomDeadline(invitation.expiresAt)}.</p></Card> : null}
      <details className="rooms-word-bank" open={Boolean(params.get("friendCode"))}><summary>Accept a friend invitation</summary><div className="stack-2">
        <label className="field">Friend invitation code<input className="input" value={friendCode} autoComplete="off" autoCapitalize="none" spellCheck={false}
          maxLength={100} disabled={blocked} onChange={event => setFriendCode(event.target.value)} placeholder="Paste a friend invitation code" /></label>
        <p className="small muted">Accepting saves you in each other’s friends list and lets you send direct challenges. Each challenge still needs both people to get ready.</p>
        <Button variant="secondary" disabled={!activeProfile || !friendCode.trim() || blocked} onClick={() => void perform("acceptFriend")}>Accept friend invitation</Button>
      </div></details>
    </section>
    <Card className="stack"><h2>Have a challenge invitation?</h2>
      <label className="field">Room code<input className="input" value={code} autoComplete="off" autoCapitalize="none" spellCheck={false}
        maxLength={100} disabled={blocked} onChange={event => setCode(event.target.value)} placeholder="Paste your friend’s code" /></label>
      <Button variant="secondary" disabled={!activeProfile || !code.trim() || blocked} onClick={() => void perform("join")}>Join room</Button>
      <p className="small muted">A challenge link shares its photos with the person who joins. Keep it private.</p>
    </Card>
  </div>;
}

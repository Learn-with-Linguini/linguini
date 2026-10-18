import { InlineLoader, LoadingScreen } from "../components/LoadingScreen";
import { useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, proficiencyLabel } from "../lib/api";
import { createRoom, getActiveRoom, joinRoom, roomMatchesProfile, roomQueryKeys } from "../lib/rooms";
import { friendlyError } from "../lib/queryKeys";
import { useAppState } from "../state/useAppState";
import { Button, Card } from "../components/ui";
import { GameResources } from "../components/GameResources";
import "../components/rooms.css";

export function Rooms() {
  const { user, activeProfile } = useAppState();
  return <RoomLobby key={`${user?.id}:${activeProfile?.id}`} />;
}

function RoomLobby() {
  const { user, activeProfile } = useAppState();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [params] = useSearchParams();
  const [code, setCode] = useState(params.get("code") ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<{ kind: "create" | "join"; profileId: string; code: string; commandId: string } | null>(null);
  const [pendingKind, setPendingKind] = useState<"create" | "join" | null>(null);
  const busyRef = useRef(false);
  const owner = user?.id ?? "";
  const profile = activeProfile?.id ?? "";
  const active = useQuery({ queryKey: roomQueryKeys.active(owner, profile), queryFn: async ({ signal }) => {
    const current = await getActiveRoom(signal);
    if (current && current.meId !== owner) throw new Error("The room belongs to another signed-in account.");
    return current;
  },
    enabled: Boolean(owner && profile), retry: false });

  const enter = async (kind: "create" | "join") => {
    if (!activeProfile || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    const command = pending.current ?? { kind, profileId: activeProfile.id, code: code.trim(), commandId: crypto.randomUUID() };
    pending.current = command;
    setPendingKind(command.kind);
    try {
      const entry = command.kind === "create" ? await createRoom(command.profileId, command.commandId)
        : await joinRoom(command.profileId, command.code, command.commandId);
      if (entry.room.meId !== owner) throw new Error("This room changed accounts. Return home and open it again.");
      client.setQueryData(roomQueryKeys.snapshot(owner, profile, entry.room.id), entry.room);
      client.setQueryData(roomQueryKeys.active(owner, profile), entry.room);
      pending.current = null;
      setPendingKind(null);
      navigate(`/rooms/${encodeURIComponent(entry.room.id)}`, { state: { inviteCode: entry.inviteCode ?? null } });
    } catch (reason) {
      if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500) { pending.current = null; setPendingKind(null); }
      setError(reason instanceof ApiError ? reason.message : friendlyError(reason));
    } finally { busyRef.current = false; setBusy(false); }
  };

  return <div className="stack rooms-page">
    <h1>I Spy with a friend</h1>
    <p>Add a few photos together. Take turns giving a clue and spotting the object in a fresh photo.</p>
    <GameResources />
    {!activeProfile ? <p role="alert">Choose your learning language in Profile before joining a room.</p> :
      <p className="small muted">Your room uses {activeProfile.targetLanguageCode.toUpperCase()} · {proficiencyLabel(activeProfile.proficiencyLevel)}.
        Your friend needs the same learning language, explanation language, and level.</p>}
    {active.isPending && activeProfile ? <InlineLoader label="Checking for an open room…" /> : active.error ?
      <div className="stack-2"><p role="alert">We couldn’t check your open room.</p>
        <Button variant="secondary" onClick={() => void active.refetch()}>Try again</Button></div> : active.data ?
      <Card className="stack"><h2>Your open room</h2><p>{active.data.status === "playing" ? "Your game is underway." : "Your photos and friend are waiting here."}</p>
        {!roomMatchesProfile(active.data, activeProfile) ? <p className="small muted">This room uses a different learning setup. You can return to it or leave it.</p> : null}
        <Button disabled={busy} onClick={() => navigate(`/rooms/${encodeURIComponent(active.data!.id)}`)}>Return to room</Button></Card> :
      <Card className="stack"><h2>Start a private room</h2><p>Invite one friend, then add 2–4 photos. Each photo becomes one round.</p>
        <Button disabled={!activeProfile || busy || Boolean(pendingKind)} onClick={() => void enter("create")}>Create a room</Button>
        <p className="small muted">Take turns with a friend across photos you choose together.</p></Card>}
    {!active.data ? <Card className="stack"><h2>Have an invitation?</h2>
      <label className="field">Room code<input className="input" value={code} autoComplete="off" autoCapitalize="none" spellCheck={false}
        maxLength={100} disabled={busy || Boolean(pendingKind)} onChange={event => setCode(event.target.value)} placeholder="Paste your friend’s code" /></label>
      <Button variant="secondary" disabled={!activeProfile || !code.trim() || busy || Boolean(pendingKind) || active.isPending || Boolean(active.error)}
        onClick={() => void enter("join")}>Join room</Button></Card> : null}
    {busy ? <LoadingScreen label={pendingKind === "join" ? "Joining your friend…" : "Creating your room…"} /> : null}
    {error ? <div className="stack-2"><p role="alert">{error}</p>{pendingKind ?
      <Button variant="secondary" disabled={busy} onClick={() => void enter(pendingKind)}>Retry request</Button> : null}</div> : null}
  </div>;
}

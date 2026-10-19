import { InlineLoader, LoadingScreen } from "../components/LoadingScreen";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import { canStartRoom, getRoom, getRoomPhoto, prepareRoomCommand, roomQueryKeys, roomReviewPayload, sendRoomCommand } from "../lib/rooms";
import type { PendingRoomCommand, RoomObject, RoomPhoto, RoomPhotoReview, RoomRelationType, RoomSnapshot, RoomTurn } from "../lib/rooms";
import { friendlyError, queryKeys } from "../lib/queryKeys";
import { useAppState } from "../state/useAppState";
import { Button, Card, Feedback } from "../components/ui";
import { ImageUpload } from "../components/ImageUpload";
import { BasilIcon } from "../components/icons";
import { languages } from "../config/languages";
import "../components/rooms.css";

export function Room() {
  const { roomId } = useParams();
  const { user, activeProfile } = useAppState();
  if (!roomId) return <Navigate to="/ispy/friends" replace />;
  return <RoomSession key={`${user?.id}:${activeProfile?.id}:${roomId}`} roomId={roomId} />;
}

function RoomSession({ roomId }: { roomId: string }) {
  const { user, activeProfile } = useAppState();
  const location = useLocation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const owner = user?.id ?? "";
  const profile = activeProfile?.id ?? "";
  const key = roomQueryKeys.snapshot(owner, profile, roomId);
  const busyRef = useRef(false);
  const pending = useRef<PendingRoomCommand | null>(null);
  const lastResourceState = useRef<string | null>(null);
  const [pendingIntent, setPendingIntent] = useState<string | null>(null);
  const [rejectedCommand, setRejectedCommand] = useState<PendingRoomCommand | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const entryInviteCode = (location.state as { inviteCode?: string | null } | null)?.inviteCode;
  const room = useQuery({ queryKey: key, enabled: Boolean(owner && profile), retry: 1,
    queryFn: async ({ signal }) => {
      const next = await getRoom(roomId, signal);
      if (next.meId !== owner) throw new Error("The room belongs to another signed-in account.");
      const current = client.getQueryData<RoomSnapshot>(key);
      return current && current.revision > next.revision ? current : next;
    },
    refetchInterval: query => {
      if (busyRef.current || document.hidden) return false;
      const status = query.state.data?.status;
      return status === "playing" ? 1_500 + Math.random() * 300 : status === "lobby" ? 3_000 + Math.random() * 500 : false;
    }, refetchIntervalInBackground: false, refetchOnWindowFocus: true });

  const ownContribution = room.data?.contributions.find(item => item.userId === owner);
  const resourceState = room.data ? `${room.data.status}:${ownContribution?.basilEarned ?? 0}:${ownContribution?.xpEarned ?? 0}` : null;
  useEffect(() => {
    if (resourceState === null) return;
    const previous = lastResourceState.current;
    lastResourceState.current = resourceState;
    // The partner can start the room or finish a turn while this page only polls.
    // Repeated snapshots of the same status/credit do not trigger extra reads.
    if (previous === resourceState || (previous === null && resourceState.startsWith("lobby:"))) return;
    void client.invalidateQueries({ queryKey: queryKeys.progress(profile) });
  }, [resourceState, client, owner, profile]);

  const act = async (intent: string, payload: Record<string, unknown> = {}): Promise<boolean> => {
    if (!room.data || busyRef.current) return false;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    setRejectedCommand(null);
    const command = prepareRoomCommand(intent, room.data.revision, payload, pending.current);
    pending.current = command;
    setPendingIntent(command.intent);
    await client.cancelQueries({ queryKey: key });
    try {
      const next = await sendRoomCommand(roomId, command);
      if (next.meId !== owner) throw new Error("This room changed accounts. Return home and open it again.");
      client.setQueryData<RoomSnapshot>(key, previous => previous && previous.revision > next.revision ? previous : next);
      pending.current = null;
      setPendingIntent(null);
      void client.invalidateQueries({ queryKey: roomQueryKeys.active(owner, profile) });
      return true;
    } catch (reason) {
      if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500) {
        pending.current = null;
        setPendingIntent(null);
        if (reason.code === "room_stale_revision") setRejectedCommand(command);
        await room.refetch();
      }
      setError(reason instanceof ApiError ? reason.message : friendlyError(reason));
      return false;
    } finally { busyRef.current = false; setBusy(false); }
  };

  if (room.isPending) return <LoadingScreen label="Opening your room…" />;
  if (!room.data) return <div className="stack rooms-page"><h1>Room unavailable</h1>
    <p role="alert">{room.error instanceof ApiError ? room.error.message : "We couldn’t open this room. Check your connection and try again."}</p>
    <Button onClick={() => void room.refetch()}>Try again</Button><Button variant="quiet" onClick={() => navigate("/ispy/friends")}>Find your room</Button></div>;
  const data = room.data;
  const inviteCode = entryInviteCode ?? data.inviteCode;
  const blocked = busy || uploading || Boolean(pendingIntent);
  const me = data.members.find(member => member.userId === owner);
  const partner = data.members.find(member => member.userId !== owner);
  const terminal = ["completed", "ended", "expired"].includes(data.status);
  const languageName = languages.find(language => language.code === data.targetLanguageCode)?.name
    ?? data.targetLanguageCode.toUpperCase();

  return <div className="stack rooms-page">
    <header className="rooms-page__room-header"><div className="rooms-page__title"><div><span className="rooms-lobby__eyebrow">Private room</span><h1>I Spy together</h1></div>{!terminal ?
      <Button variant="quiet" disabled={blocked} onClick={() => void act("leave")}>Leave room</Button> : null}</div>
      <p>{languageName} · {partner ? `Playing with ${partner.displayName}` : "Waiting for your friend"}</p></header>
    {room.error ? <p role="alert">Connection interrupted. Your last saved round is shown; reconnecting…</p> : null}
    {error ? <div className="stack-2"><p role="alert">{error}</p>{pendingIntent ?
      <Button variant="secondary" disabled={busy} onClick={() => void act(pendingIntent)}>Retry action</Button> : rejectedCommand ?
        <Button variant="secondary" disabled={busy} onClick={() => {
          const { commandId: _key, expectedRevision: _revision, ...payload } = rejectedCommand.body;
          void act(rejectedCommand.intent, payload);
        }}>Retry with updated room</Button> : null}</div> : null}
    {busy ? <InlineLoader compact label="Saving your action…" /> : null}

    {data.status === "lobby" ? <>
      {!partner ? <Card className="stack"><h2>Invite one friend</h2>
        {inviteCode ? <><label className="field">Room code<input className="input" readOnly value={inviteCode} onFocus={event => event.target.select()} /></label>
          <label className="field">Invitation link<input className="input" readOnly value={`${window.location.origin}/rooms?code=${encodeURIComponent(inviteCode)}`}
            onFocus={event => event.target.select()} /></label></> :
          <p className="small muted">Use the private invitation you received when creating this room. Return to that page if you saved it in another tab.</p>}
        <p className="small muted">Your friend signs in with the same learning and explanation languages.</p></Card> : null}
      <section className="stack" aria-labelledby="room-photos-heading"><h2 id="room-photos-heading">Your shared photos · {data.photos.length} / 4</h2>
        <p>Each photo is one round. Add at least two different photos, then both get ready.</p>
        <p className="small muted">Photos you add are shared with the person in this room.</p>
        {data.photos.length < 4 ? <ImageUpload disabled={blocked} cameraEnabled={user?.cameraEnabled ?? false}
          onBusyChange={setUploading} dropzoneLabel="Add a photo to the room" onUploaded={image => void act("photos", { mediaAssetId: image.id })} /> : null}
        {data.photos.map((photo, index) => <RoomPhotoCard key={photo.id} roomId={roomId} photo={photo} number={index + 1}
          own={photo.ownerUserId === owner} ownerName={data.members.find(member => member.userId === photo.ownerUserId)?.displayName ?? "Your friend"}
          disabled={blocked} onRemove={() => void act(`photos/${encodeURIComponent(photo.id)}/remove`)}
          onRetry={() => void act(`photos/${encodeURIComponent(photo.id)}/retry`)}
          onReview={review => act(`photos/${encodeURIComponent(photo.id)}/review`, { review })} />)}
      </section>
      <Card className="stack"><h2>Ready to play?</h2><ul className="rooms-members">{data.members.map(member =>
        <li key={member.userId}><strong>{member.userId === owner ? "You" : member.displayName}</strong><span>{member.ready ? "Ready" : "Preparing"}</span></li>)}</ul>
        <p className="small muted">You’ll take turns across 2–4 different photos.</p>
        {canStartRoom(data) ? <Button disabled={blocked} onClick={() => void act("start")}>Start together</Button> :
          <Button variant={me?.ready ? "secondary" : "primary"} disabled={blocked || data.photos.length < 2 || data.photos.some(photo => photo.status !== "ready") || !partner}
            onClick={() => void act("ready", { ready: !me?.ready })}>{me?.ready ? "Keep preparing" : "I’m ready"}</Button>}
        {data.photos.some(photo => photo.status === "analyzing" || photo.status === "preparing") ? <InlineLoader compact label="Preparing your photos…" /> : null}
        {!partner ? <p className="small muted">Your friend needs to join before you can get ready.</p> : null}
      </Card>
    </> : data.status === "playing" && data.currentTurn ?
      <RoomPlay key={data.currentTurn.id} roomId={roomId} room={data} turn={data.currentTurn} disabled={blocked}
        acknowledged={me?.acknowledged ?? false} onClue={id => void act(`turns/${encodeURIComponent(data.currentTurn!.id)}/clue`, { clueOptionId: id })}
        onGuess={key => void act(`turns/${encodeURIComponent(data.currentTurn!.id)}/guess`, { objectKey: key })}
        onAcknowledge={() => void act(`turns/${encodeURIComponent(data.currentTurn!.id)}/ack`)} /> :
      <Card className="stack"><h2>{data.status === "completed" ? "You played every photo!" : data.status === "expired" ? "This room has expired" : "This game has ended"}</h2>
        <p>{data.status === "completed" ? `${data.successfulRounds} of ${data.roundCount} objects found together.` : "Your accepted practice is saved. Start a fresh room when you’re ready."}</p>
        <RoomContributions room={data} />
        <Button onClick={() => navigate("/ispy/friends", { replace: true })}>Play again</Button>
        <Button variant="quiet" onClick={() => navigate("/home")}>Back home</Button></Card>}
  </div>;
}

function RoomImage({ roomId, photoId, title, markers, selectable = false, selected, disabled = false, omitted = [], onSelect }: {
  roomId: string; photoId: string; title: string; markers?: RoomObject[]; selectable?: boolean;
  selected?: string | null; disabled?: boolean; omitted?: string[]; onSelect?: (key: string) => void;
}) {
  const [attempt, setAttempt] = useState(0);
  const source = `${roomId}:${photoId}:${attempt}`;
  const [imageState, setImageState] = useState<{ url: string | null; failed: boolean; source: string } | null>(null);
  const image = imageState?.source === source ? imageState.url : null;
  const failed = imageState?.source === source && imageState.failed;
  useEffect(() => {
    const controller = new AbortController();
    let url: string | null = null;
    void getRoomPhoto(roomId, photoId, controller.signal).then(blob => {
      if (controller.signal.aborted) return;
      url = URL.createObjectURL(blob);
      setImageState({ url, failed: false, source });
    }).catch(() => { if (!controller.signal.aborted) setImageState({ url: null, failed: true, source }); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [roomId, photoId, source]);

  if (failed) return <div className="rooms-photo__placeholder"><p role="alert">We couldn’t load this photo.</p>
    <Button variant="secondary" onClick={() => setAttempt(current => current + 1)}>Reload photo</Button></div>;
  if (!image) return <div className="rooms-photo__placeholder"><InlineLoader compact label="Preparing photo…" /></div>;
  return <div className="rooms-photo"><img src={image} alt={title} onError={() => setImageState({ url: null, failed: true, source })} />
    {markers?.map((object, index) => <button type="button" key={object.key} className={`rooms-marker${selected === object.key ? " rooms-marker--selected" : ""}`}
      style={{ left: `${Math.max(3, Math.min(97, object.x))}%`, top: `${Math.max(3, Math.min(97, object.y))}%` }}
      aria-label={`Object ${object.marker ?? index + 1}`} aria-pressed={selected === object.key}
      disabled={!selectable || disabled || omitted.includes(object.key)} tabIndex={selectable ? 0 : -1}
      onClick={() => onSelect?.(object.key)}>{object.marker ?? index + 1}</button>)}
  </div>;
}

function RoomPhotoCard({ roomId, photo, number, own, ownerName, disabled, onRemove, onRetry, onReview }: {
  roomId: string; photo: RoomPhoto; number: number; own: boolean; ownerName: string; disabled: boolean;
  onRemove: () => void; onRetry: () => void; onReview: (review: RoomPhotoReview) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState(false);
  const status = { queued: "Waiting to check", analyzing: "Checking your photo", awaitingReview: "Needs your review", preparing: "Preparing clues", ready: "Ready", failed: "Needs another look" }[photo.status];
  const reviewable = own && Boolean(photo.review) && (photo.status === "awaitingReview" || photo.status === "failed" || (editing && photo.status === "ready"));
  return <Card className="stack rooms-photo-card"><div className="rooms-photo-card__heading"><h3>{photo.title ?? `Photo ${number}`}</h3><span className="small muted">{own ? "Added by you" : `Added by ${ownerName}`}</span></div>
    {photo.imageUrl && !reviewable ? <RoomImage roomId={roomId} photoId={photo.id} title={photo.title ?? `Shared photo ${number}`} /> : !photo.imageUrl ?
      <div className="rooms-photo__placeholder">{photo.status === "failed" ? <p role="status">This photo isn’t available to share.</p> : <InlineLoader compact label={own ? "Checking the photo before sharing it…" : "Your friend’s photo is being checked before sharing."} />}</div> : null}
    <p className="small" role={photo.status === "failed" ? "alert" : "status"}>{own ? status : photo.status === "awaitingReview" ? "Your friend is reviewing this photo" : status}</p>
    {reviewable ? <PhotoReview key={`${photo.id}:${photo.status}`} roomId={roomId} photoId={photo.id} initial={photo.review!} disabled={disabled}
      onSave={review => { void onReview(review).then(saved => { if (saved) setEditing(false); }); }} /> : null}
    {own && photo.status === "ready" && !editing && photo.review ? <Button variant="quiet" disabled={disabled} onClick={() => setEditing(true)}>Review words and clues</Button> : null}
    {own && photo.status === "failed" ? <><p className="small muted">{photo.errorCode === "room_photo_no_clues" ? "Check the colours and locations, then save to prepare new clues." : "Review the photo or try checking it again."}</p>
      {photo.retryable ? <Button variant="secondary" disabled={disabled} onClick={onRetry}>Retry photo check</Button> : null}</> : null}
    {own ? <Button variant="quiet" disabled={disabled} onClick={onRemove}>Remove photo {number}</Button> : null}
  </Card>;
}

const relationLabels: { value: RoomRelationType; label: string }[] = [
  { value: "left_of", label: "left of" }, { value: "right_of", label: "right of" }, { value: "above", label: "above" },
  { value: "below", label: "below" }, { value: "on", label: "on" }, { value: "under", label: "under" }, { value: "inside", label: "inside" },
  { value: "in_front_of", label: "in front of" }, { value: "behind", label: "behind" }, { value: "next_to", label: "next to" }, { value: "near", label: "near" },
];

function PhotoReview({ roomId, photoId, initial, disabled, onSave }: { roomId: string; photoId: string; initial: RoomPhotoReview; disabled: boolean; onSave: (review: RoomPhotoReview) => void }) {
  const [draft, setDraft] = useState<RoomPhotoReview>(() => roomReviewPayload(initial));
  const [selected, setSelected] = useState(initial.objects.map(item => item.key));
  const [relationError, setRelationError] = useState<string | null>(null);
  const activeObjects = draft.objects.filter(item => selected.includes(item.key));
  const activeRelations = draft.relations.filter(item => selected.includes(item.subjectObjectKey) && selected.includes(item.referenceObjectKey));
  const valid = activeObjects.length >= 2 && activeObjects.length <= 6 && activeRelations.length <= 20
    && activeObjects.every(item => item.label.trim() && Number.isFinite(item.x) && Number.isFinite(item.y));
  const changeObject = (key: string, patch: Partial<RoomPhotoReview["objects"][number]>) => setDraft(current => ({ ...current,
    objects: current.objects.map(item => item.key === key ? { ...item, ...patch } : item) }));
  const addRelation = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const subject = String(values.get("subject") ?? "");
    const reference = String(values.get("reference") ?? "");
    if (subject === reference) { setRelationError("Choose two different objects for a location clue."); return; }
    if (draft.relations.some(item => item.subjectObjectKey === subject && item.referenceObjectKey === reference && item.relation === values.get("relation"))) {
      setRelationError("That location fact is already included."); return;
    }
    setRelationError(null);
    setDraft(current => ({ ...current, relations: [...current.relations, { key: crypto.randomUUID(), subjectObjectKey: subject,
      relation: String(values.get("relation")) as RoomRelationType, referenceObjectKey: reference }] }));
  };
  return <div className="stack rooms-review"><h3>Review the objects and facts</h3>
    <RoomImage roomId={roomId} photoId={photoId} title={draft.title ?? "Your photo for review"} markers={activeObjects.filter(item => Number.isFinite(item.x) && Number.isFinite(item.y)).map(item =>
      ({ key: item.key, word: item.label, translation: item.label, x: item.x, y: item.y, marker: draft.objects.indexOf(item) + 1 }))} />
    <label className="field">Photo title<input className="input" maxLength={100} disabled={disabled} value={draft.title ?? ""} onChange={event => setDraft(current => ({ ...current, title: event.target.value || null }))} /></label>
    <p className="small muted">Choose 2–6 objects. Correct names, marker positions, colours, and locations before sharing clues.</p>
    {draft.objects.map((object, index) => <fieldset className="rooms-review__object" disabled={disabled} key={object.key}>
      <legend>Object {index + 1}</legend><label className="rooms-review__include"><input type="checkbox" checked={selected.includes(object.key)}
        onChange={event => setSelected(current => event.target.checked ? [...current, object.key] : current.filter(key => key !== object.key))} />Use this object</label>
      {selected.includes(object.key) ? <><label className="field">Name<input className="input" value={object.label} maxLength={100} onChange={event => changeObject(object.key, { label: event.target.value })} /></label>
        <div className="rooms-review__coordinates"><label className="field">Move marker left / right<input className="input" type="range" min={0} max={100} value={object.x}
          onChange={event => changeObject(object.key, { x: Math.max(0, Math.min(100, event.target.valueAsNumber)) })} /></label>
          <label className="field">Move marker up / down<input className="input" type="range" min={0} max={100} value={object.y}
            onChange={event => changeObject(object.key, { y: Math.max(0, Math.min(100, event.target.valueAsNumber)) })} /></label></div>
        <label className="field">Colour, if clear<input className="input" value={object.color ?? ""} maxLength={40} placeholder="For example, red" onChange={event => changeObject(object.key, { color: event.target.value || null })} /></label></> : null}
    </fieldset>)}
    <h3>Locations you can see</h3><ul className="rooms-review__relations">{activeRelations.map(relation => <li key={relation.key}>
      <span>{activeObjects.find(item => item.key === relation.subjectObjectKey)?.label} · {relationLabels.find(item => item.value === relation.relation)?.label} · {activeObjects.find(item => item.key === relation.referenceObjectKey)?.label}</span>
      <Button variant="quiet" disabled={disabled} aria-label="Remove this location fact" onClick={() => setDraft(current => ({ ...current, relations: current.relations.filter(item => item.key !== relation.key) }))}>Remove</Button></li>)}</ul>
    {activeObjects.length >= 2 ? <form className="stack-2 rooms-review__relation-form" onSubmit={addRelation}>
      <label className="field">Object<select className="input" name="subject" disabled={disabled}>{activeObjects.map(item => <option value={item.key} key={item.key}>{item.label}</option>)}</select></label>
      <label className="field">Location<select className="input" name="relation" disabled={disabled}>{relationLabels.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label className="field">Compared with<select className="input" name="reference" disabled={disabled} defaultValue={activeObjects[1]?.key}>{activeObjects.map(item => <option value={item.key} key={item.key}>{item.label}</option>)}</select></label>
      <Button type="submit" variant="secondary" disabled={disabled || activeRelations.length >= 20}>Add location fact</Button>
      {relationError ? <p role="alert">{relationError}</p> : null}
    </form> : null}
    {!valid ? <p className="small muted">Select 2–6 named objects with valid marker positions.</p> : null}
    <Button disabled={disabled || !valid} onClick={() => onSave(roomReviewPayload({ ...draft, objects: activeObjects, relations: activeRelations }))}>Confirm photo facts</Button>
  </div>;
}

function RoomPlay({ roomId, room, turn, disabled, acknowledged, onClue, onGuess, onAcknowledge }: {
  roomId: string; room: RoomSnapshot; turn: RoomTurn; disabled: boolean; acknowledged: boolean;
  onClue: (id: string) => void; onGuess: (key: string) => void; onAcknowledge: () => void;
}) {
  const [choice, setChoice] = useState<string | null>(null);
  const [clue, setClue] = useState<string | null>(null);
  const [showWords, setShowWords] = useState(false);
  const guessing = turn.role === "guesser" && turn.phase === "guess";
  const target = turn.role === "sender" ? turn.objects.find(item => item.key === turn.targetObjectKey) : null;
  const revealed = turn.phase === "reveal" ? turn.objects.find(item => item.key === turn.result?.targetObjectKey) : null;
  const used = turn.guessedObjectKeys ?? [];
  const canGuess = guessing && Boolean(choice) && !used.includes(choice!);

  return <section className="stack rooms-play" aria-label={`Round ${turn.index + 1}`}>
    <div className="rooms-play__progress"><strong>Photo {turn.index + 1} of {room.roundCount}</strong><span>{room.successfulRounds} found together</span></div>
    <h2>{turn.phase === "reveal" ? "Let’s look together" : turn.role === "sender" ? "Give your friend a clue" : "Spot your friend’s object"}</h2>
    <RoomImage roomId={roomId} photoId={turn.photoId} title={`Shared photo for round ${turn.index + 1}`} markers={turn.objects}
      selectable={guessing} selected={turn.phase === "reveal" ? turn.result?.targetObjectKey : turn.role === "sender" ? turn.targetObjectKey : choice}
      disabled={disabled} omitted={used} onSelect={setChoice} />
    {turn.phase === "compose" && turn.role === "sender" ? <Card className="stack">
      <p>Your object: <strong>{target?.word ?? "Look at your marked object"}</strong>{target ? ` · marker ${target.marker ?? turn.objects.indexOf(target) + 1}` : ""}</p>
      <p className="small muted">Choose a checked phrase. Your friend sees only the clue.</p>
      <div className="rooms-choices" role="group" aria-label="Choose your clue">{turn.clueOptions?.map(option =>
        <button type="button" key={option.id} className={`rooms-choice${clue === option.id ? " rooms-choice--selected" : ""}`}
          aria-pressed={clue === option.id} disabled={disabled} onClick={() => setClue(option.id)}>{option.text}</button>)}</div>
      <Button disabled={disabled || !clue} onClick={() => onClue(clue!)}>Send clue</Button>
    </Card> : turn.phase === "compose" ? <InlineLoader label="Your friend is choosing a clue for this photo…" /> : null}
    {turn.clue ? <Card className="stack-2"><strong>Your {turn.role === "sender" ? "saved" : "friend’s"} clue</strong><p lang={room.targetLanguageCode}>{turn.clue}</p></Card> : null}
    {guessing ? <>
      {turn.guessCount > 0 ? <Feedback tone="warn"><p>Not quite. Try one more object.</p></Feedback> : null}
      <p className="small muted">Choose a numbered marker or the matching number below.</p>
      <div className="rooms-choices rooms-choices--numbers" role="group" aria-label="Choose the object">
        {turn.objects.map((object, index) => <button type="button" key={object.key} aria-pressed={choice === object.key}
          className={`rooms-choice${choice === object.key ? " rooms-choice--selected" : ""}`} disabled={disabled || used.includes(object.key)} onClick={() => setChoice(object.key)}>
          <span>Object {object.marker ?? index + 1}</span>{used.includes(object.key) ? <span className="small">Already tried</span> : null}</button>)}
      </div>
      <Button disabled={disabled || !canGuess} onClick={() => onGuess(choice!)}>Check my guess</Button>
    </> : turn.phase === "guess" ? <InlineLoader label={turn.guessCount > 0 ? "Your friend is trying another object…" : "Your friend is looking for the object…"} /> : null}
    {turn.phase === "reveal" ? <>
      <Feedback tone={turn.result?.isCorrect ? "good" : "warn"}><div className="stack-2" role="status">
        <strong>{turn.result?.isCorrect ? "You found it together!" : "Here’s the object"}</strong>
        <span>{turn.result?.explanation ?? "Compare the clue with the highlighted marker in the photo."}</span>
        {revealed ? <span>Marker {revealed.marker ?? turn.objects.indexOf(revealed) + 1}: <strong>{revealed.word}</strong> · {revealed.translation}</span> : null}
      </div></Feedback>
      <Button disabled={disabled || acknowledged} onClick={onAcknowledge}>{acknowledged ? "Waiting for your friend…" : turn.index + 1 === room.roundCount ? "See our recap" : "Next photo"}</Button>
    </> : null}
    <details open={showWords} onToggle={event => setShowWords(event.currentTarget.open)} className="rooms-word-bank">
      <summary>Photo words and translations</summary><ul>{turn.objects.map((object, index) => <li key={object.key}>
        <span>{object.marker ?? index + 1}. <strong>{object.word}</strong></span><span>{object.translation}</span></li>)}</ul>
    </details>
  </section>;
}

function RoomContributions({ room }: { room: RoomSnapshot }) {
  return <section className="stack-2" aria-label="Each person’s practice"><h3>Your own practice</h3>{room.contributions.map(item =>
    <div key={item.userId} className="rooms-contribution"><strong>{item.userId === room.meId ? "You" : room.members.find(member => member.userId === item.userId)?.displayName ?? "Your friend"}</strong>
      <span>{item.cluesSent} {item.cluesSent === 1 ? "clue" : "clues"} sent · {item.guessesMade} {item.guessesMade === 1 ? "guess" : "guesses"} · {item.correctGuesses} found</span>
      <span className="small muted rooms-contribution__rewards">+{item.basilEarned} Basil leaves · <span className="basil-reward"><BasilIcon size={15} />+{item.xpEarned} Basil</span></span></div>)}</section>;
}

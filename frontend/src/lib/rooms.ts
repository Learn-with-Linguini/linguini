import { request, requestBlob, write } from "./api.ts";
import type { LanguageProfile } from "./api.ts";

export type RoomStatus = "lobby" | "playing" | "completed" | "ended" | "expired";
export type RoomRelationType = "left_of" | "right_of" | "above" | "below" | "on" | "under" | "inside" | "in_front_of" | "behind" | "next_to" | "near";
export interface RoomReviewObject { key: string; label: string; x: number; y: number; color: string | null }
export interface RoomRelation { key: string; subjectObjectKey: string; relation: RoomRelationType; referenceObjectKey: string }
export interface RoomPhotoReview { title?: string | null; objects: RoomReviewObject[]; relations: RoomRelation[] }
export interface RoomObject { key: string; label?: string; word: string; translation: string; x: number; y: number; marker?: number }
export interface RoomPhoto {
  id: string; ownerUserId: string | null; mediaAssetId: string | null;
  status: "queued" | "analyzing" | "awaitingReview" | "preparing" | "ready" | "failed";
  imageUrl: string | null; title?: string; errorCode?: string | null; errorMessage?: string | null; retryable?: boolean; review?: RoomPhotoReview | null;
}
export interface RoomTurn {
  id: string; index: number; role: "sender" | "guesser"; phase: "compose" | "guess" | "reveal";
  photoId: string; imageUrl: string; objects: RoomObject[]; clue: string | null;
  targetObjectKey?: string | null; clueOptions?: { id: string; text: string }[] | null; guessCount: number;
  guessedObjectKeys?: string[];
  result?: { isCorrect: boolean; targetObjectKey?: string; message?: string; explanation?: string } | null;
}
export interface RoomSnapshot {
  id: string; status: RoomStatus; revision: number; expiresAt: string; meId: string;
  hostUserId?: string | null; inviteCode?: string | null;
  sourceLanguageCode: string; targetLanguageCode: string; proficiencyLevel: LanguageProfile["proficiencyLevel"];
  members: { userId: string; displayName: string; seat: number; ready: boolean; acknowledged: boolean }[];
  photos: RoomPhoto[]; currentTurn: RoomTurn | null; successfulRounds: number; roundCount: number;
  contributions: { userId: string; cluesSent: number; guessesMade: number; correctGuesses: number; basilEarned: number; xpEarned: number }[];
}
export interface RoomEntry { room: RoomSnapshot; inviteCode?: string | null }
export interface PendingRoomCommand { intent: string; body: { commandId: string; expectedRevision: number } & Record<string, unknown> }

export const roomQueryKeys = {
  active: (owner: string, profile: string) => ["rooms", owner, profile, "active"] as const,
  snapshot: (owner: string, profile: string, room: string) => ["rooms", owner, profile, room] as const,
};
export const roomPhotoPath = (roomId: string, photoId: string) =>
  `/api/v1/rooms/${encodeURIComponent(roomId)}/photos/${encodeURIComponent(photoId)}/image?width=640`;
export const getRoomPhoto = (roomId: string, photoId: string, signal?: AbortSignal) => requestBlob(roomPhotoPath(roomId, photoId), signal);

/** Defense in depth: recipient caches never keep sender-only answers or another owner's review. */
export function sanitizeRoomSnapshot(room: RoomSnapshot): RoomSnapshot {
  const turn = room.currentTurn;
  let publicTurn = turn;
  if (turn?.role === "guesser") {
    const { targetObjectKey: _target, clueOptions: _options, ...recipient } = turn;
    publicTurn = { ...recipient, result: turn.phase === "reveal" ? turn.result : null };
  }
  return { ...room, inviteCode: room.hostUserId === room.meId && room.status === "lobby" ? room.inviteCode : null,
    currentTurn: publicTurn, photos: room.photos.map(photo => {
    if (photo.ownerUserId === room.meId) return photo;
    const { review: _review, ...shared } = photo;
    return { ...shared, imageUrl: ["queued", "analyzing"].includes(photo.status) ? null : photo.imageUrl };
  }) };
}

/** Analysis has private provenance and version fields; review accepts only editable facts. */
export function roomReviewPayload(review: RoomPhotoReview): RoomPhotoReview {
  return {
    ...(review.title ? { title: review.title.slice(0, 100) } : {}),
    objects: review.objects.map(({ key, label, x, y, color }) => ({ key, label, x, y, color })),
    relations: review.relations.map(({ key, subjectObjectKey, relation, referenceObjectKey }) =>
      ({ key, subjectObjectKey, relation, referenceObjectKey })),
  };
}

export const getActiveRoom = async (signal?: AbortSignal): Promise<RoomSnapshot | null> => {
  const room = await request<RoomSnapshot | null>("/api/v1/rooms/active", signal);
  return room ? sanitizeRoomSnapshot(room) : null;
};
export const getRoom = async (id: string, signal?: AbortSignal) =>
  sanitizeRoomSnapshot(await request<RoomSnapshot>(`/api/v1/rooms/${encodeURIComponent(id)}`, signal));
export const createRoom = async (languageProfileId: string, commandId: string): Promise<RoomEntry> => {
  const entry = await write<RoomEntry>("/api/v1/rooms", "POST", { languageProfileId, commandId });
  return { ...entry, room: sanitizeRoomSnapshot(entry.room) };
};
export const joinRoom = async (languageProfileId: string, inviteCode: string, commandId: string): Promise<RoomEntry> => {
  const entry = await write<RoomEntry>("/api/v1/rooms/join", "POST", { languageProfileId, inviteCode, commandId });
  return { ...entry, room: sanitizeRoomSnapshot(entry.room) };
};
export const sendRoomCommand = async (roomId: string, command: PendingRoomCommand) =>
  sanitizeRoomSnapshot(await write<RoomSnapshot>(`/api/v1/rooms/${encodeURIComponent(roomId)}/${command.intent}`, "POST", command.body));

export function prepareRoomCommand(intent: string, expectedRevision: number, payload: Record<string, unknown>,
  pending: PendingRoomCommand | null, newId: () => string = () => crypto.randomUUID()): PendingRoomCommand {
  return pending ?? { intent, body: { ...payload, commandId: newId(), expectedRevision } };
}

export function canStartRoom(room: RoomSnapshot): boolean {
  return room.status === "lobby" && room.members.length === 2 && room.members.every(member => member.ready)
    && room.photos.length >= 2 && room.photos.length <= 4 && room.photos.every(photo => photo.status === "ready");
}
export function roomMatchesProfile(room: RoomSnapshot, profile: LanguageProfile | null | undefined): boolean {
  return Boolean(profile && room.targetLanguageCode.toLowerCase() === profile.targetLanguageCode.toLowerCase()
    && room.sourceLanguageCode.toLowerCase() === profile.sourceLanguageCode.toLowerCase()
    && room.proficiencyLevel === profile.proficiencyLevel);
}

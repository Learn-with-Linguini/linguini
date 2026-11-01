import { request, requestBlob, write } from "./api.ts";

export interface ChatPerson { id: string; displayName: string; avatar?: string | null; avatarUrl?: string | null }
export interface ChatCheatsheet { missionId: string; practiceLevel: string; contentVersion: number }
export interface ChatObject {
  key: string; label: string; word: string; translation: string;
  x: number; y: number; width?: number; height?: number;
}
export interface ChatClueOption {
  id: string; text: string; translation: string;
  concept: "adjective" | "position" | "quantity" | "identity";
  cheatSheet?: ChatCheatsheet | null;
}
export interface ChatMessage {
  id: string; type: "system" | "clue" | "followUpClue" | "guess" | "incorrectResult" | "correctResult" | "reveal";
  senderId?: string | null; text?: string | null; x?: number | null; y?: number | null;
  isCorrect?: boolean | null; createdAt: string;
}
export interface ChatRound {
  id: string; senderId: string;
  status: "selectingTarget" | "composingClue" | "awaitingGuess" | "awaitingFollowUp" | "completed" | "cancelled";
  photoStatus: "analyzing" | "ready" | "failed"; imageUrl: string | null; createdAt: string;
  completedAt?: string | null; objects: ChatObject[]; target?: ChatObject | null;
  clueOptions: ChatClueOption[]; messages: ChatMessage[]; error?: string | null; retryable: boolean;
}
export interface ChatSnapshot {
  id: string; status: "waiting" | "active" | "left" | "blocked"; revision: number; meId: string;
  targetLanguageCode: string; viewerLevel: string; partner: ChatPerson | null; creator: ChatPerson;
  inviteStatus: "open" | "accepted" | "expired" | "revoked"; createdAt: string; updatedAt: string;
  activeRound: ChatRound | null; rounds: ChatRound[];
}
export interface ChatInvitePreview {
  status: "open" | "full" | "expired" | "revoked";
  creator?: ChatPerson; targetLanguageCode?: string;
}
export interface ChatHelp {
  explanation: string; vocabulary: { word: string; meaning: string }[]; hint?: string | null;
  cheatsheetRefs: { missionCode: string; level: string; contentVersion?: number }[];
}
export interface ChatCommand {
  intent: string; body: { commandId: string; expectedRevision: number } & Record<string, unknown>;
}
export interface ChatEntry { chat: ChatSnapshot; inviteToken: string }
export type ChatPoint = { x: number; y: number };

const prefix = "/api/v1/friend-chats";
const chatPath = (id: string) => `${prefix}/${encodeURIComponent(id)}`;
export const chatRoundIntent = (roundId: string, action: string) => `rounds/${encodeURIComponent(roundId)}/${action}`;
export const friendChatKeys = {
  list: (owner: string, profile: string) => ["friend-chats", owner, profile, "list"] as const,
  chat: (owner: string, profile: string, id: string) => ["friend-chats", owner, profile, id] as const,
};

/** Receiver caches cannot retain sender-only drafts or geometry, even after a malformed response. */
export function safeFriendChat(chat: ChatSnapshot): ChatSnapshot {
  const safeRound = (round: ChatRound): ChatRound => round.senderId === chat.meId || round.status === "completed"
    ? round : { ...round, objects: [], target: null, clueOptions: [] };
  return { ...chat, activeRound: chat.activeRound ? safeRound(chat.activeRound) : null, rounds: chat.rounds.map(safeRound) };
}
export const getFriendChats = async (signal?: AbortSignal) =>
  (await request<ChatSnapshot[]>(prefix, signal)).map(safeFriendChat);
export const getFriendChat = async (id: string, signal?: AbortSignal) =>
  safeFriendChat(await request<ChatSnapshot>(chatPath(id), signal));
export const createFriendChat = (languageProfileId: string, commandId: string) =>
  write<ChatEntry>(prefix, "POST", { languageProfileId, commandId });
export const previewChatInvite = (inviteToken: string) =>
  write<ChatInvitePreview>(`${prefix}/invites/preview`, "POST", { inviteToken });
export const joinFriendChat = async (languageProfileId: string, inviteToken: string, commandId: string) =>
  safeFriendChat(await write<ChatSnapshot>(`${prefix}/join`, "POST", { languageProfileId, inviteToken, commandId }));
export const sendChatCommand = <T = ChatSnapshot>(id: string, command: ChatCommand) =>
  write<T>(`${chatPath(id)}/${command.intent}`, "POST", command.body);
export const getChatHelp = (id: string, roundId: string) =>
  write<ChatHelp>(`${chatPath(id)}/${chatRoundIntent(roundId, "help")}`, "POST", {});
export const getChatPhoto = (id: string, roundId: string, signal?: AbortSignal) =>
  requestBlob(`${chatPath(id)}/${chatRoundIntent(roundId, "image")}?width=640`, signal);

export function prepareChatCommand(intent: string, revision: number, payload: Record<string, unknown>, pending: ChatCommand | null): ChatCommand {
  return pending ?? { intent, body: { ...payload, commandId: crypto.randomUUID(), expectedRevision: revision } };
}

const draftPrefix = "linguini-friend-chat:";
export const chatDraftKey = (owner: string, chatId: string, roundId: string) => `${draftPrefix}${owner}:${chatId}:${roundId}`;
export function readChatDraft<T>(key: string, fallback: T): T {
  try { const value = sessionStorage.getItem(key); return value ? JSON.parse(value) as T : fallback; }
  catch { return fallback; }
}
export function saveChatDraft(key: string, value: unknown): void {
  try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, JSON.stringify(value)); }
  catch { /* Draft storage is optional when the browser disables it. */ }
}
export function clearChatDrafts(owner: string, chatId: string, roundId?: string): void {
  try {
    const prefix = chatDraftKey(owner, chatId, roundId ?? "");
    for (const key of Object.keys(sessionStorage)) if (key.startsWith(prefix)) sessionStorage.removeItem(key);
  } catch { /* A saved server round remains available without browser storage. */ }
}
export function activateChatDraftOwner(owner: string): void {
  if (!owner) return;
  try {
    for (const key of Object.keys(sessionStorage)) {
      if (key.startsWith(draftPrefix) && !key.startsWith(`${draftPrefix}${owner}:`)) sessionStorage.removeItem(key);
    }
  } catch { /* Server state is still protected when browser storage is unavailable. */ }
}
export const friendInviteStorageKey = "linguini-friend-chat-invite";
export function readFriendInvite(): string {
  try { return sessionStorage.getItem(friendInviteStorageKey) ?? (window as Window & { linguiniFriendInvite?: string }).linguiniFriendInvite ?? ""; } catch { return (window as Window & { linguiniFriendInvite?: string }).linguiniFriendInvite ?? ""; }
}
export function rememberFriendInvite(token: string): void {
  (window as Window & { linguiniFriendInvite?: string }).linguiniFriendInvite = token;
  try { if (token) sessionStorage.setItem(friendInviteStorageKey, token); else sessionStorage.removeItem(friendInviteStorageKey); } catch { /* Invitation may still be pasted manually. */ }
}
export const friendInviteUrl = (token: string) => `${window.location.origin}/ispy/friends#invite=${encodeURIComponent(token)}`;

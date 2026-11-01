import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import { friendlyError, queryKeys } from "../lib/queryKeys";
import { activateChatDraftOwner, chatDraftKey, friendChatKeys, getFriendChat, prepareChatCommand, readChatDraft, safeFriendChat, saveChatDraft, sendChatCommand } from "../lib/friendChats";
import type { ChatCommand, ChatSnapshot } from "../lib/friendChats";

export function useFriendChat(owner: string, profile: string, chatId: string) {
  const client = useQueryClient();
  const key = friendChatKeys.chat(owner, profile, chatId);
  const pendingKey = chatDraftKey(owner, chatId, "command");
  const pending = useRef<ChatCommand | null>(readChatDraft(pendingKey, null));
  const busyRef = useRef(false);
  const alive = useRef(true);
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(typeof navigator !== "undefined" && navigator.onLine === false);
  const [error, setError] = useState<string | null>(null);
  const [hasPending, setHasPending] = useState(() => Boolean(readChatDraft(pendingKey, null)));
  const query = useQuery({ queryKey: key, enabled: Boolean(owner && profile), retry: false,
    queryFn: async ({ signal }) => {
      const next = await getFriendChat(chatId, signal);
      if (next.meId !== owner) throw new Error("This chat belongs to another account.");
      const previous = client.getQueryData<ChatSnapshot>(key);
      return previous && previous.revision > next.revision ? previous : next;
    }, refetchInterval: query => busy || ["left", "blocked"].includes(query.state.data?.status ?? "") ? false : 3_000,
    refetchIntervalInBackground: false, refetchOnWindowFocus: "always", refetchOnReconnect: true });

  const refetch = query.refetch;
  useEffect(() => {
    alive.current = true;
    activateChatDraftOwner(owner);
    const online = () => { setOffline(false); void refetch(); };
    const offline = () => setOffline(true);
    window.addEventListener("online", online); window.addEventListener("offline", offline);
    return () => { alive.current = false; window.removeEventListener("online", online); window.removeEventListener("offline", offline); };
  }, [chatId, owner, refetch]);

  const command = async <T = ChatSnapshot>(intent: string, payload: Record<string, unknown> = {}): Promise<T | null> => {
    if (!query.data || busyRef.current || offline) return null;
    const request = prepareChatCommand(intent, query.data.revision, payload, pending.current);
    pending.current = request; saveChatDraft(pendingKey, request); setHasPending(true);
    busyRef.current = true; setBusy(true); setError(null);
    await client.cancelQueries({ queryKey: key });
    try {
      const result = await sendChatCommand<T>(chatId, request);
      if (!alive.current) return null;
      const snapshot = result as T & Partial<ChatSnapshot> & { chat?: ChatSnapshot };
      const chat = snapshot.chat ?? (snapshot.meId ? snapshot as ChatSnapshot : null);
      if (chat) {
        if (chat.meId !== owner) throw new Error("Your account changed. Open this chat again.");
        const next = safeFriendChat(chat);
        client.setQueryData<ChatSnapshot>(key, previous => previous && previous.revision > next.revision ? previous : next);
        void client.invalidateQueries({ queryKey: friendChatKeys.list(owner, profile) });
        void client.invalidateQueries({ queryKey: queryKeys.progress(profile) });
      }
      pending.current = null; saveChatDraft(pendingKey, null); setHasPending(false);
      return result;
    } catch (reason) {
      if (!alive.current) return null;
      if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500) {
        pending.current = null; saveChatDraft(pendingKey, null); setHasPending(false);
        await query.refetch();
      }
      setError(reason instanceof ApiError ? reason.message : friendlyError(reason));
      return null;
    } finally { busyRef.current = false; if (alive.current) setBusy(false); }
  };
  const retry = () => pending.current ? command(pending.current.intent) : query.refetch();
  return { query, command, retry, busy, offline, error, hasPending, blocked: busy || offline || hasPending };
}

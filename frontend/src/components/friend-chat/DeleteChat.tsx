import { useState } from "react";
import { ApiError } from "../../lib/api";
import { deleteFriendChat } from "../../lib/friendChats";
import type { ChatSnapshot } from "../../lib/friendChats";
import { friendlyError } from "../../lib/queryKeys";
import { trackAction } from "../../lib/analytics";
import { Button } from "../ui";

/** Delete an ended chat or unanswered invite, after an inline confirmation. */
export function DeleteChat({ chat, onDeleted, compact = false }: { chat: ChatSnapshot; onDeleted: () => void; compact?: boolean }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const invite = chat.status === "waiting";
  const friend = chat.partner?.displayName ?? "Your friend";
  const remove = async () => {
    setBusy(true); setError(null);
    try {
      await deleteFriendChat(chat.id);
    } catch (reason) {
      // Already gone from this list counts as deleted.
      if (!(reason instanceof ApiError && reason.status === 404)) { setError(friendlyError(reason)); setBusy(false); return; }
    }
    trackAction("ispy_friend_chat_deleted", { status: chat.status });
    onDeleted();
  };
  if (!confirming) return <Button variant="quiet" className={compact ? "friend-delete__open" : undefined} disabled={busy}
    aria-label={`${invite ? "Delete invite" : "Delete chat"}${chat.partner ? ` with ${friend}` : ""}`} onClick={() => setConfirming(true)}>
    {invite ? "Delete invite" : "Delete chat"}</Button>;
  return <div className="stack-2 friend-delete" role="group" aria-label={invite ? "Delete this invite" : "Delete this chat"}>
    <p className="small">{invite ? "Delete this invite? The link will stop working."
      : `Delete this chat? It’s removed from your chats, along with your photos from it that aren’t used anywhere else. ${friend} keeps their copy until they delete it too.`}</p>
    {error ? <p role="alert" className="small">{error}</p> : null}
    <div className="friend-delete__actions">
      <Button variant="secondary" disabled={busy} onClick={() => void remove()}>{busy ? "Deleting…" : invite ? "Delete invite" : "Delete chat"}</Button>
      <Button variant="quiet" disabled={busy} onClick={() => { setConfirming(false); setError(null); }}>Keep it</Button>
    </div>
  </div>;
}

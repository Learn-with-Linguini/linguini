import { useState } from "react";
import { trackAction } from "../../lib/analytics";
import { chatDraftKey, friendInviteUrl, readChatDraft, saveChatDraft } from "../../lib/friendChats";
import type { ChatEntry, ChatSnapshot } from "../../lib/friendChats";
import { Button, Card } from "../ui";

type Command = <T = ChatSnapshot>(intent: string, payload?: Record<string, unknown>) => Promise<T | null>;
export function InviteControls({ chat, command, disabled }: { chat: ChatSnapshot; command: Command; disabled: boolean }) {
  const storageKey = chatDraftKey(chat.meId, chat.id, "invite");
  const [token, setToken] = useState<string>(() => readChatDraft(storageKey, ""));
  const [message, setMessage] = useState<string | null>(null);
  const link = token && chat.inviteStatus === "open" ? friendInviteUrl(token) : "";
  const rotate = async () => {
    const result = await command<ChatEntry>("invite");
    if (result) { saveChatDraft(storageKey, result.inviteToken); setToken(result.inviteToken); setMessage(result.inviteToken ? "Your new invitation is ready. Older links no longer work." : "Create a new invitation link to share this chat."); trackAction("ispy_friend_invite_created"); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(link); setMessage("Invitation copied."); trackAction("ispy_friend_invite_copied"); }
    catch { setMessage("Select the invitation link above and copy it to share."); }
  };
  const share = async () => {
    if (!navigator.share) { await copy(); return; }
    try { await navigator.share({ title: "Join my Linguini I-Spy chat", text: "Let’s send each other photo clues.", url: link }); trackAction("ispy_friend_invite_shared"); }
    catch (reason) { if (!(reason instanceof DOMException && reason.name === "AbortError")) setMessage("Sharing is unavailable. Copy the link instead."); }
  };
  return <Card className="stack friend-invite"><h2>Your I-Spy chat is ready.</h2><p>Share this link with one friend.</p>
    {link ? <><label className="field">Private invitation<input className="input" readOnly value={link} onFocus={event => event.target.select()} /></label>
      <Button disabled={disabled} onClick={() => void copy()}>Copy link</Button><Button variant="secondary" disabled={disabled} onClick={() => void share()}>Share invite</Button>
      <Button variant="quiet" disabled={disabled} onClick={() => void rotate()}>Replace invitation link</Button>
      <Button variant="quiet" disabled={disabled} onClick={async () => { if (await command("invite/revoke")) { setToken(""); saveChatDraft(storageKey, null); trackAction("ispy_friend_invite_revoked"); } }}>Revoke invitation</Button>
    </> : <><p>{chat.inviteStatus === "expired" ? "This invitation has expired." : chat.inviteStatus === "revoked" ? "This invitation was revoked." : "Your chat is saved. Create a new invitation link to share it."}</p>
      <Button disabled={disabled} onClick={() => void rotate()}>Create a new invite link</Button></>}
    {message ? <p role="status" className="small">{message}</p> : null}
  </Card>;
}

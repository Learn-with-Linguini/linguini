import type { ChatPerson, ChatSnapshot } from "../../lib/friendChats";
import { ChatAvatar } from "./ChatAvatar";

/** Both players in a friend I-Spy chat, with the signed-in learner tagged "You". */
export function ChatPlayers({ me, partner, status }: { me: ChatPerson; partner: ChatPerson | null; status: ChatSnapshot["status"] }) {
  return <ul className="friend-players" aria-label="Players">
    <li className="friend-players__player friend-players__player--me">
      <ChatAvatar person={me} />
      <span className="friend-players__name"><strong>{me.displayName}</strong><span className="friend-players__tag">You</span></span>
    </li>
    <li className="friend-players__player">
      {partner ? <>
        <ChatAvatar person={partner} />
        <span className="friend-players__name"><strong>{partner.displayName}</strong>
          {status === "left" ? <span className="small muted">Left the chat</span> : status === "blocked" ? <span className="small muted">Blocked</span> : null}</span>
      </> : <>
        <span className="friend-avatar friend-players__empty" aria-hidden="true">?</span>
        <span className="friend-players__name"><strong>Your friend</strong><span className="small muted">{status === "waiting" ? "Waiting to join" : "Not joined"}</span></span>
      </>}
    </li>
  </ul>;
}

import { useState } from "react";
import type { ChatPerson } from "../../lib/friendChats";
import { PASTA_AVATARS } from "../../lib/onboardingDraft";
import type { PastaAvatar } from "../../data/types";

export function ChatAvatar({ person }: { person: ChatPerson | null }) {
  const [failed, setFailed] = useState(false);
  const avatar = person?.avatar && PASTA_AVATARS.includes(person.avatar as PastaAvatar) ? `/pasta-assets/${person.avatar}.png` : person?.avatarUrl;
  return <span className="friend-avatar" aria-hidden="true">{avatar && !failed ?
    <img src={avatar} alt="" referrerPolicy="no-referrer" onError={() => setFailed(true)} /> :
    (person?.displayName.trim().charAt(0).toLocaleUpperCase() || "?")}</span>;
}

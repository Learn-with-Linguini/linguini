import { useEffect, useId, useRef } from "react";
import { BADGE_MIN_CORRECT_PERCENT, batchAccuracy, type MissionBatch } from "../lib/gamification";
import { BadgeArt } from "./MissionBadges";
import { Button, Card } from "./ui";
import "./gamification.css";

const SKIPPED = "Complete the mission's tasks without skipping.";

/** What this session did for each finished mission's badge; missions with no news are left out. */
export function SummaryBadges({ batches }: { batches: MissionBatch[] }) {
  const earned = batches.filter(batch => batch.badgeEarned);
  const missed = batches.filter(batch => batch.status === "review");
  if (!earned.length && !missed.length) return null;
  return <Card><section className="stack-2" aria-labelledby="summary-badges-title">
    <h2 id="summary-badges-title">Badges</h2>
    {earned.map(batch => <div key={batch.missionId} className="summary-badge">
      <span className="chef-badge chef-badge--small"><BadgeArt missionId={batch.missionId} /></span>
      <div><strong>New badge: {batch.name}</strong><p className="small muted">{batch.badgeEarned} · {batchAccuracy(batch)}% correct</p></div>
    </div>)}
    {missed.map(batch => <div key={batch.missionId} className="summary-badge">
      <span className="chef-badge chef-badge--small chef-badge--empty"><BadgeArt missionId={batch.missionId} /></span>
      <div><strong>{batch.name}</strong><p className="small muted">{batch.requirements.includes(SKIPPED)
        ? "Finish every task without skipping to earn this badge."
        : `You got ${batchAccuracy(batch)}% correct. Try again and get more than ${BADGE_MIN_CORRECT_PERCENT}% to earn this badge.`}</p></div>
    </div>)}
  </section></Card>;
}

/** Celebrates the badges this session earned; closes with its button, Escape or the backdrop. */
export function BadgeEarnedModal({ batches, onClose }: { batches: MissionBatch[]; onClose: () => void }) {
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  useEffect(() => {
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  return <div className="help-modal__backdrop" onMouseDown={onClose}>
    <section ref={dialogRef} className="help-modal badge-earned" role="dialog" aria-modal="true" aria-labelledby={titleId} onMouseDown={event => event.stopPropagation()}>
      <h2 id={titleId}>{batches.length === 1 ? "New badge earned!" : "New badges earned!"}</h2>
      <div className="badge-earned__list">{batches.map(batch => <div key={batch.missionId} className="badge-earned__item">
        <span className="chef-badge"><BadgeArt missionId={batch.missionId} /></span>
        <strong>{batch.name}</strong><span className="small muted">{batch.badgeEarned}</span>
      </div>)}</div>
      <Button block onClick={onClose}>Nice!</Button>
    </section>
  </div>;
}

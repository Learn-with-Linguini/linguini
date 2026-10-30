import { useGamification } from "../state/gamification";
import { BADGE_LEVELS, EARNABLE_BADGE_LEVELS, earnedBadgeLevels, type MissionBadge } from "../lib/gamification";
import { missionBadgeAsset } from "../lib/missionBadges";
import { MissionIllustration } from "./MissionIllustration";
import { LockIcon } from "./icons";
import { Button, Card } from "./ui";
import "./gamification.css";

export function BadgeArt({ missionId }: { missionId: string }) {
  const asset = missionBadgeAsset(missionId);
  return asset ? <img src={asset} alt="" width="96" height="96" loading="lazy" /> : <MissionIllustration missionId={missionId} />;
}

export function ChefBadge({ mission }: { mission: MissionBadge }) {
  const label = mission.badgeLevel ? mission.badgeLevel : mission.available ? "badge not yet earned" : "unlocks at a higher level";
  return <span className={`chef-badge chef-badge--${mission.badgeLevel?.toLowerCase().replaceAll(" ", "-") ?? "empty"}`} aria-label={`${mission.name}: ${label}`}>
    <BadgeArt missionId={mission.missionId} />
    {!mission.available && !mission.badgeLevel ? <span className="chef-badge__lock"><LockIcon size={22} /></span> : null}
  </span>;
}

/** One dot per level: earned dots fill, levels not yet offered stay faint. */
function BadgeLevelDots({ mission }: { mission: MissionBadge }) {
  const earned = earnedBadgeLevels(mission.badgeLevel);
  return <p className="badge-level"><span className="badge-level__dots" aria-hidden="true">{BADGE_LEVELS.map((level, index) =>
    <span key={level} className={`badge-level__dot${index < earned ? " is-earned" : index >= EARNABLE_BADGE_LEVELS ? " is-coming" : ""}`} />)}</span>
    {mission.badgeLevel ? <span className="small muted">{mission.badgeLevel}</span> : null}</p>;
}

export function MissionBadges() {
  const progress = useGamification();
  return <section className="stack" aria-labelledby="mission-badges-title"><h2 id="mission-badges-title">Your Chef Badges</h2>
    {progress.isPending ? <p role="status">Loading your badges…</p> : progress.isError ? <div><p role="alert">We couldn’t load your badges.</p>
      <Button variant="quiet" onClick={() => void progress.refetch()}>Retry badges</Button></div> :
      <div className="mission-badges">{progress.data?.missions.map(mission => <Card plain key={mission.missionId}>
        <div className="mission-badges__heading"><ChefBadge mission={mission} /><div><h3>{mission.name}</h3><p className="small muted">{mission.skill}</p><BadgeLevelDots mission={mission} /></div></div>
      </Card>)}</div>}
  </section>;
}

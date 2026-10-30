import { useGamification } from "../state/gamification";
import { type MissionBadge } from "../lib/gamification";
import { missionBadgeAsset } from "../lib/missionBadges";
import { MissionIllustration } from "./MissionIllustration";
import { Button, Card } from "./ui";
import "./gamification.css";

export function ChefBadge({ mission }: { mission: MissionBadge }) {
  const asset = missionBadgeAsset(mission.missionId);
  return <span className={`chef-badge chef-badge--${mission.badgeLevel?.toLowerCase().replaceAll(" ", "-") ?? "empty"}`} aria-label={mission.badgeLevel ? `${mission.name}: ${mission.badgeLevel}` : `${mission.name}: badge not yet earned`}>
    {asset ? <img src={asset} alt="" width="96" height="96" loading="lazy" /> : <MissionIllustration missionId={mission.missionId} />}
  </span>;
}

export function MissionBadges() {
  const progress = useGamification();
  return <section className="stack" aria-labelledby="mission-badges-title"><h2 id="mission-badges-title">Your Chef’s Badges</h2>
    <p className="small muted">New photos, varied situations and less support help your badges grow.</p>
    {progress.isPending ? <p role="status">Loading your badges…</p> : progress.isError ? <div><p role="alert">We couldn’t load your badges.</p>
      <Button variant="quiet" onClick={() => void progress.refetch()}>Retry badges</Button></div> :
      <div className="mission-badges">{progress.data?.missions.map(mission => <Card plain key={mission.missionId}>
        <div className="mission-badges__heading"><ChefBadge mission={mission} /><div><h3>{mission.name}</h3><p className="small muted">{mission.skill}</p></div></div>
      </Card>)}</div>}
  </section>;
}

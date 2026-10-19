import { useNavigate } from "react-router-dom";
import { Button, Card } from "../components/ui";
import { BasilIcon, TrophyIcon } from "../components/icons";
import { InlineLoader } from "../components/LoadingScreen";
import { useAppState } from "../state/useAppState";
import "../components/leaderboard.css";

export function ISpyModes() {
  const navigate = useNavigate();
  const { progress, progressLoading, progressError } = useAppState();
  const leaderboard = progress?.leaderboard ?? [];
  const chefs = leaderboard.slice(0, 5);
  const player = leaderboard.find(chef => chef.isYou) ?? null;
  const leader = leaderboard[0] ?? null;
  const basilToLeader = player && leader ? Math.max(0, leader.xp - player.xp) : 0;
  return <main className="ispy-modes">
    <Card lifted className="ispy-modes__card ispy-modes__play-card">
      <h1>Let’s play I-Spy!</h1>
      <div className="ispy-modes__actions">
        <Button block onClick={() => navigate("/ispy/play")}>Play with Linguini</Button>
        <Button variant="secondary" block onClick={() => navigate("/ispy/friends")}>Play with friends</Button>
      </div>
    </Card>
    <Card className="ispy-modes__card ispy-chefs">
      <div className="ispy-chefs__heading"><div><span>Weekly Basil leaderboard</span><h2>Chefs of the Day</h2></div><TrophyIcon size={30} /></div>
      {progressLoading ? <InlineLoader label="Loading this week’s chefs…" /> : progressError ? <p role="alert">{progressError}</p> : chefs.length ?
        <><section className="ispy-chefs__comparison" aria-label="Your leaderboard position">
          <div><span>Your place</span><strong>#{player?.rank ?? "—"}</strong></div>
          <div><span>Your Basil</span><strong>{player?.xp ?? progress?.xp ?? 0}</strong></div>
          <p>{!player ? "Earn Basil from learning activities to enter the rankings." : player.rank === 1 ? "You’re leading this week!" :
            `${basilToLeader} Basil behind ${leader?.name ?? "the leader"}.`}</p>
        </section>
        <ol className="ispy-chefs__list">{chefs.map(chef => <li key={`${chef.rank}-${chef.name}`} className={`ispy-chefs__entry${chef.isYou ? " is-you" : ""}`}>
          <span className="ispy-chefs__rank">{chef.rank}</span><img className="leaderboard-avatar" src={`/pasta-assets/${chef.avatar}.png`} alt="" /><strong>{chef.isYou ? `${chef.name} (you)` : chef.name}</strong>
          <span className="ispy-chefs__basil"><BasilIcon size={17} />{chef.xp} Basil</span>
        </li>)}</ol></> : <p className="muted">Earn Basil this week to join the leaderboard.</p>}
    </Card>
  </main>;
}

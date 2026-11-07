import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui";
import { ChatIcon, EyeIcon } from "../components/icons";
import { DailyChallenge } from "../components/DailyChallenge";
import { ChefOfTheDay } from "../components/ChefOfTheDay";
import { trackAction } from "../lib/analytics.ts";

export function ISpyModes() {
  const navigate = useNavigate();
  return <main className="ispy-modes">
    <header className="ispy-modes__heading">
      <h1>Games &amp; challenges</h1>
      <nav className="ispy-modes__nav" aria-label="Game sections">
        <a href="#daily-challenge" onClick={() => trackAction("play_section_nav_clicked", { section: "challenge" })}>Challenge</a>
        <a href="#ispy" onClick={() => trackAction("play_section_nav_clicked", { section: "ispy" })}>I-Spy</a>
        <a href="#leaderboard" onClick={() => trackAction("play_section_nav_clicked", { section: "leaderboard" })}>Leaderboard</a>
      </nav>
    </header>
    <div className="ispy-modes__activities">
      <section id="daily-challenge" className="ispy-modes__challenge"><DailyChallenge /></section>
      <section id="ispy" className="ispy-modes__play-card" aria-labelledby="ispy-title">
        <div className="ispy-modes__play-heading"><span aria-hidden="true"><img src="/apple-touch-icon.png" alt="" /></span><h2 id="ispy-title">I-Spy</h2></div>
        <div className="ispy-modes__actions">
          <Button block onClick={() => { trackAction("ispy_mode_selected", { mode: "ai" }); navigate("/ispy/play"); }}><EyeIcon size={19} />Play with Linguini</Button>
          <Button variant="secondary" block onClick={() => { trackAction("ispy_mode_selected", { mode: "friend" }); navigate("/ispy/friends"); }}><ChatIcon size={19} />Play with friends</Button>
        </div>
      </section>
    </div>
    <section id="leaderboard" className="card ispy-modes__leaderboard ispy-chefs"><ChefOfTheDay /></section>
  </main>;
}

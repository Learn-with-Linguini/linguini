import { useNavigate } from "react-router-dom";
import { Button, Card } from "../components/ui";
import { ChevronRightIcon } from "../components/icons";
import { DailyChallenge } from "../components/DailyChallenge";
import { trackAction } from "../lib/analytics.ts";
import { useChefStandings } from "../state/gamification";

export function ISpyModes() {
  const navigate = useNavigate();
  const standings = useChefStandings().data;
  const standing = standings?.currentRank ? `Your place: #${standings.currentRank} · ${standings.todayBasil} Basil` : standings ? "Earn Basil to join today’s board." : null;
  return <main className="ispy-modes">
    <Card lifted className="ispy-modes__card ispy-modes__play-card">
      <h1>Play I-Spy</h1>
      <div className="ispy-modes__actions">
        <Button block onClick={() => { trackAction("ispy_mode_selected", { mode: "ai" }); navigate("/ispy/play"); }}>Play with Linguini</Button>
        <Button variant="secondary" block onClick={() => { trackAction("ispy_mode_selected", { mode: "friend" }); navigate("/ispy/friends"); }}>Play with friends</Button>
      </div>
    </Card>
    <Card lifted className="ispy-modes__card ispy-modes__challenge"><DailyChallenge /></Card>
    <button type="button" className="ispy-modes__chefs" onClick={() => { trackAction("ispy_chefs_board_clicked"); navigate("/ispy/chefs"); }}>
      <span><strong>Chefs of the Day</strong>{standing ? <small>{standing}</small> : null}</span>
      <span className="ispy-modes__chefs-action">View board<ChevronRightIcon size={18} /></span>
    </button>
  </main>;
}

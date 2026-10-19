import { useNavigate } from "react-router-dom";
import { Button, Card } from "../components/ui";
import { ChefOfTheDay } from "../components/ChefOfTheDay";
import { trackAction } from "../lib/analytics.ts";

export function ISpyModes() {
  const navigate = useNavigate();
  return <main className="ispy-modes">
    <Card lifted className="ispy-modes__card ispy-modes__play-card">
      <h1>Let’s play I-Spy!</h1>
      <div className="ispy-modes__actions">
        <Button block onClick={() => { trackAction("ispy_mode_selected", { mode: "ai" }); navigate("/ispy/play"); }}>Play with Linguini</Button>
        <Button variant="secondary" block onClick={() => { trackAction("ispy_mode_selected", { mode: "friend" }); navigate("/ispy/friends"); }}>Play with friends</Button>
      </div>
    </Card>
    <Card className="ispy-modes__card ispy-chefs"><ChefOfTheDay /></Card>
  </main>;
}

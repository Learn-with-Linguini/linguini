import { ChefOfTheDay } from "../components/ChefOfTheDay";
import { Card } from "../components/ui";

/** Today's full Basil leaderboard, opened from the Play and Home summaries. */
export function ChefsBoard() {
  return <div className="ispy-chefs-page"><Card className="ispy-chefs"><ChefOfTheDay as="h1" /></Card></div>;
}

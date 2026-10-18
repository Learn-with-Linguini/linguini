import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Card } from "../components/ui";
import { ArrowRightIcon } from "../components/icons";
import { trackAction } from "../lib/analytics.ts";
import { getActiveISpyGame } from "../lib/api";
import { queryError, queryKeys } from "../lib/queryKeys";
import { sessionDestination } from "../lib/sessionRoute";
import { useAppState } from "../state/useAppState";

export function ISpyModes() {
  const navigate = useNavigate();
  const { activeProfile } = useAppState();
  const active = useQuery({
    queryKey: queryKeys.activeGame(activeProfile?.id ?? ""),
    queryFn: ({ signal }) => getActiveISpyGame(signal),
    enabled: !!activeProfile,
    staleTime: 0,
  });
  const game = active.data ?? null;
  const error = queryError(active.error);
  return <div className="stack">
    <h1>I-Spy</h1>
    <p className="muted">Spy objects in your photos and describe them in your learning language.</p>
    {error ? <p role="alert">{error}</p> : null}
    {game ? <Card lifted><div className="stack-2">
      <h2>Game in progress</h2>
      <p className="muted">Pick up your game where you left off.</p>
      <Button block onClick={() => { trackAction("ispy_game_resumed"); navigate(sessionDestination(game).path); }}>Continue game <ArrowRightIcon /></Button>
    </div></Card> : null}
    <Card lifted><div className="stack-2">
      <h2>Play with AI</h2>
      <p className="muted">Guess Linguini's clues, then describe objects for Linguini to guess.</p>
      <p className="small muted">Revisit a confirmed photo without using Sauce.</p>
      <Button block onClick={() => { trackAction("ispy_mode_selected", { mode: "ai" }); navigate("/ispy/play"); }}>Play with AI <ArrowRightIcon /></Button>
    </div></Card>
    <Card><div className="stack-2">
      <h2>Play with a friend</h2>
      <p className="muted">Add 2–4 photos in a private room, then take turns giving clues and spotting objects.</p>
      <Button variant="secondary" block onClick={() => { trackAction("ispy_mode_selected", { mode: "friend" }); navigate("/ispy/friends"); }}>Play with a friend <ArrowRightIcon /></Button>
    </div></Card>
  </div>;
}

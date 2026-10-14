import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Card } from "../components/ui";
import { ArrowRightIcon } from "../components/icons";
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
      <Button block onClick={() => navigate(sessionDestination(game).path)}>Continue game <ArrowRightIcon /></Button>
    </div></Card> : null}
    <Card lifted><div className="stack-2">
      <h2>Play with AI</h2>
      <p className="muted">Guess Linguini's clues, then describe objects for Linguini to guess.</p>
      <Button block onClick={() => navigate("/ispy/play")}>Play with AI <ArrowRightIcon /></Button>
    </div></Card>
    <Card><div className="stack-2">
      <div className="spread"><h2>Two-player</h2><span className="pill pill--new">Coming soon</span></div>
      <p className="muted">Take turns spying objects with a friend.</p>
      <Button variant="secondary" block disabled>Two-player — Coming soon</Button>
    </div></Card>
  </div>;
}

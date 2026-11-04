import { LoadingScreen } from "../components/LoadingScreen";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Card } from "../components/ui";
import { getPracticeSummary, startISpyGame } from "../lib/api";
import { practiceStages } from "../lib/practiceTasks";
import { gameStartError, queryError, queryKeys } from "../lib/queryKeys";
import { sessionDestination } from "../lib/sessionRoute";
import { useAppState } from "../state/useAppState";
import { useScene } from "../state/useScene";

export function ISpyResults() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, activeProfile, completionPending, completionError, retryCompletion } = useAppState();
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const replayKey = useRef<string | null>(null);
  const { data, error: queryErrorValue, isPending } = useQuery({
    queryKey: queryKeys.sessionSummary(scene.sessionId!),
    queryFn: () => getPracticeSummary(scene.sessionId!),
  });
  const error = queryError(queryErrorValue);
  const completed = session?.session.status === "completed" && !completionPending && !completionError && Boolean(data) && !error;
  const described = session ? practiceStages(session.tasks).reflection : [];
  const found = described.filter(task => task.status === "completed").length;
  const playAgain = async () => {
    if (!session || !activeProfile || starting) return;
    setStarting(true); setStartError(null);
    replayKey.current ??= crypto.randomUUID();
    try {
      const detail = await startISpyGame(activeProfile.id, session.mediaAsset.id, replayKey.current);
      replayKey.current = null;
      navigate(sessionDestination(detail).path);
    } catch (reason) {
      setStartError(gameStartError(reason));
    } finally { setStarting(false); }
  };
  return <div className="stack session-summary">
    <Card plain className="summary-card"><div className="summary-card__body">
    <header className="summary-hero">
      <img className="summary-hero__mascot" src="/linguini-logo-sunglasses.png" width={104} height={104} alt="Linguini celebrating in sunglasses" />
      <h1>{completed ? "Great game, keep it up!" : "Your game"}</h1>
    </header>
    {isPending ? <LoadingScreen label="Loading your results" /> : null}
    {error ? <p role="alert">{error}</p> : null}
    {completionError ? <><p role="alert">{completionError}</p><Button onClick={retryCompletion}>Retry saving your game</Button></> : null}
    {data ? <div className="summary-results summary-results--three" aria-label="Game results">
      <div className="summary-result summary-result--basil"><div className="summary-result__value">{data.ispyCorrectCount}/{data.ispyAttemptCount}</div><span>Clues solved</span></div>
      <div className="summary-result"><div className="summary-result__value">{found}/{described.length}</div><span>Objects Linguini found</span></div>
      <div className="summary-result"><div className="summary-result__value">{data.progress.skippedTaskCount}</div><span>Rounds skipped</span></div>
    </div> : null}
    
    {startError ? <p role="alert">{startError}</p> : null}
    <div className="summary-actions">
      <Button block variant="secondary" onClick={() => navigate("/ispy/play")}>Choose another photo</Button>
      <Button block disabled={starting || !session} onClick={() => void playAgain()}>{starting ? "Setting up" : "Play again"}</Button>
    </div>
    <Button variant="quiet" block onClick={() => navigate("/home")}>Back home</Button>
    </div></Card>
  </div>;
}

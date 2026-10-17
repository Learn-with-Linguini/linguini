import { LoadingScreen } from "../components/LoadingScreen";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Noodle } from "../components/ui";
import { getPracticeSummary, startISpyGame } from "../lib/api";
import { practiceStages } from "../lib/practiceTasks";
import { gameStartError, queryError, queryKeys } from "../lib/queryKeys";
import { sessionDestination } from "../lib/sessionRoute";
import { useAppState } from "../state/useAppState";
import { useScene } from "../state/useScene";

export function ISpyResults() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, activeProfile, completionError, retryCompletion } = useAppState();
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const replayKey = useRef<string | null>(null);
  const { data, error: queryErrorValue, isPending } = useQuery({
    queryKey: queryKeys.sessionSummary(scene.sessionId!),
    queryFn: () => getPracticeSummary(scene.sessionId!),
  });
  const error = queryError(queryErrorValue);
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
  return <div className="stack">
    <div className="center-text stack-2" style={{ alignItems: "center" }}>
      <img className="mascot" src="/linguini-logo.png" width={120} height={120} alt="Linguini mascot" />
      <h1>Game over!</h1>
      <Noodle className="noodle-divider summary__noodle" />
      <p className="muted">You played I-Spy with {scene.title.toLowerCase()}.</p>
    </div>
    {isPending ? <LoadingScreen label="Loading your results…" /> : null}
    {error ? <p role="alert">{error}</p> : null}
    {completionError ? <><p role="alert">{completionError}</p><Button onClick={retryCompletion}>Retry saving your game</Button></> : null}
    {data ? <div className="stat-grid">
      <div className="stat"><div className="stat__value">{data.ispyCorrectCount}/{data.ispyAttemptCount}</div><span className="stat__label">Correct answers</span></div>
      <div className="stat"><div className="stat__value">{found}/{described.length}</div><span className="stat__label">Objects Linguini found</span></div>
      <div className="stat"><div className="stat__value">{data.progress.skippedTaskCount}</div><span className="stat__label">Rounds skipped</span></div>
    </div> : null}
    <p className="small muted">Games are just for fun: they don't earn XP or change your word progress.</p>
    {startError ? <p role="alert">{startError}</p> : null}
    <div className="stack-2">
      <Button block disabled={starting || !session} onClick={() => void playAgain()}>{starting ? "Setting up..." : "Play again"}</Button>
      <Button variant="secondary" block onClick={() => navigate("/ispy/play")}>Choose another photo</Button>
      <Button variant="quiet" block onClick={() => navigate("/home")}>Back home</Button>
    </div>
  </div>;
}

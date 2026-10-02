import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Noodle, StatusPill, XpPill } from "../components/ui";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { useVocabularyQuery } from "../state/queries";
import { getPracticeSummary } from "../lib/api";
import { sessionDestination } from "../lib/sessionRoute";
import { queryError, queryKeys } from "../lib/queryKeys";

export function SessionSummary() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, completionError, retryCompletion } = useAppState();
  const { vocabulary } = useVocabularyQuery(); 
  const [startError] = useState<string | null>(null);
  // Stats render from the in-flight numbers straight away; the completion
  // mutation invalidates this key so final XP replaces them once it lands.
  const { data, error: queryErrorValue, isPending: loading } = useQuery({
    queryKey: queryKeys.sessionSummary(scene.sessionId!),
    queryFn: () => getPracticeSummary(scene.sessionId!),
  });
  const error = queryError(queryErrorValue);
  const completed = session?.session.status === "completed";
  const revisit = scene.items.filter(item => data?.learnedVocabularyIds.includes(
    session?.sceneObjects.find(object => object.id === item.id)?.vocabularyItemId ?? ""
  )).slice(0, 3);
  
  return <div className="stack">
    {session?.session.status === "inProgress" ? <Button onClick={() => navigate(sessionDestination(session).path)}>Continue unfinished practice</Button> : null}
    <div className="center-text stack-2" style={{ alignItems: "center" }}>
      <img className="mascot" src="/linguini-logo.png" width={120} height={120} alt="Linguini mascot" /><h1>{completed ? "Good job!" : "Your session"}</h1><Noodle className="noodle-divider summary__noodle" />
      <p className="muted">You practised {scene.title.toLowerCase()}.</p>
    </div>
    {loading ? <p role="status">Loading your results...</p> : null}
    {error || startError ? <p role="alert">{error || startError}</p> : null}
    {completionError ? <><p role="alert">{completionError}</p><Button onClick={retryCompletion}>Retry saving your session</Button></> : null}
    {data ? <>
      <div className="stat-grid">
        <div className="stat"><div className="stat__value">{data.xpEarned}</div><span className="stat__label">XP earned</span></div>
        <div className="stat"><div className="stat__value">{data.ispyCorrectCount}/{data.ispyAttemptCount}</div><span className="stat__label">I-Spy correct</span></div>
        <div className="stat"><div className="stat__value">{data.learnedVocabularyIds.length}</div><span className="stat__label">Words learned</span></div>
      </div>
      <Card><div className="stack-2">
        <div className="spread"><h2>Words to revisit</h2><XpPill xp={data.xpEarned} /></div>
        {revisit.map(item => {
          const vocabularyId = session?.sceneObjects.find(object => object.id === item.id)?.vocabularyItemId;
          return <div key={item.id} className="spread"><div><strong>{item.word}</strong><p className="small muted">{item.translation}</p></div><StatusPill status={vocabulary.find(word => word.id === vocabularyId)?.status ?? "learning"} /></div>;
        })}
        {revisit.length === 0 ? <p className="small muted">No vocabulary practised in this session.</p> : null}
      </div></Card>
    </> : null}
    <div className="stack-2">
      <Button block onClick={() => navigate("/journal/new")}>Write today&apos;s journal entry</Button>
      <Button variant="secondary" block onClick={() => navigate("/vocabulary")}>Review difficult words</Button>
      <Button variant="quiet" block onClick={() => navigate("/home")}>Back home</Button>
    </div>
  </div>;
}

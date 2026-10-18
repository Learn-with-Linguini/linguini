import { LoadingScreen } from "../components/LoadingScreen";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Noodle, StatusPill, XpPill } from "../components/ui";
import { HelpImproveModal } from "../components/HelpImproveModal";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { useVocabularyQuery } from "../state/queries";
import { getPracticeSummary, startISpyGame } from "../lib/api";
import { trackAction } from "../lib/analytics.ts";
import { isMissionSession } from "../lib/practiceTasks";
import { sessionDestination } from "../lib/sessionRoute";
import { gameStartError, queryError, queryKeys } from "../lib/queryKeys";

export function SessionSummary() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, activeProfile, completionError, retryCompletion } = useAppState();
  const { vocabulary } = useVocabularyQuery(); 
  const [startingISpy, setStartingISpy] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [surveyOpen, setSurveyOpen] = useState(false);
  const startKey = useRef<string | null>(null);
  // Stats render from the in-flight numbers straight away; the completion
  // mutation invalidates this key so final XP replaces them once it lands.
  const { data, error: queryErrorValue, isPending: loading } = useQuery({
    queryKey: queryKeys.sessionSummary(scene.sessionId!),
    queryFn: () => getPracticeSummary(scene.sessionId!),
  });
  const error = queryError(queryErrorValue);
  const completed = session?.session.status === "completed";
  const completedLessons = data?.completedLessonsCount ?? 0;
  // Prompt after account's first lesson (1) and every 5 lessons afterwards (6, 11, 16...)
  const isMilestone =
    completedLessons === 1 ||
    (completedLessons > 1 && (completedLessons - 1) % 5 === 0);

  useEffect(() => {
    if (!completed || !data || !isMilestone) return;
    const promptedKey = `linguini_survey_prompted_lesson_${completedLessons}`;
    if (localStorage.getItem(promptedKey)) return;
    const timer = setTimeout(() => {
      setSurveyOpen(true);
      localStorage.setItem(promptedKey, "true");
    }, 900);
    return () => clearTimeout(timer);
  }, [completed, data, isMilestone, completedLessons]);

  useEffect(() => {
    if (data) {
      trackAction("session_summary_viewed", {
        xpEarned: data.xpEarned,
        wordsLearnedCount: data.learnedVocabularyIds.length,
        ispyCorrectCount: data.ispyCorrectCount,
        completedLessonsCount: data.completedLessonsCount,
      });
    }
  }, [data]);

  const revisit = scene.items.filter(item => data?.learnedVocabularyIds.includes(
    session?.sceneObjects.find(object => object.id === item.id)?.vocabularyItemId ?? ""
  )).slice(0, 3);
  const missionSession = Boolean(session && isMissionSession(session.tasks));
  const playISpy = async () => {
    if (!session || !activeProfile || startingISpy) return;
    setStartingISpy(true);
    setStartError(null);
    trackAction("summary_play_ispy_clicked");
    startKey.current ??= crypto.randomUUID();
    try {
      const detail = await startISpyGame(activeProfile.id, session.mediaAsset.id, startKey.current);
      startKey.current = null;
      navigate(sessionDestination(detail).path);
    } catch (reason) {
      setStartError(gameStartError(reason));
    } finally {
      setStartingISpy(false);
    }
  };
  
  return <div className="stack">
    {session?.session.status === "inProgress" ? <Button onClick={() => navigate(sessionDestination(session).path)}>Continue unfinished practice</Button> : null}
    <div className="center-text stack-2" style={{ alignItems: "center" }}>
      <img className="mascot" src="/linguini-logo.png" width={120} height={120} alt="Linguini mascot" /><h1>{completed ? "Good job!" : "Your session"}</h1><Noodle className="noodle-divider summary__noodle" />
      <p className="muted">You practised {scene.title.toLowerCase()}.</p>
    </div>
    {loading ? <LoadingScreen label="Loading your results…" /> : null}
    {error || startError ? <p role="alert">{error || startError}</p> : null}
    {completionError ? <><p role="alert">{completionError}</p><Button onClick={retryCompletion}>Retry saving your session</Button></> : null}
    {data ? <>
      <div className="stat-grid">
        <div className="stat"><div className="stat__value">{data.xpEarned}</div><span className="stat__label">XP earned</span></div>
        {data.ispyAttemptCount ? <div className="stat"><div className="stat__value">{data.ispyCorrectCount}/{data.ispyAttemptCount}</div><span className="stat__label">I-Spy correct</span></div> : null}
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
      {missionSession ? <Button block disabled={startingISpy || !completed} onClick={() => void playISpy()}>
        {startingISpy ? "Setting up I-Spy..." : "Play I-Spy with this scene"}
      </Button> : <>
        <Button block onClick={() => { trackAction("summary_journal_cta_clicked"); navigate("/journal/new"); }}>Write today&apos;s journal entry</Button>
        <Button variant="secondary" block onClick={() => { trackAction("summary_review_words_cta_clicked"); navigate("/vocabulary"); }}>Review difficult words</Button>
      </>}
      <Button variant="quiet" block onClick={() => navigate("/home")}>Back home</Button>
    </div>

    <HelpImproveModal
      open={surveyOpen}
      onClose={() => setSurveyOpen(false)}
      triggerSource="lesson_completed"
      lessonCount={completedLessons}
    />
  </div>;
}

import { LoadingScreen } from "../components/LoadingScreen";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, StatusPill } from "../components/ui";
import { HelpImproveModal } from "../components/HelpImproveModal";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { useVocabularyQuery } from "../state/queries";
import { getPracticeSummary, startISpyGame } from "../lib/api";
import { isMissionSession } from "../lib/practiceTasks";
import { sessionDestination } from "../lib/sessionRoute";
import { BasilIcon } from "../components/icons";
import { gameStartError, queryError, queryKeys } from "../lib/queryKeys";
import { learningFeedback } from "../lib/learningFeedback";
import { trackAction } from "../lib/analytics.ts";
import { useMissionProgress } from "../state/gamification";
import { batchAccuracy } from "../lib/gamification";
import { BadgeEarnedModal, SummaryBadges } from "../components/SummaryBadges";

export function SessionSummary() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, activeProfile, completionPending, completionError, retryCompletion } = useAppState();
  const { vocabulary } = useVocabularyQuery(); 
  const [startingISpy, setStartingISpy] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [surveyOpen, setSurveyOpen] = useState(false);
  const startKey = useRef<string | null>(null);
  // Stats render from the in-flight numbers straight away; the completion
  // mutation invalidates this key so the final Basil total replaces it once it lands.
  const { data, error: queryErrorValue, isPending: loading } = useQuery({
    queryKey: queryKeys.sessionSummary(scene.sessionId!),
    queryFn: () => getPracticeSummary(scene.sessionId!),
  });
  const error = queryError(queryErrorValue);
  const completed = session?.session.status === "completed" && !completionPending && !completionError && Boolean(data) && !error;
  const completedLessons = data?.completedLessonsCount ?? 0;
  const missionProgress = useMissionProgress(scene.sessionId!, completed);
  const batches = missionProgress.data ?? [];
  const earnedBadges = batches.filter(batch => batch.badgeEarned);
  const [badgePopupOpen, setBadgePopupOpen] = useState(false);
  // The survey waits until any badge celebration has been seen.
  const badgesSettled = !completed || (!missionProgress.isPending && !badgePopupOpen);
  // Prompt after account's first lesson (1) and every 5 lessons afterwards (6, 11, 16...)
  const isMilestone =
    completedLessons === 1 ||
    (completedLessons > 1 && (completedLessons - 1) % 5 === 0);

  useEffect(() => {
    if (!completed || !data) return;
    trackAction("session_summary_viewed", {
      sessionId: scene.sessionId,
      basilEarned: data.basilEarned,
      wordsLearnedCount: data.learnedVocabularyIds.length,
      completedLessonsCount: data.completedLessonsCount,
    });
  }, [completed, data, scene.sessionId]);

  useEffect(() => {
    if (!completed || !missionProgress.data) return;
    const popupKey = `linguini_badges_seen_${scene.sessionId}`;
    let shown = false;
    try { shown = Boolean(sessionStorage.getItem(popupKey)); } catch { /* storage blocked: show once per visit */ }
    if (shown) return;
    try { sessionStorage.setItem(popupKey, "true"); } catch { /* the popup still shows once */ }
    for (const batch of missionProgress.data.filter(item => item.status === "review")) {
      trackAction("summary_badge_missed", { missionId: batch.missionId, accuracy: batchAccuracy(batch) });
    }
    const earned = missionProgress.data.filter(batch => batch.badgeEarned);
    if (!earned.length) return;
    for (const batch of earned) trackAction("badge_earned_popup_shown", { missionId: batch.missionId, level: batch.badgeEarned });
    setBadgePopupOpen(true);
  }, [completed, missionProgress.data, scene.sessionId]);

  useEffect(() => {
    if (!completed || !data || !isMilestone || !badgesSettled) return;
    const promptedKey = `linguini_survey_prompted_lesson_${completedLessons}`;
    if (localStorage.getItem(promptedKey)) return;
    const timer = setTimeout(() => {
      setSurveyOpen(true);
      localStorage.setItem(promptedKey, "true");
    }, 900);
    return () => clearTimeout(timer);
  }, [completed, data, isMilestone, completedLessons, badgesSettled]);

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
  
  const closeBadgePopup = useCallback(() => {
    trackAction("badge_earned_popup_closed");
    setBadgePopupOpen(false);
  }, []);

  const wordsLearned = data?.learnedVocabularyIds.length ?? 0;
  const resultMessage = data
    ? wordsLearned > 0
      ? `You served up ${wordsLearned} new ${wordsLearned === 1 ? "word" : "words"} and collected ${data.basilEarned} basil. That’s a lesson well cooked.`
      : `You kept your language skills simmering and collected ${data.basilEarned} basil. Nicely done, Chef.`
    : `You practised ${scene.title.toLowerCase()}.`;

  return <div className="stack session-summary">
    {session?.session.status === "inProgress" ? <Button onClick={() => navigate(sessionDestination(session).path)}>Continue unfinished practice</Button> : null}
    <header className="summary-hero">
      <div className="summary-hero__mascot"><img className="mascot" src="/linguini-logo-sunglasses.png" width={132} height={132} alt="Linguini celebrating in sunglasses" /></div>
      <h1>{completed ? learningFeedback("completed", scene.sessionId!) : "Your session"}</h1>
      <p>{resultMessage}</p>
    </header>
    {loading ? <LoadingScreen label="Loading your results" /> : null}
    {error || startError ? <p role="alert">{error || startError}</p> : null}
    {completionError ? <><p role="alert">{completionError}</p><Button onClick={retryCompletion}>Retry saving your session</Button></> : null}
    {data ? <>
      <div className="summary-results" aria-label="Session results">
        <div className="summary-result summary-result--basil"><div className="summary-result__value"><BasilIcon size={28} />{data.basilEarned}</div><span>Basil collected</span></div>
        <div className="summary-result summary-result--words"><div className="summary-result__value">{wordsLearned}</div><span>New {wordsLearned === 1 ? "word" : "words"} learned</span></div>
      </div>
      <Card><div className="stack-2">
        <h2>Fresh from this lesson</h2>
        {revisit.map(item => {
          const vocabularyId = session?.sceneObjects.find(object => object.id === item.id)?.vocabularyItemId;
          return <div key={item.id} className="spread"><div><strong>{item.word}</strong><p className="small muted">{item.translation}</p></div><StatusPill status={vocabulary.find(word => word.id === vocabularyId)?.status ?? "learning"} /></div>;
        })}
        {revisit.length === 0 ? <p className="small muted">No vocabulary practised in this session.</p> : null}
      </div></Card>
      <SummaryBadges batches={batches} />
    </> : null}
    <div className="stack-2">
      <Button block variant="secondary" onClick={() => { trackAction("summary_back_home_clicked"); navigate("/home"); }}>Back home</Button>
      {missionSession ? <Button block disabled={startingISpy || !completed} onClick={() => void playISpy()}>
        {startingISpy ? "Setting up I-Spy" : "Play I-Spy with this scene"}
      </Button> : <>
      </>}
      
    </div>

    {badgePopupOpen ? <BadgeEarnedModal batches={earnedBadges} onClose={closeBadgePopup} /> : null}
    <HelpImproveModal
      open={surveyOpen}
      onClose={() => setSurveyOpen(false)}
      triggerSource="lesson_completed"
      lessonCount={completedLessons}
    />
  </div>;
}

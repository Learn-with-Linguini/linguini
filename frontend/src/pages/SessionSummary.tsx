import { LoadingScreen } from "../components/LoadingScreen";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Card } from "../components/ui";
import { HelpImproveModal } from "../components/HelpImproveModal";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { getPracticeSummary, startISpyGame } from "../lib/api";
import { isMissionSession } from "../lib/practiceTasks";
import { sessionDestination } from "../lib/sessionRoute";
import { BasilIcon } from "../components/icons";
import { gameStartError, queryError, queryKeys } from "../lib/queryKeys";
import { trackAction } from "../lib/analytics.ts";
import { useMissionProgress } from "../state/gamification";
import { batchAccuracy, lessonFinishScore } from "../lib/gamification";
import { celebrateFinish } from "../lib/answerCelebration";
import { BadgeEarnedModal, SummaryBadges } from "../components/SummaryBadges";

export function SessionSummary() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, activeProfile, completionPending, completionError, retryCompletion } = useAppState();
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
  const celebrated = useRef(false);
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
    // Wait for the graded mission results so a perfect lesson gets its fuller shower.
    if (!completed || !data || missionProgress.isPending || celebrated.current) return;
    celebrated.current = true;
    const score = lessonFinishScore(missionProgress.data ?? [], data.progress.skippedTaskCount);
    celebrateFinish(score);
    trackAction("finish_celebration_shown", { screen: "lesson", score });
  }, [completed, data, missionProgress.isPending, missionProgress.data]);

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
  )).slice(0, 6);
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
  return <div className="stack session-summary">
    {session?.session.status === "inProgress" ? <Button onClick={() => navigate(sessionDestination(session).path)}>Continue unfinished practice</Button> : null}
    <Card plain className="summary-card"><div className="summary-card__body">
    <header className="summary-hero">
      <img className="summary-hero__mascot" src="/linguini-logo-sunglasses.png" width={104} height={104} alt="Linguini celebrating in sunglasses" />
      <h1>{completed ? "Great work, keep it up!" : "Your session"}</h1>
    </header>
    {loading ? <LoadingScreen label="Loading your results" /> : null}
    {error || startError ? <p role="alert">{error || startError}</p> : null}
    {completionError ? <><p role="alert">{completionError}</p><Button onClick={retryCompletion}>Retry saving your session</Button></> : null}
    {data ? <>
      <div className="summary-results" aria-label="Session results">
        <div className="summary-result summary-result--basil"><div className="summary-result__value"><BasilIcon size={24} />{data.basilEarned}</div><span>Basil collected</span></div>
        <div className="summary-result summary-result--words"><div className="summary-result__value">{wordsLearned}</div><span>New {wordsLearned === 1 ? "word" : "words"} learned</span></div>
      </div>
      {revisit.length ? <section className="summary-fresh" aria-labelledby="summary-fresh-title">
        <h2 id="summary-fresh-title" className="summary-fresh__title">Fresh from this lesson</h2>
        <ul className="known-words">{revisit.map(item => <li key={item.id} className="known-words__pill" lang={scene.languageCode}>{item.word}</li>)}</ul>
      </section> : null}
      <SummaryBadges batches={batches} />
    </> : null}
    <div className="summary-actions">
      <Button block variant="secondary" onClick={() => { trackAction("summary_back_home_clicked"); navigate("/home"); }}>Back home</Button>
      {missionSession ? <Button block disabled={startingISpy || !completed} onClick={() => void playISpy()}>
        {startingISpy ? "Setting up I-Spy" : "Play I-Spy with this scene"}
      </Button> : null}
    </div>
    </div></Card>

    {badgePopupOpen ? <BadgeEarnedModal batches={earnedBadges} onClose={closeBadgePopup} /> : null}
    <HelpImproveModal
      open={surveyOpen}
      onClose={() => setSurveyOpen(false)}
      triggerSource="lesson_completed"
      lessonCount={completedLessons}
    />
  </div>;
}

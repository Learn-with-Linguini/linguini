import { InlineLoader } from "../components/LoadingScreen";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useNavigate } from "react-router-dom";
import { sessionDestination, sessionPaths } from "../lib/sessionRoute";
import { BasilReward, Button, Feedback, IconButton, ProgressTrail, XpPill } from "../components/ui";
import { ArrowRightIcon, CloseIcon, EyeIcon, EyeOffIcon, SpeakerIcon } from "../components/icons";
import { ScenePhoto } from "../components/ScenePhoto";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { practiceStages, taskDone, taskXp } from "../lib/practiceTasks";
import { speak } from "../lib/speech";
import { trackAction } from "../lib/analytics.ts";
import { getLatestAttempt } from "../lib/api";
import type { SessionTask, TaskActionResult } from "../lib/api";
import { queryKeys } from "../lib/queryKeys";
import { ReportIssueLink } from "../components/ReportIssueLink";
import { playAnswerSound } from "../lib/answerSound";
import { basilEarnedText } from "../lib/gamification";
import { learningFeedback } from "../lib/learningFeedback";
import { ISpyLevelHelp } from "../components/ISpyLevelHelp";

const clueOpening = (languageCode: string) => languageCode === "es"
  ? "Veo, veo, algo que"
  : languageCode === "fr"
    ? "Je vois, je vois, quelque chose qui"
    : languageCode === "de"
      ? "Ich sehe etwas, das"
      : languageCode === "ko"
        ? "나는 무언가를 보고 있어요:"
        : "I spy with my little eye, something that";

export function ISpyPhase1() {
  const navigate = useNavigate();
  const { session, practiceStalled, practiceError, retryProcessing, completeSession } = useAppState();
  const [index, setIndex] = useState(() => {
    const clues = practiceStages(session?.tasks ?? []).clues;
    const next = clues.findIndex(task => !taskDone(task));
    return next < 0 ? Math.max(0, clues.length - 1) : next;
  });
  if (!session) return null;
  const { learning, clues, reflection } = practiceStages(session.tasks);
  const paths = sessionPaths(session);
  const game = session.session.mode === "ispy";
  const finishWithoutDescription = () => {
    if (!completeSession()) return;
    trackAction("describe_round_skipped", { mode: session.session.mode });
    navigate(paths.done);
  };
  if (session.session.status === "completed") return <Navigate to={paths.done} replace />;
  if (game && ["abandoned", "failed"].includes(session.session.status)) {
    const exit = sessionDestination(session);
    return <Navigate to={exit.path} replace state={exit.notice ? { practiceNotice: exit.notice } : undefined} />;
  }
  if (!learning.every(taskDone) || ["abandoned", "failed"].includes(session.session.status)) return <Navigate to={paths.exit} replace />;
  if (game && !clues.length) return <div className="stack">
    <h2 className="text-center">I-Spy · Linguini's clues</h2>
    {practiceStalled
      ? <><InlineLoader label="Linguini is still choosing objects to spy…" /><Button block onClick={() => void retryProcessing(session.session.id)}>Check again</Button></>
      : <InlineLoader label="Linguini is choosing objects to spy…" />}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
  </div>;
  const task = clues[index];
  if (!task) return <Navigate to={paths.describe} replace />;
  return <ClueRound key={task.id} task={task} index={index} total={clues.length} describePath={paths.describe}
    skipDescription={!reflection.length} finishLabel={game ? "See results" : "Finish session"}
    onExit={() => { trackAction("ispy_exit_clicked", { phase: "clues" }); navigate("/home"); }}
    onFinish={finishWithoutDescription} onNext={() => setIndex(value => value + 1)} />;
}

function ClueRound({ task, index, total, describePath, skipDescription, finishLabel, onExit, onFinish, onNext }: {
  task: SessionTask; index: number; total: number; describePath: string;
  skipDescription: boolean; finishLabel: string; onExit: () => void; onFinish: () => void; onNext: () => void;
}) {
  const navigate = useNavigate();
  const scene = useScene();
  const { actOnTask, practiceSaving, practiceError } = useAppState();
  const [picked, setPicked] = useState<string | null>(null);
  const [result, setResult] = useState<TaskActionResult | null>(null);
  const round = task.publicContent.kind === "ispyRound" ? task.publicContent : null;
  // A0 reads the translation straight away; A2 hears the clue before reading it.
  const [showTranslation, setShowTranslation] = useState(Boolean(round?.translationShown));
  const [heard, setHeard] = useState(!round?.listenFirst || taskDone(task));
  const [checking, setChecking] = useState(false);
  const request = useRef<{ answer: string; key: string } | null>(null);
  const submitting = useRef(false);
  const restored = useQuery({
    queryKey: queryKeys.latestAttempt(task.id),
    queryFn: ({ signal }) => getLatestAttempt(task.id, signal),
    enabled: task.status === "completed" && !result?.attempt,
  }).data?.attempt;
  const autoPlay = round?.learnerLevel === "A0" && !taskDone(task);
  useEffect(() => {
    if (autoPlay && round) speak(`${clueOpening(scene.languageCode)} ${round.clue}`, scene.languageCode);
    // Played once when the round opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const content = task.publicContent;
  if (content.kind !== "ispyRound") return null;
  const opening = clueOpening(scene.languageCode);
  const hearClue = () => {
    speak(`${opening} ${content.clue}`, scene.languageCode);
    if (!heard) trackAction("ispy_clue_listened_first", { taskId: task.id });
    setHeard(true);
  };
  const answered = taskDone(task);
  const choose = async (optionId: string) => {
    if (answered || practiceSaving || submitting.current) return;
    submitting.current = true;
    setChecking(true);
    if (request.current?.answer !== optionId) request.current = { answer: optionId, key: crypto.randomUUID() };
    setPicked(optionId);
    setResult(null);
    try {
      const saved = await actOnTask(task.id, "attempts", { inputMode: "multipleChoice", optionId }, request.current.key);
      setResult(saved);
      if (saved?.attempt?.isCorrect != null) playAnswerSound(saved.attempt.isCorrect);
      if (saved) {
        request.current = null;
        trackAction("ispy_clue_submitted", { optionId, isCorrect: saved.attempt?.isCorrect, source: "photo_marker" });
      }
    } finally {
      submitting.current = false;
      setChecking(false);
    }
  };
  const isCorrect = result?.attempt?.isCorrect ?? restored?.isCorrect ?? null;
  const acceptedOption = result?.attempt?.responsePayload?.optionId;
  const acceptedPick = typeof acceptedOption === "string" ? acceptedOption : result?.attempt ? picked : null;
  // A later tap may have been rejected after an earlier response was lost.
  // Only the accepted answer can be paired with a stored grade.
  const shownPick = acceptedPick ?? restored?.optionId ?? (answered ? null : picked);
  const feedback = result?.attempt?.feedback?.message ?? restored?.feedback;
  const selected = content.options.find(option => option.optionId === shownPick);
  const optionItems = scene.items.filter(item => content.options.some(option => option.sceneObjectId === item.id));
  const reward = !answered ? taskXp(task) : null;
  const earnedText = basilEarnedText(result?.basilEarned);
  return <div className="stack">
    <div className="learning-title-row">
      <h1>I-Spy · Linguini's clues</h1>
      <div className="learning-title-actions">
        {reward ? <XpPill {...reward} /> : null}
        <Button variant="quiet" className="learning-exit" onClick={onExit}><CloseIcon size={18} /> Exit</Button>
      </div>
    </div>
    <ProgressTrail value={index + (answered ? 1 : 0)} total={total} label={`${index + 1} / ${total}`} />
    {!answered ? <p className="muted">Tap the matching numbered marker in the photo.</p> : null}
    <ScenePhoto scene={scene} items={optionItems} hideWords
      activeItemId={isCorrect ? selected?.sceneObjectId : null}
      guessItemId={selected?.sceneObjectId}
      onMarkerClick={!answered && !practiceSaving && !checking ? item => {
        const option = content.options.find(candidate => candidate.sceneObjectId === item.id);
        if (option) void choose(option.optionId);
      } : undefined} />
    <div className="card card--lifted stack-2 ispy-clue-card">
      <div className="spread"><span className="label muted">Linguini says</span><IconButton label="Hear the clue" onClick={hearClue}><SpeakerIcon /></IconButton></div>
      {heard ? <>
      <span className="prompt-translation prompt-translation--with-source">
        <span className="prompt-translation__source"><h3>{opening} {content.clue}</h3>{content.clueTranslation ? <IconButton className="prompt-translation__toggle" label={showTranslation ? "Hide translation" : "Show translation"} onClick={() => setShowTranslation(value => !value)}>{showTranslation ? <EyeIcon size={20} /> : <EyeOffIcon size={20} />}</IconButton> : null}</span>
        {content.clueTranslation && showTranslation ? <span className="small muted">{content.clueTranslation}</span> : null}
      </span>
      </> : <div className="stack-2" data-testid="listen-first">
        <p className="muted">Listen to Linguini's clue first, then find the object.</p>
        <div className="spread"><Button variant="secondary" onClick={hearClue}><SpeakerIcon /> Play the clue</Button>
          <Button variant="quiet" onClick={() => { trackAction("ispy_clue_text_revealed", { taskId: task.id }); setHeard(true); }}>Show the clue</Button></div>
      </div>}
    </div>
    <ISpyLevelHelp support={content} languageCode={scene.languageCode} />
    {checking ? <InlineLoader compact label="Checking your answer…" /> : null}
    {answered || result ? <>
      <Feedback tone={isCorrect === false ? "warn" : "good"}><div className="stack-2" role="status">
        {task.status === "skipped" ? <strong>Skipped — no Basil earned.</strong> : <>
          {isCorrect !== null ? <strong>{learningFeedback(isCorrect ? "correct" : "incorrect", task.id)}</strong> : null}
          <span>{feedback ?? "Answer saved."}</span>
        </>}
        {content.encouragement ? <span className="small muted">{content.encouragement}</span> : null}
      </div></Feedback>
      <BasilReward text={earnedText} />
    </> : null}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    <Button block disabled={!answered || practiceSaving} onClick={() => index === total - 1
      ? skipDescription ? onFinish() : navigate(describePath)
      : onNext()}>{index === total - 1 ? skipDescription ? finishLabel : "Your turn" : "Next clue"} <ArrowRightIcon /></Button>
    {(answered || result) && task.status !== "skipped" ? <div className="learning-question-report"><ReportIssueLink reportType="I-Spy answer" fields={[
      ["Task ID", task.id],
      ["Clue", `${opening} ${content.clue}`],
      ["Clue translation", content.clueTranslation],
      ["Your answer", selected?.label],
      ["Photo marker", optionItems.find(item => item.id === selected?.sceneObjectId)?.marker?.toString()],
      ["Displayed feedback", feedback],
      ["Language", scene.languageCode],
    ]} /></div> : null}
    {!answered ? <Button variant="quiet" block disabled={practiceSaving} onClick={() => void actOnTask(task.id, "skip")}>Skip task</Button> : null}
  </div>;
}

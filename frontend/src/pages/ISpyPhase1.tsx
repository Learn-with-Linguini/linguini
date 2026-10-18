import { InlineLoader } from "../components/LoadingScreen";
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useNavigate } from "react-router-dom";
import { sessionDestination, sessionPaths } from "../lib/sessionRoute";
import { Button, Feedback, IconButton, ProgressTrail, XpPill } from "../components/ui";
import { ArrowRightIcon, CheckIcon, SpeakerIcon } from "../components/icons";
import { ScenePhoto } from "../components/ScenePhoto";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { choiceOrder, practiceStages, taskDone, taskXp, xpEarnedText } from "../lib/practiceTasks";
import { speak } from "../lib/speech";
import { trackAction } from "../lib/analytics.ts";
import { getLatestAttempt } from "../lib/api";
import type { SessionTask, TaskActionResult } from "../lib/api";
import { queryKeys } from "../lib/queryKeys";
import { ReportIssueLink } from "../components/ReportIssueLink";
import { playAnswerSound } from "../lib/answerSound";

export function ISpyPhase1() {
  const { session, practiceStalled, practiceError, retryProcessing } = useAppState();
  const [index, setIndex] = useState(() => {
    const clues = practiceStages(session?.tasks ?? []).clues;
    const next = clues.findIndex(task => !taskDone(task));
    return next < 0 ? Math.max(0, clues.length - 1) : next;
  });
  if (!session) return null;
  const { learning, clues } = practiceStages(session.tasks);
  const paths = sessionPaths(session);
  const game = session.session.mode === "ispy";
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
  return <ClueRound key={task.id} task={task} index={index} total={clues.length} describePath={paths.describe} onNext={() => setIndex(value => value + 1)} />;
}

function ClueRound({ task, index, total, describePath, onNext }: { task: SessionTask; index: number; total: number; describePath: string; onNext: () => void }) {
  const navigate = useNavigate();
  const scene = useScene();
  const { actOnTask, practiceSaving, practiceError } = useAppState();
  const [picked, setPicked] = useState<string | null>(null);
  const [result, setResult] = useState<TaskActionResult | null>(null);
  const [showTranslation, setShowTranslation] = useState(false);
  const [checking, setChecking] = useState(false);
  const request = useRef<{ answer: string; key: string } | null>(null);
  const submitting = useRef(false);
  const restored = useQuery({
    queryKey: queryKeys.latestAttempt(task.id),
    queryFn: ({ signal }) => getLatestAttempt(task.id, signal),
    enabled: task.status === "completed" && !result?.attempt,
  }).data?.attempt;
  const content = task.publicContent;
  if (content.kind !== "ispyRound") return null;
  const opening = scene.languageCode === "es"
    ? "Veo, veo, algo que"
    : scene.languageCode === "fr"
      ? "Je vois, je vois, quelque chose qui"
      : scene.languageCode === "de"
        ? "Ich sehe etwas, das"
        : scene.languageCode === "ko"
          ? "나는 무언가를 보고 있어요:"
          : "I spy with my little eye, something that";
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
        trackAction("ispy_clue_submitted", { optionId, isCorrect: saved.attempt?.isCorrect });
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
  const reward = !answered ? taskXp(task) : null;
  const earnedText = xpEarnedText(result?.xpEarned);
  return <div className="stack">
    <div className="spread"><h2 className="text-center">I-Spy · Linguini's clues</h2>{reward ? <XpPill {...reward} /> : null}</div>
    <p>Use the clues to find the word</p>
    <ProgressTrail value={index + (answered ? 1 : 0)} total={total} label={`${index + 1} / ${total}`} />
    <ScenePhoto scene={scene} activeItemId={isCorrect ? selected?.sceneObjectId : null} />
    <div className="card card--lifted stack-2">
      <div className="spread"><span className="label muted">Linguini says</span><IconButton label="Hear the clue" onClick={() => speak(`${opening} ${content.clue}`, scene.languageCode)}><SpeakerIcon /></IconButton></div>
      <h3>{opening} {content.clue}</h3>
      {content.clueTranslation ? showTranslation ? <p className="small muted">{content.clueTranslation}</p> : <button type="button" className="text-link text-link--muted" onClick={() => setShowTranslation(true)}>See translation</button> : null}
    </div>
    <div className="choice-grid">{choiceOrder(content.options, task.id, option => option.optionId).map(option => {
      const state = shownPick !== option.optionId ? "" : isCorrect != null ? (isCorrect ? " choice--correct" : " choice--incorrect") : " choice--selected";
      return <button key={option.optionId} type="button" className={`choice${state}`} aria-pressed={shownPick === option.optionId} disabled={answered || practiceSaving || checking} onClick={() => void choose(option.optionId)}>
        {isCorrect && shownPick === option.optionId ? <CheckIcon size={16} /> : null}{option.label}
      </button>;
    })}</div>
    {checking ? <InlineLoader compact label="Checking your answer…" /> : null}
    {answered || result ? <>
      <Feedback tone={isCorrect === false ? "warn" : "good"}><div className="stack-2" role="status"><strong>{task.status === "skipped" ? "Skipped — no XP earned." : feedback ?? "Answer saved."}</strong>{content.encouragement ? <span className="small muted">{content.encouragement}</span> : null}{earnedText ? <strong>{earnedText}</strong> : null}</div></Feedback>
      {task.status !== "skipped" ? <ReportIssueLink reportType="I-Spy answer" fields={[
        ["Task ID", task.id],
        ["Clue", `${opening} ${content.clue}`],
        ["Clue translation", content.clueTranslation],
        ["Your answer", selected?.label],
        ["Displayed feedback", feedback],
        ["Language", scene.languageCode],
      ]} /> : null}
    </> : null}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    <Button block disabled={!answered || practiceSaving} onClick={() => index === total - 1 ? navigate(describePath) : onNext()}>{index === total - 1 ? "Your turn" : "Next clue"} <ArrowRightIcon /></Button>
    {!answered ? <Button variant="quiet" block disabled={practiceSaving} onClick={() => void actOnTask(task.id, "skip")}>Skip task</Button> : null}
  </div>;
}

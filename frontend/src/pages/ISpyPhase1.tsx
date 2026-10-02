import { useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Button, Feedback, IconButton, ProgressTrail } from "../components/ui";
import { ArrowRightIcon, CheckIcon, SpeakerIcon } from "../components/icons";
import { ScenePhoto } from "../components/ScenePhoto";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { choiceOrder, practiceStages, taskDone } from "../lib/practiceTasks";
import { speak } from "../lib/speech";
import type { SessionTask, TaskActionResult } from "../lib/api";

export function ISpyPhase1() {
  const scene = useScene();
  const { session } = useAppState();
  const [index, setIndex] = useState(() => {
    const clues = practiceStages(session?.tasks ?? []).clues;
    const next = clues.findIndex(task => !taskDone(task));
    return next < 0 ? Math.max(0, clues.length - 1) : next;
  });
  if (!session) return null;
  const { learning, clues } = practiceStages(session.tasks);
  const base = `/practice/sessions/${scene.sessionId}`;
  if (session.session.status === "completed") return <Navigate to={`${base}/summary`} replace />;
  if (!learning.every(taskDone) || ["abandoned", "failed"].includes(session.session.status)) return <Navigate to={`${base}/learn`} replace />;
  const task = clues[index];
  if (!task) return <Navigate to={`${base}/ispy-2`} replace />;
  return <ClueRound key={task.id} task={task} index={index} total={clues.length} onNext={() => setIndex(value => value + 1)} />;
}

function ClueRound({ task, index, total, onNext }: { task: SessionTask; index: number; total: number; onNext: () => void }) {
  const navigate = useNavigate();
  const scene = useScene();
  const { actOnTask, practiceSaving, practiceError } = useAppState();
  const [picked, setPicked] = useState<string | null>(null);
  const [result, setResult] = useState<TaskActionResult | null>(null);
  const [showTranslation, setShowTranslation] = useState(false);
  const [checking, setChecking] = useState(false);
  const request = useRef<{ answer: string; key: string } | null>(null);
  const submitting = useRef(false);
  const content = task.publicContent;
  if (content.kind !== "ispyRound") return null;
  const opening = scene.languageCode === "es"
    ? "Veo, veo, algo que"
    : scene.languageCode === "fr"
      ? "Je vois, je vois, quelque chose qui"
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
      if (saved) request.current = null;
    } finally {
      submitting.current = false;
      setChecking(false);
    }
  };
  const selected = content.options.find(option => option.optionId === picked);
  return <div className="stack">
    <h2 className="text-center">I-Spy · Linguini's clues</h2>
    <p>Use the clues to find the word</p>
    <ProgressTrail value={index + (answered ? 1 : 0)} total={total} label={`${index + 1} / ${total}`} />
    <ScenePhoto scene={scene} activeItemId={result?.attempt?.isCorrect ? selected?.sceneObjectId : null} />
    <div className="card card--lifted stack-2">
      <div className="spread"><span className="label muted">Linguini says</span><IconButton label="Hear the clue" onClick={() => speak(`${opening} ${content.clue}`, scene.languageCode)}><SpeakerIcon /></IconButton></div>
      <h3>{opening} {content.clue}</h3>
      {content.clueTranslation ? showTranslation ? <p className="small muted">{content.clueTranslation}</p> : <button type="button" className="text-link text-link--muted" onClick={() => setShowTranslation(true)}>See translation</button> : null}
    </div>
    <div className="choice-grid">{choiceOrder(content.options, task.id, option => option.optionId).map(option => {
      const state = picked !== option.optionId ? "" : result?.attempt?.isCorrect != null ? (result.attempt.isCorrect ? " choice--correct" : " choice--incorrect") : " choice--selected";
      return <button key={option.optionId} type="button" className={`choice${state}`} aria-pressed={picked === option.optionId} disabled={answered || practiceSaving || checking} onClick={() => void choose(option.optionId)}>
        {result?.attempt?.isCorrect && picked === option.optionId ? <CheckIcon size={16} /> : null}{option.label}
      </button>;
    })}</div>
    {checking ? <p className="choice-checking" role="status">Checking your answer…</p> : null}
    {answered || result ? <Feedback tone={result?.attempt?.isCorrect === false ? "warn" : "good"}><div className="stack-2" role="status"><strong>{task.status === "skipped" ? "Skipped — no XP earned." : result?.attempt?.feedback?.message ?? "Answer saved."}</strong>{content.encouragement ? <span className="small muted">{content.encouragement}</span> : null}</div></Feedback> : null}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    <Button block disabled={!answered || practiceSaving} onClick={() => index === total - 1 ? navigate(`/practice/sessions/${scene.sessionId}/ispy-2`) : onNext()}>{index === total - 1 ? "Your turn" : "Next clue"} <ArrowRightIcon /></Button>
    {!answered ? <Button variant="quiet" block disabled={practiceSaving} onClick={() => void actOnTask(task.id, "skip")}>Skip task</Button> : null}
  </div>;
}

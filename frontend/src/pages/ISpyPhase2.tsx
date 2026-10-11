import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Button, Card, Feedback, ProgressTrail, TopBar } from "../components/ui";
import { ArrowRightIcon } from "../components/icons";
import { ScenePhoto } from "../components/ScenePhoto";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { practiceStages, taskDone } from "../lib/practiceTasks";
import { descriptionEvaluation } from "../lib/api";
import type { ISpyDescriptionEvaluation, ISpyDescriptionOutcome, SessionTask } from "../lib/api";
import type { LanguageItem } from "../data/types";

export function ISpyPhase2() {
  const scene = useScene();
  const navigate = useNavigate();
  const { session, completeSession, completionPending, completionError, practiceError } = useAppState();
  const [index, setIndex] = useState(() => {
    const tasks = practiceStages(session?.tasks ?? []).reflection;
    const next = tasks.findIndex(task => !taskDone(task));
    return next < 0 ? Math.max(0, tasks.length - 1) : next;
  });
  if (!session) return null;
  const { learning, clues, reflection } = practiceStages(session.tasks);
  const base = `/practice/sessions/${scene.sessionId}`;
  if (session.session.status === "completed") return <Navigate to={`${base}/summary`} replace />;
  if (!learning.every(taskDone) || ["abandoned", "failed"].includes(session.session.status)) return <Navigate to={`${base}/learn`} replace />;
  if (!clues.every(taskDone)) return <Navigate to={`${base}/ispy-1`} replace />;
  const task = reflection[index];
  const finish = () => { if (completeSession()) navigate(`${base}/summary`); };
  const alerts = [practiceError, completionError].filter(Boolean);
  if (!task) return <div className="stack"><TopBar title="Practice complete" />{alerts.map((message, alertIndex) => <p key={alertIndex} role="alert">{message}</p>)}<Button disabled={completionPending} onClick={finish}>Finish session</Button></div>;
  return <Reflection key={task.id} task={task} index={index} total={reflection.length} onNext={() => index === reflection.length - 1 ? finish() : setIndex(value => value + 1)} />;
}

const OUTCOME_PROMPTS: Record<ISpyDescriptionOutcome, string> = {
  clearMatch: "Is this the object you described?",
  needsClarification: "Linguini can't decide between a few objects. Add a detail that sets yours apart.",
  needsRevision: "Part of your clue doesn't fit this object. Check your clue and try again.",
  noMatch: "That's not the object you described. Add another detail.",
  evaluationFailed: "Your clue is saved. Retry guessing when you're ready.",
};

type LatestGuess = { attemptId: string; evaluation: ISpyDescriptionEvaluation; feedback: string | null };

function Reflection({ task, index, total, onNext }: { task: SessionTask; index: number; total: number; onNext: () => void }) {
  const scene = useScene();
  const { actOnTask, practiceSaving, practiceError, session } = useAppState();
  const [text, setText] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [guess, setGuess] = useState<LatestGuess | null>(null);
  const [revising, setRevising] = useState(false);
  const request = useRef<{ answer: string; key: string } | null>(null);
  const submitting = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { if (revising) input.current?.focus(); }, [revising]);
  const target = scene.items.find(item => item.id === task.sceneObjectId);
  const guessedId = guess?.evaluation.guessedObjectKey ?? null;
  const guessed = guessedId ? scene.items.find(item => item.id === guessedId) ?? null : null;
  const content = task.publicContent;
  if (content.kind !== "reflection") return null;
  const opening = scene.languageCode === "es"
    ? "Veo, veo, algo que"
    : scene.languageCode === "fr"
      ? "Je vois, je vois, quelque chose qui"
      : "I spy with my little eye, something that";
  const suggestions = [
    ...scene.items.map(item => item.word),
    ...(session?.translationPreview?.attributes.map(item => item.translation) ?? []),
    ...(session?.translationPreview?.relationships.map(item => item.translation) ?? []),
  ].filter((word, wordIndex, words) => words.findIndex(item => item.toLocaleLowerCase() === word.toLocaleLowerCase()) === wordIndex);
  const answered = taskDone(task);
  const locked = answered || practiceSaving || guess !== null;
  const markers = [target, guessed && guessed.id !== target?.id ? guessed : null].filter((item): item is LanguageItem => Boolean(item));
  const submit = async () => {
    const answer = text.trim();
    if (!answer || answered || practiceSaving || submitting.current) return;
    submitting.current = true;
    // A network retry reuses the key; a revised clue or "Retry guessing" gets a new one.
    if (request.current?.answer !== answer) request.current = { answer, key: crypto.randomUUID() };
    try {
      const result = await actOnTask(task.id, "attempts", { inputMode: "text", text: answer }, request.current.key);
      if (result) {
        request.current = null;
        setRevising(false);
        const evaluation = descriptionEvaluation(result.attempt);
        if (result.attempt && evaluation) setGuess({ attemptId: result.attempt.id, evaluation, feedback: result.attempt.feedback?.message ?? null });
        else setFeedback(result.attempt?.feedback?.message ?? "Reflection saved.");
      }
    } finally { submitting.current = false; }
  };
  const confirm = async () => {
    if (!guess) return;
    if (await actOnTask(task.id, "confirm-guess", { attemptId: guess.attemptId })) setFeedback("Linguini found your object!");
  };
  const improve = () => { setGuess(null); setRevising(true); };
  const outcome = guess?.evaluation.outcome;
  return <div className="stack">
    <TopBar title="I-Spy · Your turn" help="Describe the object so Linguini can guess it." />
    <ProgressTrail value={index + (answered ? 1 : 0)} total={total} label={`${index + 1} / ${total}`} />
    <ScenePhoto scene={scene} items={markers} activeItemId={target?.id ?? null} guessItemId={guessed?.id ?? null} />
    {guessed && target ? <p className="small muted" data-testid="guess-legend">{guessed.id === target.id
      ? `Linguini's guess is your object (marker ${target.marker}).`
      : `Your object: marker ${target.marker} · Linguini's guess: marker ${guessed.marker} (dashed)`}</p> : null}
    <Card><div className="stack-2"><span className="label muted">Describe this object</span><h2>{target?.word}</h2><span className="small muted">{target?.translation}</span><p>{content.prompt}</p></div></Card>
    <div className="stack-2"><span className="label muted">Words from this scene</span><div className="chip-row">{suggestions.map(word => <button key={word} type="button" className="chip" disabled={locked} onClick={() => setText(value => `${value} ${word}`.trim())}>{word}</button>)}</div></div>
    <div className="field"><label className="field__label" htmlFor="reflection">Your clue</label><p className="ispy-opening">{opening}</p><input id="reflection" ref={input} className="input" value={text} maxLength={2000} disabled={locked} onChange={event => setText(event.target.value)} /></div>
    {answered || feedback || guess ? <Feedback><div className="stack-2" role="status">
      {outcome && outcome !== "evaluationFailed" ? <strong>{guessed ? `Linguini guessed: ${guessed.word}` : "Linguini couldn't match your clue to an object."}</strong> : null}
      {task.status === "skipped" ? <span>Skipped — no XP earned.</span> : <>
        {guess?.feedback ? <span>{guess.feedback}</span> : null}
        {outcome && !answered ? <span>{OUTCOME_PROMPTS[outcome]}</span> : null}
        {feedback || (answered && !guess) ? <span>{feedback ?? "Reflection saved."}</span> : null}
      </>}
    </div></Feedback> : null}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    {answered ? <Button block disabled={practiceSaving} onClick={onNext}>{index === total - 1 ? "Finish session" : "Next item"} <ArrowRightIcon /></Button> : <>
      {!guess ? <Button block disabled={!text.trim() || practiceSaving} onClick={() => void submit()}>Send my response</Button> : null}
      {outcome === "clearMatch" ? <Button block disabled={practiceSaving} onClick={() => void confirm()}>That's it</Button> : null}
      {outcome === "evaluationFailed" ? <Button block disabled={practiceSaving} onClick={() => void submit()}>Retry guessing</Button> : null}
      {guess ? <Button variant="secondary" block disabled={practiceSaving} onClick={improve}>Improve my clue</Button> : null}
      <Button variant="quiet" block disabled={practiceSaving} onClick={() => void actOnTask(task.id, "skip")}>Skip task</Button>
    </>}
  </div>;
}

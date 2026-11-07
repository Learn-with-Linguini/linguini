import { basilEarnedText } from "../lib/gamification";
import { InlineLoader } from "../components/LoadingScreen";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useNavigate } from "react-router-dom";
import { sessionDestination, sessionPaths } from "../lib/sessionRoute";
import { BasilReward, Button, Feedback, ProgressTrail, TopBar } from "../components/ui";
import { ArrowRightIcon, CloseIcon } from "../components/icons";
import { ScenePhoto } from "../components/ScenePhoto";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { practiceStages, taskDone } from "../lib/practiceTasks";
import { trackAction } from "../lib/analytics.ts";
import { CLUE_ASSISTANCE_VERSION, descriptionEvaluation, getLatestAttempt } from "../lib/api";
import { queryKeys } from "../lib/queryKeys";
import type { ClueAssistance, ISpyDescriptionEvaluation, ISpyDescriptionOutcome, SessionTask, TaskAnswer } from "../lib/api";
import { mentionsTarget, nearTarget, savedAssistance, visibleFrames } from "../lib/clueFrames";
import type { LanguageItem } from "../data/types";
import { ReportIssueLink } from "../components/ReportIssueLink";
import { learningFeedback } from "../lib/learningFeedback";
import { ISpyLevelHelp } from "../components/ISpyLevelHelp";
import { MissionCheatSheetLauncher } from "../components/MissionCheatSheet";
import { clueExample, clueOpening } from "../lib/ispyClue";

export function ISpyPhase2() {
  const navigate = useNavigate();
  const { session, completeSession, completionPending, completionError, practiceError } = useAppState();
  const completionStarted = useRef(false);
  const [index, setIndex] = useState(() => {
    const tasks = practiceStages(session?.tasks ?? []).reflection;
    const next = tasks.findIndex(task => !taskDone(task));
    return next < 0 ? Math.max(0, tasks.length - 1) : next;
  });
  useEffect(() => {
    if (!session || completionStarted.current) return;
    const { learning, clues, reflection } = practiceStages(session.tasks);
    if (reflection.length || !learning.every(taskDone) || !clues.every(taskDone)
      || ["completed", "abandoned", "failed"].includes(session.session.status)) return;
    completionStarted.current = true;
    if (completeSession()) {
      trackAction("describe_round_skipped", { mode: session.session.mode });
      navigate(sessionPaths(session).done, { replace: true });
    }
  }, [session, completeSession, navigate]);
  if (!session) return null;
  const { learning, clues, reflection } = practiceStages(session.tasks);
  const paths = sessionPaths(session);
  const game = session.session.mode === "ispy";
  if (session.session.status === "completed") return <Navigate to={paths.done} replace />;
  if (game && ["abandoned", "failed"].includes(session.session.status)) {
    const exit = sessionDestination(session);
    return <Navigate to={exit.path} replace state={exit.notice ? { practiceNotice: exit.notice } : undefined} />;
  }
  if (!learning.every(taskDone) || ["abandoned", "failed"].includes(session.session.status)) return <Navigate to={paths.exit} replace />;
  if (!clues.every(taskDone)) return <Navigate to={paths.clues} replace />;
  const task = reflection[index];
  const finishLabel = game ? "See results" : "Finish session";
  const finish = () => { if (completeSession()) navigate(paths.done); };
  const alerts = [practiceError, completionError].filter(Boolean);
  if (!task && !reflection.length) return alerts.length
    ? <div className="stack"><TopBar title={game ? "Game complete" : "Practice complete"} />
      {alerts.map((message, alertIndex) => <p key={alertIndex} role="alert">{message}</p>)}
      <Button disabled={completionPending} onClick={finish}>{finishLabel}</Button>
    </div>
    : <div className="stack"><InlineLoader label="Finishing your session" /></div>;
  if (!task) return <div className="stack"><TopBar title={game ? "Game complete" : "Practice complete"} />
    {alerts.map((message, alertIndex) => <p key={alertIndex} role="alert">{message}</p>)}
    <Button disabled={completionPending} onClick={finish}>{finishLabel}</Button>
  </div>;
  return <Reflection key={task.id} task={task} index={index} total={reflection.length} finishLabel={finishLabel}
    onExit={() => { trackAction("ispy_exit_clicked", { phase: "describe" }); navigate("/home"); }}
    onNext={() => index === reflection.length - 1 ? finish() : setIndex(value => value + 1)} />;
}

const OUTCOME_PROMPTS: Record<ISpyDescriptionOutcome, string> = {
  clearMatch: "Is this the object you described?",
  needsClarification: "Linguini can't decide between a few objects. Add a detail that sets yours apart.",
  needsRevision: "Part of your clue doesn't fit this object. Check your clue and try again.",
  noMatch: "That's not the object you described. Add another detail.",
  evaluationFailed: "Your clue is saved. Retry guessing when you're ready.",
};

type LatestGuess = { attemptId: string; evaluation: ISpyDescriptionEvaluation; feedback: string | null };

function Reflection({ task, index, total, finishLabel, onExit, onNext }: { task: SessionTask; index: number; total: number; finishLabel: string; onExit: () => void; onNext: () => void }) {
  const scene = useScene();
  const { actOnTask, practiceSaving, practiceError } = useAppState();
  const [text, setText] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [basilEarned, setBasilEarned] = useState<number>();
  const [guess, setGuess] = useState<LatestGuess | null>(null);
  const [revising, setRevising] = useState(false);
  // Word bank words the learner tapped into the clue, recorded as guided help.
  const [insertedChips, setInsertedChips] = useState<string[]>([]);
  // A pending task has no attempts; any other task restores its latest one before taking input.
  const [hydrated, setHydrated] = useState(task.status === "pending");
  const latest = useQuery({
    queryKey: queryKeys.latestAttempt(task.id),
    queryFn: ({ signal }) => getLatestAttempt(task.id, signal),
    enabled: task.status !== "pending",
    staleTime: 0,
    refetchOnMount: "always",
  });
  useEffect(() => {
    if (hydrated || !latest.isSuccess || latest.isFetching) return;
    setHydrated(true);
    const saved = latest.data.attempt;
    if (!saved) return;
    setText(current => current || saved.text);
    setInsertedChips(saved.assistance?.insertedChips ?? []);
    const evaluation = saved.evaluationDetails;
    if (evaluation) setGuess({ attemptId: saved.id, evaluation, feedback: saved.feedback });
    if (task.status === "completed") setFeedback(evaluation?.outcome === "clearMatch" ? "Linguini found your object!" : saved.feedback ?? "Reflection saved.");
  }, [hydrated, latest.isSuccess, latest.isFetching, latest.data, task.status]);
  const request = useRef<{ fingerprint: string; key: string } | null>(null);
  const submitting = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { if (revising) input.current?.focus(); }, [revising]);
  const target = scene.items.find(item => item.id === task.sceneObjectId);
  const guessedId = guess?.evaluation.guessedObjectKey ?? null;
  const guessed = guessedId ? scene.items.find(item => item.id === guessedId) ?? null : null;
  const content = task.publicContent;
  if (content.kind !== "reflection") return null;
  const frames = visibleFrames(content.clueFrames);
  const namesTarget = mentionsTarget(text, content.avoidWords ?? []);
  const nearName = !namesTarget && nearTarget(text, content.avoidWords ?? []);
  // A word bank word joins the end of the clue; it counts as guided help like a chip.
  const addWord = (word: string) => {
    setText(current => {
      const base = current.trimEnd();
      return base ? `${base} ${word}` : word;
    });
    setInsertedChips(chips => chips.includes(word) ? chips : [...chips, word]);
    input.current?.focus();
  };
  const answered = taskDone(task);
  const restoreFailed = !hydrated && latest.isError;
  const locked = answered || practiceSaving || guess !== null || !hydrated;
  const markers = [target, guessed && guessed.id !== target?.id ? guessed : null].filter((item): item is LanguageItem => Boolean(item));
  const submit = async () => {
    const answer = text.trim();
    if (!answer || namesTarget || answered || practiceSaving || !hydrated || submitting.current) return;
    submitting.current = true;
    // The clue patterns are offered help; tapped word bank words are the help used.
    const assistance: ClueAssistance | null = frames.length || insertedChips.length ? {
      version: CLUE_ASSISTANCE_VERSION, practiceMode: "guided", targetWordShown: true,
      offeredFrameIds: frames.map(frame => frame.frameId), selectedFrameIds: [], insertedChips,
      selectedSlots: [], revealedHelpFrameIds: [],
    } : null;
    const body: TaskAnswer = assistance ? { inputMode: "text", text: answer, assistance } : { inputMode: "text", text: answer };
    const fingerprint = JSON.stringify(body);
    // A network retry reuses the key; a revised clue or "Retry guessing" gets a new one.
    if (request.current?.fingerprint !== fingerprint) request.current = { fingerprint, key: crypto.randomUUID() };
    try {
      const result = await actOnTask(task.id, "attempts", body, request.current.key);
      if (result) {
        request.current = null;
        setRevising(false);
        const saved = savedAssistance(result.attempt?.responsePayload);
        if (saved) setInsertedChips(saved.insertedChips);
        const evaluation = descriptionEvaluation(result.attempt);
        trackAction("ispy_description_submitted", { outcome: evaluation?.outcome });
        if (result.attempt && evaluation) setGuess({ attemptId: result.attempt.id, evaluation, feedback: result.attempt.feedback?.message ?? null });
        else setFeedback(result.attempt?.feedback?.message ?? "Reflection saved.");
      }
    } finally { submitting.current = false; }
  };
  const confirm = async () => {
    if (!guess) return;
    const result = await actOnTask(task.id, "confirm-guess", { attemptId: guess.attemptId });
    if (result) {
      trackAction("ispy_match_confirmed");
      setFeedback("Linguini found your object!");
      setBasilEarned(result.basilEarned);
    }
  };
  const improve = () => { setGuess(null); setRevising(true); };
  const outcome = guess?.evaluation.outcome;
  return <div className="stack">
    <div className="vocabulary-flow__header">
      <div className="learning-title-row">
        <div className="vocabulary-flow__title"><h1>Your Clues</h1></div>
        <div className="learning-title-actions">
          <div className="learning-title-primary-actions">
            {content.cheatSheet ? <MissionCheatSheetLauncher missionId={content.cheatSheet.missionId}
              practiceLevel={content.cheatSheet.practiceLevel} contentVersion={content.cheatSheet.contentVersion}
              languageCode={scene.languageCode} /> : null}
            {hydrated && !answered ? <button type="button" className="vocabulary-flow__skip-pill" disabled={practiceSaving}
              onClick={() => void actOnTask(task.id, "skip")}>Skip<span className="vocabulary-flow__skip-more"> this task</span></button> : null}
          </div>
          <div className="learning-title-progress-actions">
            <Button variant="quiet" className="learning-exit" onClick={onExit}><CloseIcon size={18} /> Exit</Button>
          </div>
        </div>
      </div>
      <div className="vocabulary-flow__progress"><ProgressTrail value={index + (answered ? 1 : 0)} total={total} label={`Object ${index + 1} of ${total}`} /></div>
    </div>
    {/* Desktop keeps the photo beside the clue writing; phones stack them. */}
    <div className="lesson-flow__body">
    <div className="lesson-flow__scene">
      <ScenePhoto scene={scene} items={markers} activeItemId={target?.id ?? null} guessItemId={guessed?.id ?? null} />
      {guessed && target ? <p className="small muted" data-testid="guess-legend">{guessed.id === target.id
        ? `Linguini's guess is your object (marker ${target.marker}).`
        : `Your object: marker ${target.marker} · Linguini's guess: marker ${guessed.marker} (dashed)`}</p> : null}
    </div>
    <div className="lesson-flow__panel stack">
    {/* One card for the round: what to do, the object, word help, then the learner's clue. */}
    <section className="ispy-round-card" aria-label="Describe your object">
    {!answered ? <h2 className="ispy-instruction">Describe the highlighted object so Linguini can find it.</h2> : null}
    <div className="ispy-target-card">
      {/* With its article (la chaise) when the task carries it; older tasks show the bare word. */}
      <strong className="ispy-target-card__word" lang={scene.languageCode}>{content.targetPhrase ?? target?.word}</strong>
      <span className="ispy-target-card__meaning">{target?.translation}</span>
    </div>
    <ISpyLevelHelp support={content} languageCode={scene.languageCode} showCheatSheet={false} onPick={locked ? undefined : addWord}
      canPick={word => !mentionsTarget(word, content.avoidWords ?? [])} />
    {/* The clue carries on from the I-Spy opener, so the opener labels the field. */}
    <div className="field"><label className="field__label ispy-clue-opening" htmlFor="reflection">
      <span className="visually-hidden">Your clue, continuing: </span>
      <span lang={scene.languageCode}>{clueOpening(scene.languageCode)}</span>
    </label>
      <input id="reflection" ref={input} className="input" value={text} maxLength={2000} disabled={locked}
        lang={scene.languageCode}
        placeholder={`e.g. ${clueExample(scene.languageCode)}…`}
        onChange={event => setText(event.target.value)} />
    </div>
    </section>
    {!hydrated && !restoreFailed ? <InlineLoader compact testId="restoring" label="Loading your last clue" /> : null}
    {restoreFailed ? <div className="stack-2" role="alert" data-testid="restore-error"><span>We couldn't load your saved clue, so this task can't continue yet.</span><Button variant="secondary" onClick={() => void latest.refetch()}>Try again</Button></div> : null}
    {nearName && !locked ? <p className="small muted" data-testid="clue-near-warning">One word looks close to this object's name. If it's a different word, you can still send it.</p> : null}
    {namesTarget && !locked ? <p className="clue-warning" data-testid="clue-warning" role="alert">Your clue uses the word for this object. Change your clue to describe it without naming it.</p> : null}
    {answered || feedback || guess ? <Feedback><div className="stack-2" role="status">
      {outcome && outcome !== "evaluationFailed" ? <strong>{guessed ? `Linguini guessed: ${guessed.word}` : "Linguini couldn't match your clue to an object."}</strong> : null}
      {task.status === "skipped" ? <span>Skipped.</span> : <>
        {outcome === "clearMatch" && task.status === "completed" ? <strong>{learningFeedback("correct", task.id)}</strong>
          : outcome === "needsRevision" || outcome === "noMatch" ? <strong>{learningFeedback("incorrect", task.id)}</strong> : null}
        {guess?.feedback ? <span>{guess.feedback}</span> : null}
        {outcome && !answered ? <span>{OUTCOME_PROMPTS[outcome]}</span> : null}
        {feedback || (answered && !guess) ? <span>{feedback ?? "Reflection saved."}</span> : null}
      </>}
    </div></Feedback> : null}
    {answered || feedback || guess ? <BasilReward text={basilEarnedText(basilEarned)} /> : null}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    {!hydrated ? null : answered ? <Button block disabled={practiceSaving} onClick={onNext}>{index === total - 1 ? finishLabel : "Next item"} <ArrowRightIcon /></Button> : <>
      {!guess ? <Button block disabled={!text.trim() || namesTarget || practiceSaving} onClick={() => void submit()}>Send my response</Button> : null}
      {outcome === "clearMatch" ? <Button block disabled={practiceSaving} onClick={() => void confirm()}>That's it</Button> : null}
      {outcome === "evaluationFailed" ? <Button block disabled={practiceSaving} onClick={() => void submit()}>Retry guessing</Button> : null}
      {guess ? <Button variant="secondary" block disabled={practiceSaving} onClick={improve}>Improve my clue</Button> : null}
    </>}
    {(answered || guess) && task.status !== "skipped" ? <div className="learning-question-report"><ReportIssueLink label="Report a wrong guess" reportType="I-Spy guess" fields={[
      ["Task ID", task.id],
      ["Object shown", target?.word],
      ["Your clue", text.trim()],
      ["Linguini guessed", guessed?.word],
      ["Displayed feedback", guess?.feedback ?? feedback],
      ["Language", scene.languageCode],
    ]} /></div> : null}
    </div>
    </div>
  </div>;
}

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useNavigate } from "react-router-dom";
import { sessionDestination, sessionPaths } from "../lib/sessionRoute";
import { Button, Card, Feedback, ProgressTrail, TopBar, XpPill } from "../components/ui";
import { ArrowRightIcon } from "../components/icons";
import { ScenePhoto } from "../components/ScenePhoto";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { practiceStages, taskDone, taskXp, xpEarnedText } from "../lib/practiceTasks";
import { CLUE_ASSISTANCE_VERSION, descriptionEvaluation, getLatestAttempt } from "../lib/api";
import { queryKeys } from "../lib/queryKeys";
import type { ClueAssistance, ClueFrame, ClueFrameId, ClueSlotId, ISpyDescriptionEvaluation, ISpyDescriptionOutcome, SessionTask, TaskAnswer } from "../lib/api";
import { applyFrame, choicesFromSlots, fillSlot, mentionsTarget, nearTarget, restoreSentences, savedAssistance, slotSentence, slotsFromChoices, usesEnglish, visibleFrames, writeSentence, type FrameSentences, type SlotChoices } from "../lib/clueFrames";
import type { LanguageItem } from "../data/types";
import { ReportIssueLink } from "../components/ReportIssueLink";

export function ISpyPhase2() {
  const navigate = useNavigate();
  const { session, completeSession, completionPending, completionError, practiceError } = useAppState();
  const [index, setIndex] = useState(() => {
    const tasks = practiceStages(session?.tasks ?? []).reflection;
    const next = tasks.findIndex(task => !taskDone(task));
    return next < 0 ? Math.max(0, tasks.length - 1) : next;
  });
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
  if (!task) return <div className="stack"><TopBar title={game ? "Game complete" : "Practice complete"} />{reflection.length ? null : <p data-testid="no-description-round">This photo doesn't have enough confirmed colours or positions for a describing round, so there's nothing to describe this time.</p>}{alerts.map((message, alertIndex) => <p key={alertIndex} role="alert">{message}</p>)}<Button disabled={completionPending} onClick={finish}>{finishLabel}</Button></div>;
  return <Reflection key={task.id} task={task} index={index} total={reflection.length} finishLabel={finishLabel} onNext={() => index === reflection.length - 1 ? finish() : setIndex(value => value + 1)} />;
}

const OUTCOME_PROMPTS: Record<ISpyDescriptionOutcome, string> = {
  clearMatch: "Is this the object you described?",
  needsClarification: "Linguini can't decide between a few objects. Add a detail that sets yours apart.",
  needsRevision: "Part of your clue doesn't fit this object. Check your clue and try again.",
  noMatch: "That's not the object you described. Add another detail.",
  evaluationFailed: "Your clue is saved. Retry guessing when you're ready.",
};

const FRAME_LABELS: Record<ClueFrameId, string> = { name: "Name", colour: "Colour", location: "Location" };

type LatestGuess = { attemptId: string; evaluation: ISpyDescriptionEvaluation; feedback: string | null };

function Reflection({ task, index, total, finishLabel, onNext }: { task: SessionTask; index: number; total: number; finishLabel: string; onNext: () => void }) {
  const scene = useScene();
  const { actOnTask, practiceSaving, practiceError, activeProfile } = useAppState();
  const [text, setText] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [xpEarned, setXpEarned] = useState<number>();
  const [guess, setGuess] = useState<LatestGuess | null>(null);
  const [revising, setRevising] = useState(false);
  const [activeFrameId, setActiveFrameId] = useState<ClueFrameId | null>(null);
  const [selectedFrameIds, setSelectedFrameIds] = useState<ClueFrameId[]>([]);
  const [insertedChips, setInsertedChips] = useState<string[]>([]);
  const [sentences, setSentences] = useState<FrameSentences>({});
  const [choices, setChoices] = useState<SlotChoices>({});
  const [revealedHelp, setRevealedHelp] = useState<ClueFrameId[]>([]);
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
    const savedFrames = task.publicContent.kind === "reflection" ? visibleFrames(task.publicContent.clueFrames) : [];
    const chips = saved.assistance?.insertedChips ?? [];
    const frameIds = saved.assistance?.selectedFrameIds ?? [];
    setText(current => current || saved.text);
    setSelectedFrameIds(frameIds);
    setInsertedChips(chips);
    setActiveFrameId(frameIds.at(-1) ?? null);
    const restored = choicesFromSlots(saved.assistance?.selectedSlots ?? []);
    setChoices(restored);
    setRevealedHelp(saved.assistance?.revealedHelpFrameIds ?? []);
    setSentences(restoreSentences(saved.text, savedFrames, chips, restored));
    const savedEvaluation = saved.evaluationDetails;
    const evaluation = savedEvaluation && "outcome" in savedEvaluation
      ? savedEvaluation
      : null;
    if (evaluation) setGuess({ attemptId: saved.id, evaluation, feedback: saved.feedback });
    if (task.status === "completed") setFeedback(evaluation?.outcome === "clearMatch" ? "Linguini found your object!" : saved.feedback ?? "Reflection saved.");
  }, [hydrated, latest.isSuccess, latest.isFetching, latest.data, task.publicContent, task.status]);
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
  const activeFrame = frames.find(frame => frame.frameId === activeFrameId) ?? null;
  const namesTarget = mentionsTarget(text, content.avoidWords ?? []);
  const englishClue = usesEnglish(text);
  const nearName = !namesTarget && nearTarget(text, content.avoidWords ?? []);
  const beginner = ["A0", "A1"].includes(activeProfile?.proficiencyLevel ?? "");
  const languageName = scene.languageCode === "es" ? "Spanish"
    : scene.languageCode === "fr" ? "French" : "your learning language";
  const chooseFrame = (frame: ClueFrame) => {
    setActiveFrameId(frame.frameId);
    setSelectedFrameIds(ids => ids.includes(frame.frameId) ? ids : [...ids, frame.frameId]);
    const next = applyFrame({ text, sentences }, frame);
    setText(next.text);
    setSentences(next.sentences);
  };
  const chooseChip = (frame: ClueFrame, chip: string) => {
    const next = fillSlot({ text, sentences }, frame, chip);
    setText(next.text);
    setSentences(next.sentences);
    setInsertedChips(chips => chips.includes(chip) ? chips : [...chips, chip]);
  };
  const chooseSlotChip = (frame: ClueFrame, slotId: ClueSlotId, chip: string) => {
    const picks = { ...choices[frame.frameId], [slotId]: chip };
    const next = writeSentence({ text, sentences }, frame.frameId, slotSentence(frame, picks));
    setText(next.text);
    setSentences(next.sentences);
    setChoices(all => ({ ...all, [frame.frameId]: picks }));
    setInsertedChips(chips => chips.includes(chip) ? chips : [...chips, chip]);
  };
  const chooseHelp = (frame: ClueFrame, phrase: string) => {
    chooseChip(frame, phrase);
    setChoices(all => ({ ...all, [frame.frameId]: undefined }));
  };
  const answered = taskDone(task);
  const reward = !answered ? taskXp(task) : null;
  const restoreFailed = !hydrated && latest.isError;
  const locked = answered || practiceSaving || guess !== null || !hydrated;
  const markers = [target, guessed && guessed.id !== target?.id ? guessed : null].filter((item): item is LanguageItem => Boolean(item));
  const submit = async () => {
    const answer = text.trim();
    if (!answer || namesTarget || englishClue || answered || practiceSaving || !hydrated || submitting.current) return;
    submitting.current = true;
    const assistance: ClueAssistance | null = frames.length ? {
      version: CLUE_ASSISTANCE_VERSION, practiceMode: "guided", targetWordShown: true,
      offeredFrameIds: frames.map(frame => frame.frameId), selectedFrameIds, insertedChips,
      selectedSlots: slotsFromChoices(choices), revealedHelpFrameIds: revealedHelp,
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
        if (saved) {
          setSelectedFrameIds(saved.selectedFrameIds);
          setInsertedChips(saved.insertedChips);
          setActiveFrameId(saved.selectedFrameIds.at(-1) ?? null);
          setChoices(choicesFromSlots(saved.selectedSlots));
          setRevealedHelp(saved.revealedHelpFrameIds);
        }
        const evaluation = descriptionEvaluation(result.attempt);
        if (result.attempt && evaluation) setGuess({ attemptId: result.attempt.id, evaluation, feedback: result.attempt.feedback?.message ?? null });
        else setFeedback(result.attempt?.feedback?.message ?? "Reflection saved.");
      }
    } finally { submitting.current = false; }
  };
  const confirm = async () => {
    if (!guess) return;
    const result = await actOnTask(task.id, "confirm-guess", { attemptId: guess.attemptId });
    if (result) {
      setFeedback("Linguini found your object!");
      setXpEarned(result.xpEarned);
    }
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
    <Card><div className="stack-2"><div className="spread"><span className="label muted">Describe this object</span>{reward ? <XpPill {...reward} /> : null}</div><h2>{target?.word}</h2><span className="small muted">{target?.translation}</span><p>{content.prompt}</p></div></Card>
    {beginner ? <Card><div className="stack-2" data-testid="beginner-guide">
      <strong>How to give a clue</strong>
      <span>1. Tap Colour or Location to start a sentence.</span>
      <span>2. Tap words to fill it in — each shows its English meaning.</span>
      <span>3. Stuck? Tap Help me for phrases that fit your object.</span>
    </div></Card> : null}
    {frames.length ? <div className="stack-2" data-testid="clue-frames">
      <span className="label muted">Clue frames (optional)</span>
      <div className="chip-row">{frames.map(frame => <button key={frame.frameId} type="button" className={`chip${frame.frameId === activeFrameId ? " chip--selected" : ""}`} aria-pressed={frame.frameId === activeFrameId} disabled={locked} onClick={() => chooseFrame(frame)}>{FRAME_LABELS[frame.frameId]}</button>)}</div>
      {activeFrame ? <div className="clue-frame stack-2" data-testid="clue-frame">
        <strong lang={scene.languageCode}>{activeFrame.template ?? `${activeFrame.prefix} …`}</strong>
        <span className="small">{activeFrame.meaning}</span>
        <span className="small muted">Example: <span lang={scene.languageCode}>{activeFrame.example}</span></span>
        {activeFrame.chips.length ? <div className="chip-row">{activeFrame.chips.map(chip => <button key={chip} type="button" className={`chip${insertedChips.includes(chip) ? " chip--selected" : ""}`} disabled={locked} onClick={() => chooseChip(activeFrame, chip)}>{chip}</button>)}</div> : null}
        {(activeFrame.slots ?? []).map(slot => <div key={slot.slotId} className="stack-2" data-testid={`clue-slot-${slot.slotId}`}>
          <span className="small muted">Choose a {slot.label}</span>
          <div className="chip-row">{slot.chips.map(chip => {
            const picked = choices[activeFrame.frameId]?.[slot.slotId] === chip.text;
            return <button key={chip.text} type="button" lang={scene.languageCode} title={!beginner ? chip.meaning ?? undefined : undefined} className={`chip${picked ? " chip--selected" : ""}${beginner && chip.meaning ? " chip--meaning" : ""}`} aria-pressed={picked} disabled={locked} onClick={() => chooseSlotChip(activeFrame, slot.slotId, chip.text)}>{chip.text}{beginner && chip.meaning ? <small className="chip__meaning">{chip.meaning}</small> : null}</button>;
          })}</div>
          {slot.slotId === "position" ? <ul className="small muted" data-testid="position-meanings">{slot.chips.filter(chip => chip.meaning).map(chip => <li key={chip.text}><span lang={scene.languageCode}>{chip.text}</span> — {chip.meaning}{chip.example ? <> · <span lang={scene.languageCode}>{chip.example}</span></> : null}</li>)}</ul> : null}
        </div>)}
        {activeFrame.help?.length ? revealedHelp.includes(activeFrame.frameId)
          ? <div className="stack-2" data-testid="clue-help"><span className="small muted">Suggested phrases (guided help)</span><div className="chip-row">{activeFrame.help.map(phrase => <button key={phrase} type="button" lang={scene.languageCode} className={`chip${insertedChips.includes(phrase) ? " chip--selected" : ""}`} disabled={locked} onClick={() => chooseHelp(activeFrame, phrase)}>{phrase}</button>)}</div></div>
          : <Button variant="secondary" disabled={locked} onClick={() => setRevealedHelp(ids => [...ids, activeFrame.frameId])}>Help me</Button> : null}
      </div> : null}
    </div> : null}
    <div className="field"><label className="field__label" htmlFor="reflection">Your clue</label><input id="reflection" ref={input} className="input" value={text} maxLength={2000} disabled={locked} onChange={event => setText(event.target.value)} /></div>
    {!hydrated && !restoreFailed ? <p className="small muted" role="status" data-testid="restoring">Loading your last clue…</p> : null}
    {restoreFailed ? <div className="stack-2" role="alert" data-testid="restore-error"><span>We couldn't load your saved clue, so this task can't continue yet.</span><Button variant="secondary" onClick={() => void latest.refetch()}>Try again</Button></div> : null}
    {nearName && !locked ? <p className="small muted" data-testid="clue-near-warning">One word looks close to this object's name. If it's a different word, you can still send it.</p> : null}
    {namesTarget && !locked ? <p className="clue-warning" data-testid="clue-warning" role="alert">Your clue uses the word for this object. Change your clue to describe it without naming it.</p> : null}
    {englishClue && !locked ? <p className="clue-warning" data-testid="clue-language-warning" role="alert">Write your clue in {languageName}, not English.</p> : null}
    {answered || feedback || guess ? <Feedback><div className="stack-2" role="status">
      {outcome && outcome !== "evaluationFailed" ? <strong>{guessed ? `Linguini guessed: ${guessed.word}` : "Linguini couldn't match your clue to an object."}</strong> : null}
      {task.status === "skipped" ? <span>Skipped — no XP earned.</span> : <>
        {guess?.feedback ? <span>{guess.feedback}</span> : null}
        {outcome === "clearMatch" && guess?.evaluation.ambiguous ? <span>Other objects could fit this clue too — next time add a colour or a position.</span> : null}
        {outcome && !answered ? <span>{OUTCOME_PROMPTS[outcome]}</span> : null}
        {feedback || (answered && !guess) ? <span>{feedback ?? "Reflection saved."}</span> : null}
        {xpEarnedText(xpEarned) ? <strong>{xpEarnedText(xpEarned)}</strong> : null}
      </>}
    </div></Feedback> : null}
    {(answered || guess) && task.status !== "skipped" ? <ReportIssueLink label="Report a wrong guess" reportType="I-Spy guess" fields={[
      ["Task ID", task.id],
      ["Object shown", target?.word],
      ["Your clue", text.trim()],
      ["Linguini guessed", guessed?.word],
      ["Displayed feedback", guess?.feedback ?? feedback],
      ["Language", scene.languageCode],
    ]} /> : null}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    {!hydrated ? null : answered ? <Button block disabled={practiceSaving} onClick={onNext}>{index === total - 1 ? finishLabel : "Next item"} <ArrowRightIcon /></Button> : <>
      {!guess ? <Button block disabled={!text.trim() || namesTarget || englishClue || practiceSaving} onClick={() => void submit()}>Send my response</Button> : null}
      {outcome === "clearMatch" ? <Button block disabled={practiceSaving} onClick={() => void confirm()}>That's it</Button> : null}
      {outcome === "evaluationFailed" ? <Button block disabled={practiceSaving} onClick={() => void submit()}>Retry guessing</Button> : null}
      {guess ? <Button variant="secondary" block disabled={practiceSaving} onClick={improve}>Improve my clue</Button> : null}
      <Button variant="quiet" block disabled={practiceSaving} onClick={() => void actOnTask(task.id, "skip")}>Skip task</Button>
    </>}
  </div>;
}

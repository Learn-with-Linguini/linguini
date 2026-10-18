import { InlineLoader } from "../components/LoadingScreen";
import { useEffect, useRef, useState, type ReactNode, type TouchEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { friendlyError, queryKeys } from "../lib/queryKeys";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { Button, Card, Feedback, IconButton, ProgressTrail, XpPill } from "../components/ui";
import { ArrowLeftIcon, ArrowRightIcon, CheckIcon, CloseIcon, EyeIcon, EyeOffIcon, SpeakerIcon } from "../components/icons";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { builtSentence, choiceOrder, finishesAfterLearning, markerChoices, optionText, practiceStages, questionOptions, sentenceEnding, taskDone, taskTitle, taskXp, xpEarnedText } from "../lib/practiceTasks";
import { speak } from "../lib/speech";
import { checkLessonAnswer, checkVocabularyAnswer, checkVocabularyTyping, getLatestAttempt, getLessonChecks, requestLessonAssistance, reviewDetails, updateMissionScenario, type GrammarLessonQuestion, type LessonAnswerCheck, type SceneObject, type SessionTask, type QuestionOutcome, type TaskActionResult, type TaskAnswer, type TaskContent, type VocabularyLearningWord } from "../lib/api";
import { mergeLessonChecks, visibleLessonQuestionIndex } from "../lib/missionLessonFlow";
import { isM06ScenarioVisible, lessonCheckFinished, nextAssistanceStep, retryTokens, unlockedRetryResumeIndex } from "../lib/missionM06";
import { ReportIssueLink } from "../components/ReportIssueLink";
import { ObjectPreview } from "../components/ObjectPreview";
import { ScenePhoto } from "../components/ScenePhoto";
import { useResolvedImageUrl } from "../components/SceneImage";
import { boardRows, squareCrop } from "../lib/practiceBoard";
import { questionMarkerObjects } from "../lib/missionMarkers";
import { completeSlot, speechAvailable, writtenPromptShown } from "../lib/missionA0";
import { fillMissionGap } from "../lib/missionGaps";
import { playAnswerSound } from "../lib/answerSound";

export function LearningTaskPage() {
  const { taskId } = useParams();
  const { session, completeSession, loadSession } = useAppState();
  const navigate = useNavigate();
  const scene = useScene();
  const base = `/practice/sessions/${scene.sessionId}`;
  if (!session) return null;
  if (session.session.status === "completed") return <Navigate to={`${base}/summary`} replace />;
  const tasks = practiceStages(session.tasks).learning;
  const index = tasks.findIndex(item => item.id === taskId);
  const task = tasks[index];
  if (!task || ["abandoned", "failed"].includes(session.session.status)) return <Navigate to={`${base}/learn`} replace />;
  const next = tasks[index + 1];
  const isVocabularyTask = task.kind === "vocabularyIntroduction";
  const skipM06RolePlay = () => {
    const lastM06Index = tasks.reduce(
      (last, item, taskIndex) => item.publicContent.missionId === "M06" ? taskIndex : last,
      -1,
    );
    const afterM06 = tasks[lastM06Index + 1];
    if (afterM06) {
      navigate(`${base}/learn/${afterM06.id}`);
    } else if (session.session.status !== "generatingTasks" && finishesAfterLearning(session.tasks)) {
      if (completeSession()) navigate(`${base}/summary`);
    } else {
      navigate(`${base}/ispy-1`);
    }
  };
  return <div className="stack learning-task-page"><LearningTaskContent key={task.id} task={task} index={index} total={tasks.length}
    onScenarioChange={() => loadSession(session.session.id)}
    onSkipRolePlay={skipM06RolePlay}
    onNext={() => {
      if (isVocabularyTask) {
        navigate(`${base}/learn`);
        return;
      }
      if (!next && session.session.status !== "generatingTasks" && finishesAfterLearning(session.tasks)) {
        if (completeSession()) navigate(`${base}/summary`);
        return;
      }
      navigate(next ? `${base}/learn/${next.id}` : session.session.status === "generatingTasks" ? `${base}/learn` : `${base}/ispy-1`);
    }} onClose={() => navigate(isVocabularyTask ? `${base}/learn/vocabulary-preview` : `${base}/learn`)} onExit={() => navigate("/home")} /></div>;
}

function LearningTaskContent({ task, index, total, onNext, onClose, onExit, onScenarioChange, onSkipRolePlay }: {
  task: SessionTask; index: number; total: number; onNext: () => void; onClose: () => void; onExit: () => void;
  onScenarioChange: () => Promise<unknown>; onSkipRolePlay: () => void;
}) {
  const lastStep = useLastStepLabel();
  const scene = useScene();
  const { actOnTask, practiceSaving, practiceError } = useAppState();
  const [text, setText] = useState("");
  const [choice, setChoice] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [answerCorrect, setAnswerCorrect] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(false);
  const [actionResult, setActionResult] = useState<TaskActionResult | null>(null);
  const request = useRef<{ answer: string; key: string } | null>(null);
  const busy = useRef(false);
  const content = task.publicContent;
  if (content.kind === "vocabularyIntroduction" && content.words.length) {
    return <VocabularyLearningFlow task={task} index={index} total={total} onNext={onNext} onClose={onClose} onExit={onExit} />;
  }
  if (content.kind === "grammarLesson") {
    return content.checkEachQuestion
      ? <SequentialGrammarLessonFlow task={task} index={index} total={total} onNext={onNext} onClose={onClose} onExit={onExit}
        onScenarioChange={onScenarioChange} onSkipRolePlay={onSkipRolePlay} />
      : <GrammarLessonFlow task={task} index={index} total={total} onNext={onNext} onClose={onClose} onExit={onExit} />;
  }
  const card = scene.items.find(item => item.id === task.sceneObjectId);
  const terminal = taskDone(task);
  const reading = ["vocabularyIntroduction", "grammarExplanation", "syntaxExplanation"].includes(task.kind);
  const submit = async () => {
    const answer: TaskAnswer | undefined = reading ? undefined : content.kind === "grammarPractice"
      ? { inputMode: "multipleChoice", optionId: choice } : { inputMode: "text", text };
    if (terminal || practiceSaving || busy.current || (!reading && !(content.kind === "grammarPractice" ? choice : text.trim()))) return;
    busy.current = true;
    setChecking(true);
    const identity = JSON.stringify(answer ?? {});
    if (request.current?.answer !== identity) request.current = { answer: identity, key: crypto.randomUUID() };
    try {
      const result = await actOnTask(task.id, reading ? "complete" : "attempts", answer, request.current.key);
      if (result) {
        request.current = null;
        setActionResult(result);
        if (reading) setFeedback("Task complete.");
        else {
          setFeedback(result.attempt?.feedback?.message ?? "Saved.");
          setAnswerCorrect(result.attempt?.isCorrect ?? null);
          if (result.attempt?.isCorrect != null) playAnswerSound(result.attempt.isCorrect);
        }
      }
    } finally {
      busy.current = false;
      setChecking(false);
    }
  };
  const reward = !terminal ? taskXp(task) : null;
  const earnedText = xpEarnedText(actionResult?.xpEarned);
  return <div className="stack">
    <div className="vocabulary-flow__progress"><ProgressTrail value={index + 1} total={total} label={`Task ${index + 1} of ${total}`} />{reward ? <XpPill {...reward} /> : null}</div>
    <div className="learning-title-row"><div className="vocabulary-flow__title"><IconButton className="vocabulary-flow__back" label="Back to tasks" onClick={onClose}><ArrowLeftIcon size={20} /></IconButton><h1>{taskTitle(task)}</h1></div><ExitToHome onExit={onExit} /></div>
    {card && content.kind === "vocabularyIntroduction" ? <div className="flashcard learning-card">
      <div className="spread"><span className="label muted">{card.wordClass}{card.gender ? " · " + card.gender : ""}</span>
        <IconButton label={"Hear " + card.word} onClick={() => speak(card.word, scene.languageCode)}><SpeakerIcon /></IconButton></div>
      <div className="learning-card__word"><h2>{card.word}</h2><p className="muted">{card.translation}</p></div>
    </div> : null}
    {!card && content.kind === "vocabularyIntroduction" ? <article className="flashcard learning-card">
      <div className="learning-card__word"><h2>{content.targetText}</h2><p>{content.translation}</p></div>
      <IconButton label={`Hear ${content.targetText ?? "word"}`} onClick={() => speak(content.targetText ?? "", scene.languageCode)}><SpeakerIcon /></IconButton>
    </article> : null}
    {content.kind === "grammarExplanation" || content.kind === "syntaxExplanation" ? <>
      <div className="panel-note">{content.explanation}</div>
      <Card plain><div className="stack-2">{content.kind === "syntaxExplanation" ? <strong>{content.sentencePattern}</strong> : null}{content.examples.map((example, i) => <p key={i}>{example}</p>)}</div></Card>
    </> : null}
    {"prompt" in content ? <p className="muted">{content.prompt}</p> : null}
    {content.kind === "grammarPractice" ? <div className="choice-grid">{choiceOrder(content.options, task.id, option => option).map(option => {
      const state = choice !== option ? "" : answerCorrect === null ? " choice--selected" : answerCorrect ? " choice--correct" : " choice--incorrect";
      return <button key={option} className={`choice${state}`} aria-pressed={choice === option} disabled={terminal || practiceSaving || checking || answerCorrect !== null} onClick={() => setChoice(option)}>{option}</button>;
    })}</div> : null}
    {content.kind === "sentenceBuilding" ? <><p>{content.sourceText}</p><div className="chip-row">{content.tokenBank.map((token, i) => <button key={i} className="chip" disabled={terminal || practiceSaving} onClick={() => setText(value => (value + " " + token).trim())}>{token}</button>)}</div></> : null}
    {!reading && content.kind !== "grammarPractice" ? <div className="field"><label className="field__label" htmlFor="task-answer">Your answer</label><input id="task-answer" className="input" value={text} maxLength={2000} disabled={terminal || practiceSaving} onChange={event => setText(event.target.value)} /></div> : null}
    {checking ? <InlineLoader compact label="Checking your answer…" /> : null}
    {feedback || earnedText ? <>
      <Feedback><div className="stack-2" role="status">{feedback ? <p>{feedback}</p> : null}{earnedText ? <strong>{earnedText}</strong> : null}</div></Feedback>
      <ReportIssueLink reportType={taskTitle(task)} fields={[
        ["Task ID", task.id],
        ["Prompt", "prompt" in content ? content.prompt : taskTitle(task)],
        ["Your answer", content.kind === "grammarPractice" ? choice : text],
        ["Displayed feedback", feedback],
        ["Language", scene.languageCode],
      ]} />
    </> : null}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    {terminal ? <Button block disabled={practiceSaving} onClick={onNext}>{index < total - 1 ? "Next task" : lastStep}</Button> : <>
      <Button block disabled={practiceSaving || checking || (!reading && !(content.kind === "grammarPractice" ? choice : text.trim()))} onClick={() => void submit()}>{reading ? "Mark complete" : "Submit answer"}</Button>
      <Button variant="quiet" block disabled={practiceSaving} onClick={async () => { if (await actOnTask(task.id, "skip")) onNext(); }}>Skip task</Button>
    </>}
  </div>;
}

function ExitToHome({ onExit }: { onExit: () => void }) {
  return <Button variant="quiet" className="learning-exit" onClick={onExit}><CloseIcon size={18} /> Exit</Button>;
}

function VocabularyLearningFlow({ task, index, total, onNext, onClose, onExit }: { task: SessionTask; index: number; total: number; onNext: () => void; onClose: () => void; onExit: () => void }) {
  const lastStep = useLastStepLabel();
  const scene = useScene();
  const { actOnTask, practiceSaving, practiceError, session } = useAppState();
  const [stage, setStage] = useState<"review" | "quiz" | "typing">("review");
  const [page, setPage] = useState(0);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [typingIndex, setTypingIndex] = useState(0);
  const [typedAnswers, setTypedAnswers] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<TaskActionResult | null>(null);
  const [questionResults, setQuestionResults] = useState<Record<string, boolean>>({});
  const [correctOptionIds, setCorrectOptionIds] = useState<Record<string, string>>({});
  const [checkingQuestion, setCheckingQuestion] = useState(false);
  const [pendingOptionId, setPendingOptionId] = useState<string | null>(null);
  const [checkingTyping, setCheckingTyping] = useState(false);
  const [typingCheck, setTypingCheck] = useState<{ isCorrect: boolean; correctAnswer: string; revealed: boolean } | null>(null);
  const requestKey = useRef(crypto.randomUUID());
  const swipeStart = useRef<{ x: number; y: number } | null>(null);
  const content = task.publicContent;
  if (content.kind !== "vocabularyIntroduction") return null;
  const terminal = taskDone(task);
  const pageCount = content.words.length;
  const visibleWords = content.words.slice(page, page + 1);
  const question = content.questions[questionIndex];
  const typingWord = content.words[typingIndex];
  const typingKey = typingWord ? typingWord.learningKey ?? typingWord.vocabularyItemId ?? typingWord.targetText : "";
  const reward = !terminal ? taskXp(task) : null;
  const earnedText = xpEarnedText(actionResult?.xpEarned);
  const submit = async () => {
    const result = await actOnTask(task.id, "attempts", { inputMode: "vocabularyReview", answers, typedAnswers }, requestKey.current);
    if (result) {
      setActionResult(result);
      setFeedback("Vocabulary practice saved.");
      setQuestionResults(reviewDetails(result.attempt)?.questionResults ?? {});
    }
  };
  const finishReview = () => page < pageCount - 1 ? setPage(value => value + 1) : setStage("quiz");
  const handleCardTouchStart = (event: TouchEvent) => {
    const touch = event.changedTouches[0];
    swipeStart.current = { x: touch.clientX, y: touch.clientY };
  };
  const handleCardTouchEnd = (event: TouchEvent) => {
    const start = swipeStart.current;
    swipeStart.current = null;
    if (!start) return;
    const touch = event.changedTouches[0];
    const horizontal = touch.clientX - start.x;
    const vertical = touch.clientY - start.y;
    if (Math.abs(horizontal) < 48 || Math.abs(horizontal) <= Math.abs(vertical)) return;
    if (horizontal < 0 && page < pageCount - 1) setPage(value => value + 1);
    if (horizontal > 0 && page > 0) setPage(value => value - 1);
  };
  const finishQuestion = () => questionIndex < content.questions.length - 1 ? setQuestionIndex(value => value + 1) : setStage("typing");
  const chooseAnswer = async (optionId: string) => {
    if (!question || answers[question.questionId] || checkingQuestion) return;
    if (question.correctOptionId) {
      const correct = question.correctOptionId === optionId;
      setAnswers(value => ({ ...value, [question.questionId]: optionId }));
      setQuestionResults(value => ({ ...value, [question.questionId]: correct }));
      setCorrectOptionIds(value => ({ ...value, [question.questionId]: question.correctOptionId! }));
      playAnswerSound(correct);
      return;
    }
    setCheckingQuestion(true);
    setPendingOptionId(optionId);
    try {
      const result = await checkVocabularyAnswer(task.id, question.questionId, optionId);
      setAnswers(value => ({ ...value, [question.questionId]: optionId }));
      setQuestionResults(value => ({ ...value, [question.questionId]: result.isCorrect }));
      setCorrectOptionIds(value => ({ ...value, [question.questionId]: result.correctOptionId }));
      playAnswerSound(result.isCorrect);
    } finally {
      setCheckingQuestion(false);
      setPendingOptionId(null);
    }
  };
  const checkTyping = async (reveal = false) => {
    if (!typingWord || checkingTyping) return;
    setCheckingTyping(true);
    try {
      const result = await checkVocabularyTyping(task.id, typingKey, typedAnswers[typingKey] ?? "", reveal);
      setTypingCheck(result);
      if (result.isCorrect) playAnswerSound(true);
    } catch (error) {
      setFeedback(friendlyError(error));
    } finally {
      setCheckingTyping(false);
    }
  };
  const advanceTyping = () => {
    setTypingCheck(null);
    if (typingIndex < content.words.length - 1) setTypingIndex(value => value + 1);
    else void submit();
  };
  return <div className="stack vocabulary-flow">
    <div className="vocabulary-flow__header">
      <div className="vocabulary-flow__progress"><ProgressTrail value={index + 1} total={total} label={`Task ${index + 1} of ${total}`} />{reward ? <XpPill {...reward} /> : null}</div>
      <div className="learning-title-row"><div className="vocabulary-flow__title"><IconButton className="vocabulary-flow__back" label="Back to tasks" onClick={onClose}><ArrowLeftIcon size={20} /></IconButton><h1>{content.title}</h1></div><ExitToHome onExit={onExit} /></div>
    </div>
    {!terminal && stage === "review" ? <>
      <div className="vocabulary-learning-grid vocabulary-learning-grid--swipe" onTouchStart={handleCardTouchStart} onTouchEnd={handleCardTouchEnd}>{visibleWords.map(word => <VocabularyLearningCard key={word.learningKey ?? word.vocabularyItemId ?? word.targetText} word={word} languageCode={scene.languageCode} />)}</div>
      <div className="vocabulary-flow__actions">
        <Button disabled={page === 0} onClick={() => setPage(value => value - 1)}><ArrowLeftIcon size={18} /> Previous</Button>
        <span className="vocabulary-flow__position" aria-live="polite">{page + 1} of {pageCount}</span>
        <Button variant="secondary" onClick={finishReview}>{page < pageCount - 1 ? <>Next <ArrowRightIcon /></> : "Start quick quiz"}</Button>
      </div>
      <Button variant="quiet" className="vocabulary-flow__skip" onClick={() => setStage("quiz")}>Skip word review</Button>
    </> : null}
    {!terminal && stage === "quiz" && question ? <><Card plain><div className="stack">
      <span className="label muted">Question {questionIndex + 1} of {content.questions.length}</span><h2>{question.prompt}</h2>
      <div className="choice-grid">{choiceOrder(question.options, `${task.id}:${question.questionId}`, option => option.optionId).map(option => {
        const selected = answers[question.questionId] === option.optionId || pendingOptionId === option.optionId;
        const result = questionResults[question.questionId];
        const isCorrectOption = correctOptionIds[question.questionId] === option.optionId;
        const state = result !== undefined && isCorrectOption ? " choice--correct"
          : !selected ? ""
            : result === undefined ? " choice--selected" : result ? " choice--correct" : " choice--incorrect";
        return <button key={option.optionId} className={`choice${state}`} aria-pressed={selected} disabled={!!answers[question.questionId] || checkingQuestion || !!feedback} onClick={() => void chooseAnswer(option.optionId)}>{option.label}</button>;
      })}</div>
      {checkingQuestion ? <InlineLoader compact label="Checking your answer…" /> : null}
      {answers[question.questionId] ? <>
        <Feedback tone={questionResults[question.questionId] ? "good" : "warn"}><p role="status">{questionResults[question.questionId] ? "Correct!" : (() => {
          const answer = question.options.find(option => option.optionId === correctOptionIds[question.questionId])?.label ?? "";
          return <>Incorrect. The correct answer is <strong>{answer}</strong>{answer ? sentenceEnding(answer) : ""}</>;
        })()}</p></Feedback>
      </> : null}
      <Button block disabled={!answers[question.questionId]} onClick={finishQuestion}>{questionIndex < content.questions.length - 1 ? "Next question" : "Continue"}</Button>
    </div></Card>{answers[question.questionId] ? <ReportIssueLink reportType="Vocabulary answer" fields={[
      ["Task ID", task.id],
      ["Question ID", question.questionId],
      ["Prompt", question.prompt],
      ["Your answer", question.options.find(option => option.optionId === answers[question.questionId])?.label],
      ["Displayed solution", question.options.find(option => option.optionId === correctOptionIds[question.questionId])?.label],
      ["Language", scene.languageCode],
    ]} /> : null}</> : null}
    {!terminal && stage === "typing" && typingWord ? <Card plain><div className="stack">
      <div><h2>Type “{typingWord.translation}”</h2><p className="muted">Word {typingIndex + 1} of {content.words.length}</p></div>
      <input className="input" aria-label={`Type ${typingWord.translation}`} value={typedAnswers[typingKey] ?? ""} disabled={typingCheck?.isCorrect || typingCheck?.revealed} onChange={event => { setTypedAnswers(value => ({ ...value, [typingKey]: event.target.value })); setTypingCheck(null); }} />
      {checkingTyping ? <InlineLoader compact label="Checking your word…" /> : null}
      {typingCheck ? <Feedback tone={typingCheck.isCorrect ? "good" : typingCheck.revealed ? "neutral" : "warn"}><p role="status">{typingCheck.isCorrect ? "That’s right!" : typingCheck.revealed ? <>No worries, the answer is <strong>{typingCheck.correctAnswer}</strong>.</> : "Not quite. Give it another try."}</p></Feedback> : null}
      {typingCheck?.isCorrect || typingCheck?.revealed
        ? <Button block disabled={practiceSaving} onClick={advanceTyping}>{typingIndex < content.words.length - 1 ? "Next word" : "Finish task"}</Button>
        : <Button block disabled={!typedAnswers[typingKey]?.trim() || practiceSaving || checkingTyping} onClick={() => void checkTyping()}>Check answer</Button>}
      {!typingCheck?.isCorrect && !typingCheck?.revealed ? <Button variant="quiet" block className="typing-forgot-action" disabled={practiceSaving || checkingTyping} onClick={() => void checkTyping(true)}>I forgot, lift the lid</Button> : null}
    </div></Card> : null}
    {feedback || earnedText ? <Feedback><div className="stack-2" role="status">{feedback ? <p>{feedback}</p> : null}{earnedText ? <strong>{earnedText}</strong> : null}</div></Feedback> : null}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    {terminal ? <Button block onClick={onNext}>{session?.session.status === "generatingTasks" ? "Back to tasks" : index < total - 1 ? "Next task" : lastStep}</Button> : null}
  </div>;
}

function MissionSnapshotFacts({ task, scene }: { task: SessionTask; scene: ReturnType<typeof useScene> }) {
  const content = task.publicContent;
  if (content.kind !== "grammarLesson" || !content.missionSnapshot) return null;
  const snapshot = content.missionSnapshot;
  const objectLabel = (id?: string | null) => scene.items.find(item => item.id === id)?.translation ?? id;
  const focus = snapshot.ownedObjectId ?? snapshot.chosenObjectId ?? snapshot.preferenceObjectIds?.[0];
  return <section className="mission-planning-facts" aria-label="Your mission facts">
    <strong>{focus ? `Your choice: ${objectLabel(focus)}` : "Your choice"}</strong>
    <ul>
      {focus ? <li>{snapshot.missionId === "M04" ? "It's yours." : "You chose this object."}</li> : null}
      {snapshot.pretend ? <li>It's pretend</li> : null}
      {snapshot.reaction ? <li>You {snapshot.reaction === "like" ? "like" : "don't like"} it</li> : null}
      {snapshot.taughtChunks.slice(0, 3).map(chunk => <li key={chunk.text}>
        <span lang={scene.languageCode}>{chunk.text}</span> — {chunk.translation}
      </li>)}
    </ul>
  </section>;
}

function MissionGapIcon({ kind }: { kind: NonNullable<GrammarLessonQuestion["optionIcons"]>[string] }) {
  const icon = kind === "belongs" ? "✓" : kind === "likes" || kind === "like" ? "♥" : "♡";
  const label = kind === "belongs" ? "belongs" : kind === "likes" || kind === "like" ? "likes" : "does not like";
  return <span className="mission-gap__icon" aria-label={label}>{icon}</span>;
}

function LessonAudioPrompt({ question, languageCode, revealed, graded, onReveal, showAudioText = false }: {
  question: GrammarLessonQuestion;
  languageCode: string;
  revealed: boolean;
  graded: boolean;
  onReveal: () => void;
  showAudioText?: boolean;
}) {
  const audio = speechAvailable();
  const written = writtenPromptShown(question, { revealed, graded, audio });
  if (!question.audioText) return null;
  return <>
    {audio ? <div className="lesson-audio">
      <IconButton label={question.listenFirst ? "Play the word" : `Hear ${question.audioText}`}
        onClick={() => speak(question.audioText ?? "", languageCode)}><SpeakerIcon /></IconButton>
      {question.listenFirst && !written
        ? <Button variant="quiet" onClick={onReveal}>Show the written word</Button> : null}
    </div> : null}
    {question.listenFirst && !audio
      ? <p className="small muted" role="note">Audio isn't available here, so read the word instead.</p> : null}
    {showAudioText && written ? <p lang={languageCode}>{question.audioText}</p> : null}
  </>;
}

function A0MissionGapQuestion({ question, scene, sceneObjects, selectedOptionId, typedMode,
  typedAnswer, checked, retryPassed, checking, scenario, onSelect, onTypedMode, onTypedAnswer, onRetry }: {
  question: GrammarLessonQuestion;
  scene: ReturnType<typeof useScene>;
  sceneObjects: SceneObject[];
  selectedOptionId: string;
  typedMode: boolean;
  typedAnswer: string;
  checked?: LessonAnswerCheck;
  retryPassed: boolean;
  checking: boolean;
  scenario?: string;
  onSelect: (optionId: string) => void;
  onTypedMode: () => void;
  onTypedAnswer: (value: string) => void;
  onRetry: (optionId: string, correct: boolean) => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const solution = checked
    ? question.options.find(option => option.label === checked.correctAnswer)
    : undefined;
  const correctAnswer = solution?.label ?? checked?.correctAnswer ?? "";
  const selected = question.options.find(option => option.optionId === selectedOptionId);
  const displayedChunk = checked && !checked.isCorrect ? solution?.label ?? checked.correctAnswer ?? ""
    : checked ? selected?.label ?? solution?.label ?? checked.correctAnswer ?? ""
      : selected?.label ?? (typedMode ? typedAnswer : "");
  const completed = checked && !checked.isCorrect
    ? question.completeChunk ?? (question.slotTemplate ? fillMissionGap(question.slotTemplate, solution?.label ?? checked.correctAnswer ?? "") : solution?.label)
    : question.completeChunk ?? (question.slotTemplate ? fillMissionGap(question.slotTemplate, displayedChunk || "___") : displayedChunk);
  const showRetry = Boolean(checked && !checked.isCorrect);
  const correctOptionId = solution?.optionId;
  const dialogue = question.dialogue ?? [];
  return <section className="mission-gap" aria-label="Complete the phrase">
    {question.sceneObjectId ? <ObjectPreview scene={scene}
      object={sceneObjects.find(item => item.id === question.sceneObjectId)}
      label={question.objectLabel ?? ""} /> : null}
    {scenario ? <div className="roleplay-premise" role="note">
      <p className="roleplay-premise__text"><strong>Scenario:</strong> {roleplayScenario(scenario)}</p>
    </div> : null}
    <LessonAudioPrompt question={question} languageCode={scene.languageCode} revealed={revealed}
      graded={Boolean(checked)} onReveal={() => setRevealed(true)} showAudioText />
    {question.translation
      ? <PromptTranslation source={question.prompt} text={question.translation} lang={scene.languageCode} />
      : <h2>{question.prompt}</h2>}
    {dialogue.length ? <div className="mission-dialogue" aria-label="Dialogue">
      {dialogue.map((turn, index) => <div className={`mission-dialogue__turn mission-dialogue__turn--${turn.speaker}`} key={`${turn.speaker}-${index}`}>
        <strong>{turn.speaker === "linguini" ? "Linguini" : "You"}</strong>
        <p lang={scene.languageCode}><MissionGapText template={turn.text} chunk={displayedChunk} /></p>
        {turn.translation ? <p className="muted small">{turn.translation}</p> : null}
      </div>)}
    </div> : question.slotTemplate ? <p className="mission-gap__sentence" lang={scene.languageCode}>
      <MissionGapText template={question.slotTemplate} chunk={displayedChunk} />
    </p> : null}
    {question.typedAllowed ? <div className="stack-2">
      <Button variant="quiet" disabled={Boolean(checked) || checking} onClick={onTypedMode}>
        {typedMode ? "Choose an answer instead" : "Type it instead"}
      </Button>
      {typedMode ? <input className="input" aria-label="Type the missing words" value={typedAnswer}
        disabled={Boolean(checked) || checking} onChange={event => onTypedAnswer(event.target.value)} /> : null}
    </div> : null}
    <div className={`choice-grid${question.gapType === "pictureToBlank" ? " mission-gap__pictures" : ""}`}>
      {question.options.map(option => {
        const object = sceneObjects.find(item => item.id === question.optionObjectIds?.[option.optionId]);
        const isSelected = selectedOptionId === option.optionId;
        const isCorrect = checked ? correctOptionId === option.optionId : false;
        const state = isCorrect ? " choice--correct"
          : isSelected && checked && !checked.isCorrect ? " choice--incorrect"
            : isSelected && !checked ? " choice--selected" : "";
        return <button key={option.optionId} type="button" className={`choice${state}`}
          aria-pressed={isSelected} disabled={checking || Boolean(checked?.isCorrect)}
          onClick={() => showRetry ? onRetry(option.optionId, option.optionId === correctOptionId) : onSelect(option.optionId)}>
          {question.optionIcons?.[option.optionId] ? <MissionGapIcon kind={question.optionIcons[option.optionId]} /> : null}
          {question.gapType === "pictureToBlank" && object
            ? <ObjectPreview scene={scene} object={object} label={option.label} />
            : optionText(question, option.label)}
        </button>;
      })}
    </div>
    {checked ? <Feedback tone={checked.isCorrect || retryPassed ? "good" : "warn"}>
      <p role="status">{checked.isCorrect ? question.correctNote ?? "Correct!" : retryPassed
        ? "That's right. Try the phrase again."
        : <>Not quite. The correct answer is <strong>{correctAnswer}</strong>{sentenceEnding(correctAnswer)}</>}</p>
    </Feedback> : null}
    {checked ? <div className="mission-gap__completion">
      <p>Complete: <strong lang={scene.languageCode}>{completed}</strong></p>
      {question.completeTranslation ? <PromptTranslation text={question.completeTranslation} /> : null}
      {completed && speechAvailable() ? <IconButton label={`Hear ${completed}`} onClick={() => speak(completed, scene.languageCode)}><SpeakerIcon /></IconButton> : null}
    </div> : null}
    {checked && (checked.isCorrect || retryPassed) && question.outcome ? <div className="mission-outcome" role="status">
      <strong>{question.outcome.kind === "leftBehind" ? <CloseIcon size={18} /> : <CheckIcon size={18} />}
        {question.outcome.kind === "returned" ? " Returned to you. " : question.outcome.kind === "basket" ? " Into the picnic basket. " : " Left behind. "}
        {question.outcome.text}</strong>
    </div> : null}
    {showRetry && !retryPassed ? <p className="small muted">Tap the correct answer to try the phrase again.</p> : null}
  </section>;
}

function MissionGapText({ template, chunk }: { template: string; chunk: string }) {
  if (!template.includes("___")) return <>{template}</>;
  const [before = "", after = ""] = template.split("___", 2);
  return <>{before}<strong className="mission-gap__filled">{chunk || "___"}</strong>{after}</>;
}

type GrammarLessonContent = Extract<TaskContent, { kind: "grammarLesson" }>;

function SequentialGrammarLessonFlow({ task, index, total, onNext, onClose, onExit, onScenarioChange, onSkipRolePlay }: {
  task: SessionTask; index: number; total: number; onNext: () => void; onClose: () => void; onExit: () => void;
  onScenarioChange: () => Promise<unknown>; onSkipRolePlay: () => void;
}) {
  const lastStep = useLastStepLabel();
  const scene = useScene();
  const { actOnTask, practiceSaving, practiceError, session } = useAppState();
  const [contentOverride, setContentOverride] = useState<GrammarLessonContent | null>(null);
  const content = contentOverride ?? task.publicContent;
  const questions = content.kind === "grammarLesson" ? content.questions : [];
  const isM06 = content.kind === "grammarLesson" && content.missionId === "M06";
  const { refetch: refetchChecks, ...saved } = useQuery({
    queryKey: queryKeys.lessonChecks(task.id),
    queryFn: ({ signal }) => getLessonChecks(task.id, signal),
    enabled: content.kind === "grammarLesson" && content.checkEachQuestion === true,
  });
  const [localChecks, setLocalChecks] = useState<Record<string, LessonAnswerCheck>>({});
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [typedMode, setTypedMode] = useState<Record<string, boolean>>({});
  const [typedAnswers, setTypedAnswers] = useState<Record<string, string>>({});
  const [retryPassed, setRetryPassed] = useState<Record<string, boolean>>({});
  const [builtTokenIndexes, setBuiltTokenIndexes] = useState<Record<string, number[]>>({});
  const [retryReady, setRetryReady] = useState<Record<string, boolean>>({});
  const [revealedPrompts, setRevealedPrompts] = useState<Record<string, boolean>>({});
  const [assistanceContent, setAssistanceContent] = useState<Record<string, string>>({});
  const [assistanceSteps, setAssistanceSteps] = useState<Record<string, string[]>>({});
  const [activeIndex, setActiveIndex] = useState(0);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<TaskActionResult | null>(null);
  const submitKey = useRef(crypto.randomUUID());
  const playedCheck = useRef("");
  const checks = mergeLessonChecks(saved.data?.checks ?? [], localChecks);
  useEffect(() => {
    if (saved.data) setAssistanceSteps(saved.data.assistanceSteps ?? {});
  }, [saved.data]);
  useEffect(() => {
    if (saved.data) {
      const restored = mergeLessonChecks(saved.data.checks, {});
      setActiveIndex(isM06
        ? unlockedRetryResumeIndex(questions, restored)
        : visibleLessonQuestionIndex(questions.map(item => item.questionId), restored));
    }
  }, [saved.data, questions, isM06]);
  useEffect(() => {
    setContentOverride(null);
  }, [task.id]);
  const question = questions[Math.min(activeIndex, questions.length - 1)];
  const storedCheck = question ? checks[question.questionId] : undefined;
  const retrying = question ? Boolean(retryReady[question.questionId]) : false;
  const isSituation = content.kind === "grammarLesson" && Boolean(content.missionSnapshot);
  const tokenIndexes = question ? builtTokenIndexes[question.questionId] ?? [] : [];
  const tokenAnswer = question?.interactionType === "sentenceBuilding"
    ? builtSentence(tokenIndexes.map(position => question.tokenBank[position])) : "";
  const answer = question?.typedAllowed && typedMode[question.questionId]
    ? typedAnswers[question.questionId] ?? ""
    : question?.interactionType === "multipleChoice" || question?.interactionType === "textCloze"
      ? answers[question.questionId] ?? "" : tokenAnswer;
  const allChecked = questions.every(item => {
    const check = checks[item.questionId];
    return lessonCheckFinished(check, item.allowRetry);
  });
  const isChecked = Boolean(storedCheck && !retrying);
  const terminal = taskDone(actionResult?.task ?? task);
  const reward = !terminal ? taskXp(task) : null;
  const earnedText = xpEarnedText(actionResult?.xpEarned);
  const questionObjects = question?.groupObjectIds
    ?.map(id => scene.items.find(item => item.id === id))
    .filter((item): item is NonNullable<typeof item> => Boolean(item)) ?? [];
  const markers = question ? markerChoices(question, scene) : [];
  const showWritten = question ? writtenPromptShown(question, {
    revealed: Boolean(revealedPrompts[question.questionId]),
    graded: Boolean(storedCheck),
    audio: speechAvailable(),
  }) : true;
  const usedAssistance = question
    ? assistanceSteps[question.questionId] ?? storedCheck?.assistanceStepsUsed ?? []
    : [];
  const assistanceStep = question
    ? nextAssistanceStep(question.assistanceSteps, usedAssistance)
    : null;
  const slotFill = question?.interactionType === "multipleChoice"
    ? question.options.find(option => option.optionId === answer)?.label ?? ""
    : answer;
  const slotText = question?.slotTemplate && ["functionalChunk", "detailGap"].includes(question.gapKind ?? "")
    ? completeSlot(question.slotTemplate, isChecked
      ? (storedCheck?.correctAnswer ?? answer)
      : slotFill || "___")
    : question?.slotTemplate;

  useEffect(() => {
    if (!isSituation || !question || !checks[question.questionId]) return;
    const checkedAnswer = checks[question.questionId];
    const key = `${question.questionId}:${checkedAnswer.answer}`;
    if (playedCheck.current === key) return;
    playedCheck.current = key;
    const solution = question.options.find(option => option.label === checkedAnswer.correctAnswer)?.label
      ?? checkedAnswer.correctAnswer ?? "";
    const chunk = checkedAnswer.isCorrect
      ? question.options.find(option => option.optionId === checkedAnswer.answer)?.label ?? solution
      : solution;
    const completed = question.completeChunk ?? (question.slotTemplate
      ? fillMissionGap(question.slotTemplate, chunk) : chunk);
    speak(checkedAnswer.isCorrect ? completed : question.audioText ?? completed, scene.languageCode);
  }, [checks, isSituation, question, scene.languageCode]);
  if (content.kind !== "grammarLesson") return null;

  const check = async () => {
    if (!question || !answer || checking || saved.isLoading) return;
    setChecking(true);
    setCheckError(null);
    try {
      const result = await checkLessonAnswer(task.id, question.questionId, answer);
      setLocalChecks(value => ({ ...value, [result.questionId]: result }));
      setRetryReady(value => ({ ...value, [result.questionId]: false }));
      playAnswerSound(result.isCorrect);
    } catch (error) {
      setCheckError(friendlyError(error));
    } finally {
      setChecking(false);
    }
  };

  const retry = () => {
    if (!question || !storedCheck) return;
    if (question.interactionType === "sentenceBuilding" && storedCheck.wrongField) {
      const fields = question.wrongFieldTokens ?? {};
      setBuiltTokenIndexes(value => {
        const selected = value[question.questionId] ?? [];
        const preserved = new Set(retryTokens(
          selected.map(position => question.tokenBank[position]),
          storedCheck.wrongField,
          fields,
        ));
        return {
          ...value,
          [question.questionId]: selected.filter(position => preserved.has(question.tokenBank[position])),
        };
      });
    }
    setRetryReady(value => ({ ...value, [question.questionId]: true }));
  };

  const requestHelp = async () => {
    if (!question || !assistanceStep || checking) return;
    setChecking(true);
    setCheckError(null);
    try {
      const result = await requestLessonAssistance(task.id, question.questionId, assistanceStep as Parameters<typeof requestLessonAssistance>[2]);
      setAssistanceContent(value => ({ ...value, [question.questionId]: result.content }));
      setAssistanceSteps(value => ({
        ...value, [question.questionId]: [...usedAssistance, result.step],
      }));
    } catch (error) {
      setCheckError(friendlyError(error));
    } finally {
      setChecking(false);
    }
  };

  const scenarioAction = async (action: "accept" | "choose", sceneObjectId?: string) => {
    setChecking(true);
    setCheckError(null);
    try {
      const result = await updateMissionScenario(task.id, action, sceneObjectId);
      const updated = result.tasks.find(item => item.id === task.id)?.publicContent;
      await onScenarioChange();
      if (updated?.kind === "grammarLesson") setContentOverride(updated);
    } catch (error) {
      setCheckError(friendlyError(error));
    } finally {
      setChecking(false);
    }
  };

  const skipRolePlay = async () => {
    const m06Tasks = session?.tasks.filter(item => item.publicContent.missionId === "M06") ?? [task];
    for (const item of m06Tasks) {
      if (!taskDone(item)) await actOnTask(item.id, "skip");
    }
    onSkipRolePlay();
  };

  const submit = async () => {
    if (!allChecked || practiceSaving || checking) return;
    setChecking(true);
    setCheckError(null);
    const lockedAnswers = Object.fromEntries(content.questions.map(item => [
      item.questionId, checks[item.questionId].answer,
    ]));
    try {
      const result = await actOnTask(task.id, "attempts", {
        inputMode: "vocabularyReview", answers: lockedAnswers, typedAnswers: {},
      }, submitKey.current);
      if (result) setActionResult(result);
    } catch (error) {
      setCheckError(friendlyError(error));
    } finally {
      setChecking(false);
    }
  };

  return <div className="stack vocabulary-flow">
    <div className="vocabulary-flow__progress"><ProgressTrail value={index + 1} total={total} label={`Task ${index + 1} of ${total}`} />{reward ? <XpPill {...reward} /> : null}</div>
    <div className="learning-title-row"><div className="vocabulary-flow__title"><IconButton className="vocabulary-flow__back" label="Back to tasks" onClick={onClose}><ArrowLeftIcon size={20} /></IconButton><h1>{content.title}</h1></div><ExitToHome onExit={onExit} /></div>
    {saved.isLoading ? <InlineLoader compact label="Restoring checked answers…" /> : null}
    {saved.isError ? <div role="alert"><p>Unable to restore checked answers.</p>
      <Button variant="quiet" onClick={() => void refetchChecks()}>Retry</Button></div> : null}
    {question ? <div className="learning-section">
      {question.section ? <h2 className="learning-section__title">{question.section}</h2> : null}
      {isM06 && activeIndex === 0 && isM06ScenarioVisible(content.missionId, content.scenario) ? <Card plain>
        <section className="mission-scenario" aria-label="Choose your role-play">
          <div><strong>{content.scenario?.itemLabel}</strong><p>{content.scenario?.prompt}</p></div>
          <Button variant="secondary" disabled={checking} onClick={() => void scenarioAction("accept")}>Accept</Button>
          {content.scenario?.alternatives.map(alternative => <Button key={alternative.sceneObjectId}
            variant="quiet" disabled={checking}
            onClick={() => void scenarioAction("choose", alternative.sceneObjectId)}>
            Choose {alternative.label}
          </Button>)}
          <Button variant="quiet" disabled={checking || practiceSaving} onClick={() => void skipRolePlay()}>
            Skip role-play
          </Button>
        </section>
      </Card> : null}
      <Card plain><div className="stack">
        <span className="label muted">Question {activeIndex + 1} of {content.questions.length}</span>
        {question.dialogue?.length ? <div className="mission-dialogue" aria-label="Conversation so far">
          {question.dialogue.map((turn, turnIndex) => <p key={`${turn.speaker}-${turnIndex}`}
            className={`mission-dialogue__turn mission-dialogue__turn--${turn.speaker}`}>
            <strong>{turn.speaker === "server" ? "Server" : "You"}</strong>
            <span>{turn.text}</span>
          </p>)}
        </div> : null}
        {question.planningFacts?.length ? <section className="mission-planning-facts" aria-label="Your facts">
          <strong>Your facts</strong><ul>{question.planningFacts.map((fact, position) => <li key={`${position}-${fact}`}>{fact}</li>)}</ul>
        </section> : null}
        <MissionSnapshotFacts task={task} scene={scene} />
        {isSituation && question.gapType ? <A0MissionGapQuestion key={question.questionId}
          question={question} scene={scene} sceneObjects={session?.sceneObjects ?? []}
          selectedOptionId={answers[question.questionId] ?? ""}
          typedMode={Boolean(typedMode[question.questionId])}
          typedAnswer={typedAnswers[question.questionId] ?? ""}
          checked={checks[question.questionId]} retryPassed={Boolean(retryPassed[question.questionId])}
          checking={checking || saved.isLoading || saved.isError}
          scenario={question.roleplayPremise}
          onSelect={optionId => {
            setTypedMode(value => ({ ...value, [question.questionId]: false }));
            setAnswers(value => ({ ...value, [question.questionId]: optionId }));
          }}
          onTypedMode={() => setTypedMode(value => ({ ...value, [question.questionId]: !value[question.questionId] }))}
          onTypedAnswer={value => setTypedAnswers(current => ({ ...current, [question.questionId]: value }))}
          onRetry={(optionId, correct) => {
            setRetryPassed(value => ({ ...value, [question.questionId]: correct }));
            setAnswers(value => ({ ...value, [question.questionId]: optionId }));
          }}
        /> : <>
        {markers.length || questionObjects.length ? <div className="mission-markers"><ScenePhoto
          scene={scene} hideWords items={markers.length ? markers.map(marker => marker.item) : questionObjects}
          activeItemId={markers.find(marker => marker.option.optionId === (checks[question.questionId]?.isCorrect
            ? checks[question.questionId]?.answer
            : question.options.find(option => option.label === checks[question.questionId]?.correctAnswer)?.optionId))?.item.id ?? null}
          onMarkerClick={!isChecked && !checking && markers.length
            ? item => {
              const marker = markers.find(candidate => candidate.item.id === item.id);
              if (marker) setAnswers(value => ({ ...value, [question.questionId]: marker.option.optionId }));
            } : undefined}
        /></div> : null}
        {question.roleplayPremise ? <div className="roleplay-premise" role="note" aria-label={`Scenario: ${roleplayScenario(question.roleplayPremise)}`}>
          <p className="roleplay-premise__text"><strong>Scenario:</strong> {roleplayScenario(question.roleplayPremise)}</p>
        </div> : null}
        {question.audioText && speechAvailable() ? <div className="spread">
          <p className="muted">{question.listenFirst && !showWritten ? "Listen before reading the prompt." : "Listen to the phrase."}</p>
          <IconButton label="Play audio" onClick={() => speak(question.audioText ?? "", scene.languageCode)}><SpeakerIcon /></IconButton>
        </div> : null}
        {question.audioText && !speechAvailable() ? <>
          <p className="small muted" role="note">Audio isn't available here, so read the phrase instead.</p>
          <p lang={scene.languageCode}>{question.audioText}</p>
        </> : null}
        {question.listenFirst && !showWritten ? <Button variant="quiet" onClick={() => setRevealedPrompts(value => ({
          ...value, [question.questionId]: true,
        }))}>Show written prompt</Button> : null}
        {showWritten ? question.translation
          ? <PromptTranslation source={question.prompt} text={question.translation} lang={scene.languageCode} />
          : <h2>{question.prompt}</h2> : null}
        {slotText && showWritten ? <p className="mission-slot-template">
          {slotText}
        </p> : null}
        {question.interactionType === "sentenceBuilding" ? <>
          <div className="sentence-builder__answer" aria-label="Your sentence">
            {tokenIndexes.length ? tokenIndexes.map((tokenIndex, position) => <button key={`${tokenIndex}-${position}`}
              className="sentence-builder__token" disabled={isChecked || checking}
              onClick={() => setBuiltTokenIndexes(value => ({
                ...value, [question.questionId]: (value[question.questionId] ?? []).filter((_, itemIndex) => itemIndex !== position),
              }))}>{question.tokenBank[tokenIndex]}</button>) : <span className="muted">Choose the words to build your sentence.</span>}
          </div>
          <div className="chip-row" aria-label="Sentence building words">{question.tokenBank.map((token, tokenIndex) => {
            const used = tokenIndexes.includes(tokenIndex);
            return <button key={`${token}-${tokenIndex}`} className="chip" disabled={used || isChecked || checking}
              onClick={() => setBuiltTokenIndexes(value => ({
                ...value, [question.questionId]: [...(value[question.questionId] ?? []), tokenIndex],
              }))}>{token}</button>;
          })}</div>
        </> : question.interactionType === "textCloze" ? <div className="field">
          <label className="field__label" htmlFor={`mission-answer-${question.questionId}`}>Your reply</label>
          <input id={`mission-answer-${question.questionId}`} className="input"
            placeholder={question.slotTemplate ?? ""}
            value={answers[question.questionId] ?? ""}
            disabled={isChecked || checking || saved.isLoading || saved.isError}
            onChange={event => setAnswers(value => ({ ...value, [question.questionId]: event.target.value }))} />
        </div> : <div className="choice-grid">{questionOptions(question, `${task.id}:${question.questionId}`).map(option => {
          const result = checks[question.questionId];
          const situationRetrying = Boolean(isSituation && result && !result.isCorrect);
          const selected = answers[question.questionId] === option.optionId || result?.answer === option.optionId;
          const correct = situationRetrying ? result?.correctAnswer === option.label : result?.isCorrect && selected;
          const incorrect = result && !result.isCorrect && !situationRetrying && selected;
          const state = correct ? " choice--correct" : incorrect ? " choice--incorrect" : selected ? " choice--selected" : "";
          return <button key={option.optionId} className={`choice${state}`} aria-pressed={selected}
            disabled={(isSituation
              ? Boolean(result?.isCorrect) || Boolean(retryPassed[question.questionId])
              : Boolean(result) && !retrying) || checking || saved.isLoading || saved.isError}
            onClick={() => {
              if (situationRetrying) {
                setAnswers(value => ({ ...value, [question.questionId]: option.optionId }));
                setRetryPassed(value => ({ ...value, [question.questionId]: option.label === result?.correctAnswer }));
              } else {
                setAnswers(value => ({ ...value, [question.questionId]: option.optionId }));
              }
            }}>
            {isSituation && question.optionIcons?.[option.optionId]
              ? <MissionGapIcon kind={question.optionIcons[option.optionId]} /> : null}
            {optionText(question, option.label)}</button>;
        })}</div>}
        {storedCheck && !retrying ? <>
          <Feedback tone={storedCheck.isCorrect || (isSituation && Boolean(retryPassed[question.questionId])) ? "good" : "warn"}>
            <p role="status">{storedCheck.isCorrect
              ? question.correctNote ?? "Correct!"
              : isSituation && retryPassed[question.questionId]
                ? "That's right. Try the phrase again."
                : isSituation
                  ? <>Not quite. The correct answer is <strong>{storedCheck.correctAnswer}</strong>{sentenceEnding(storedCheck.correctAnswer ?? "")} Tap it to try again.</>
                  : storedCheck.attemptsLeft
                    ? storedCheck.feedback ?? "Not quite. Try another answer."
                    : <>Not quite. The correct answer is <strong>{storedCheck.correctAnswer}</strong>{sentenceEnding(storedCheck.correctAnswer ?? "")}</>}</p>
          </Feedback>
          {storedCheck.isCorrect || !storedCheck.attemptsLeft
            ? <QuestionOutcomeNotes outcome={storedCheck.outcome} /> : null}
          {isM06 && !storedCheck.isCorrect && (storedCheck.attemptsLeft ?? 0) > 0
            ? <Button variant="secondary" onClick={retry}>Try again</Button> : null}
        </> : null}
        {assistanceContent[question.questionId] ? <Feedback>
          <p role="status">{assistanceContent[question.questionId]}</p>
        </Feedback> : null}
        {isM06 && assistanceStep && !terminal
          && !(storedCheck && (storedCheck.isCorrect || storedCheck.attemptsLeft === 0))
          ? <Button variant="quiet" disabled={checking || practiceSaving}
          onClick={() => void requestHelp()}>
          Need help? {assistanceStep === "replayAudio" ? "Replay audio"
            : assistanceStep === "visualDetail" ? "See a visual detail"
              : assistanceStep === "phraseOnset" ? "Get the phrase opening"
                : assistanceStep === "chunkBank" ? "Show a chunk bank" : "Show the full model"}
        </Button> : null}
        </>}
      </div></Card>
      {storedCheck && (!storedCheck.isCorrect || storedCheck.correctAnswer) ? <ReportIssueLink reportType="Grammar answer" fields={[
        ["Task ID", task.id], ["Question ID", question.questionId], ["Prompt", question.prompt],
        ["Your answer", storedCheck.answer], ["Displayed solution", storedCheck.correctAnswer],
      ]} /> : null}
    </div> : null}
    {checking ? <InlineLoader compact label="Checking your answer…" /> : null}
    {checkError ? <p role="alert">{checkError}</p> : null}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    {earnedText ? <Feedback><p role="status">{earnedText}</p></Feedback> : null}
    {terminal ? <Button block onClick={onNext}>{index < total - 1 ? "Next task" : lastStep}</Button>
      : question && !isChecked
        ? <Button block disabled={!answer || checking || saved.isLoading || saved.isError || practiceSaving}
          onClick={() => void check()}>{retrying ? "Check again" : "Check answer"}</Button>
      : question && activeIndex < content.questions.length - 1
        ? <Button block disabled={checking || practiceSaving || (isSituation && !checks[question.questionId]?.isCorrect && !retryPassed[question.questionId])}
          onClick={() => setActiveIndex(activeIndex + 1)}>Next question</Button>
        : <Button block disabled={!allChecked || checking || practiceSaving || (isSituation && !checks[question?.questionId ?? ""]?.isCorrect && !retryPassed[question?.questionId ?? ""])}
          onClick={() => void submit()}>Finish task</Button>}
    {!terminal ? <Button variant="quiet" block disabled={practiceSaving || checking}
      onClick={async () => { if (await actOnTask(task.id, "skip")) onNext(); }}>Skip task</Button> : null}
  </div>;
}

function GrammarLessonFlow({ task, index, total, onNext, onClose, onExit }: { task: SessionTask; index: number; total: number; onNext: () => void; onClose: () => void; onExit: () => void }) {
  const lastStep = useLastStepLabel();
  const scene = useScene();
  const { actOnTask, practiceSaving, practiceError, session } = useAppState();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [builtTokenIndexes, setBuiltTokenIndexes] = useState<Record<string, number[]>>({});
  const [questionResults, setQuestionResults] = useState<Record<string, boolean>>({});
  const [correctAnswers, setCorrectAnswers] = useState<Record<string, string>>({});
  const [outcomes, setOutcomes] = useState<Record<string, QuestionOutcome>>({});
  const [feedback, setFeedback] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<TaskActionResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const [activeIndex, setActiveIndex] = useState(0);
  const [checkError, setCheckError] = useState<string | null>(null);
  const requestKey = useRef(crypto.randomUUID());
  const content = task.publicContent;
  const audio = speechAvailable();
  const { resolvedUrl: sceneImageUrl } = useResolvedImageUrl(scene.imageUrl);
  const [boardImageSize, setBoardImageSize] = useState<{ width: number; height: number } | null>(null);
  const savedChecks = useQuery({
    queryKey: queryKeys.lessonChecks(task.id),
    queryFn: ({ signal }) => getLessonChecks(task.id, signal),
    enabled: content.kind === "grammarLesson" && task.status !== "completed",
  });
  const restorable = content.kind === "grammarLesson" && Boolean(content.missionId) && task.status === "completed";
  const saved = useQuery({
    queryKey: queryKeys.latestAttempt(task.id),
    queryFn: ({ signal }) => getLatestAttempt(task.id, signal),
    enabled: restorable && !Object.keys(questionResults).length,
  }).data?.attempt;
  const terminal = taskDone(task);
  const reward = !terminal ? taskXp(task) : null;
  const earnedText = xpEarnedText(actionResult?.xpEarned);
  const restored = !Object.keys(questionResults).length && saved?.reviewDetails ? saved : null;
  const results = restored?.reviewDetails?.questionResults ?? questionResults;
  const solutions = restored?.reviewDetails?.correctAnswers ?? correctAnswers;
  const outcomeFor: Record<string, QuestionOutcome> = restored
    ? Object.fromEntries((restored.reviewDetails?.questionOutcomes ?? []).map(item => [item.questionId, item]))
    : outcomes;
  const chosen = restored?.answers ?? answers;
  useEffect(() => {
    if (!savedChecks.data?.checks.length || content.kind !== "grammarLesson") return;
    const stored = savedChecks.data.checks;
    setAnswers(value => ({ ...value, ...Object.fromEntries(stored.map(item => [item.questionId, item.answer])) }));
    setQuestionResults(value => ({ ...value, ...Object.fromEntries(stored.map(item => [item.questionId, item.isCorrect])) }));
    setCorrectAnswers(value => ({
      ...value,
      ...Object.fromEntries(stored.flatMap(item => item.correctAnswer === null
        ? []
        : [[item.questionId, item.correctAnswer]])),
    }));
    setOutcomes(value => ({ ...value, ...Object.fromEntries(stored.map(item => [item.questionId, item.outcome])) }));
    setActiveIndex(visibleLessonQuestionIndex(content.questions.map(item => item.questionId), Object.fromEntries(stored.map(item => [item.questionId, item]))));
  }, [savedChecks.data, content]);
  if (content.kind !== "grammarLesson") return null;
  const answerFor = (question: typeof content.questions[number]) => question.interactionType === "sentenceBuilding"
    ? builtSentence((builtTokenIndexes[question.questionId] ?? []).map(index => question.tokenBank[index]))
    : answers[question.questionId] ?? "";
  const answered = content.questions.every(question => Boolean(answerFor(question)));
  const activeQuestion = content.questions[activeIndex];
  const activeAnswer = activeQuestion ? answerFor(activeQuestion) : "";
  const activeResult = activeQuestion ? results[activeQuestion.questionId] : undefined;
  const allChecked = content.questions.every(question => results[question.questionId] !== undefined);
  const check = async () => {
    if (!activeQuestion || !activeAnswer || checking) return;
    setChecking(true);
    setCheckError(null);
    try {
      const result = await checkLessonAnswer(task.id, activeQuestion.questionId, activeAnswer);
      setQuestionResults(value => ({ ...value, [result.questionId]: result.isCorrect }));
      const correctAnswer = result.correctAnswer;
      if (correctAnswer !== null) {
        setCorrectAnswers(value => ({ ...value, [result.questionId]: correctAnswer }));
      }
      setOutcomes(value => ({ ...value, [result.questionId]: result.outcome }));
      playAnswerSound(result.isCorrect);
    } catch (error) {
      setCheckError(friendlyError(error));
    } finally {
      setChecking(false);
    }
  };
  const submit = async () => {
    const taskAnswers = Object.fromEntries(content.questions.map(question => [question.questionId, answerFor(question)]));
    setChecking(true);
    try {
      const result = await actOnTask(task.id, "attempts", { inputMode: "vocabularyReview", answers: taskAnswers, typedAnswers: {} }, requestKey.current);
      if (result) {
        setActionResult(result);
        setFeedback(result.attempt?.feedback?.message ?? "Grammar practice saved.");
        setQuestionResults(reviewDetails(result.attempt)?.questionResults ?? {});
        setCorrectAnswers(reviewDetails(result.attempt)?.correctAnswers ?? {});
        setOutcomes(Object.fromEntries((reviewDetails(result.attempt)?.questionOutcomes ?? []).map(item => [item.questionId, item])));
      }
    } finally {
      setChecking(false);
    }
  };
  return <div className="stack vocabulary-flow">
    <div className="vocabulary-flow__progress"><ProgressTrail value={index + 1} total={total} label={`Task ${index + 1} of ${total}`} />{reward ? <XpPill {...reward} /> : null}</div>
    <div className="learning-title-row"><div className="vocabulary-flow__title"><IconButton className="vocabulary-flow__back" label="Back to tasks" onClick={onClose}><ArrowLeftIcon size={20} /></IconButton><h1>{content.title}</h1></div><ExitToHome onExit={onExit} /></div>
    {activeIndex === 0 && content.prep?.length ? <Card plain><div className="stack-2 lesson-prep" aria-label="Learn first">
      <span className="label muted">Learn first</span>
      {content.prep.map(card => <div key={card.text} className="lesson-prep__card">
        <div><strong lang={scene.languageCode}>{card.text}</strong>{card.translation ? <span className="muted small"> — {card.translation}</span> : null}</div>
        {audio ? <IconButton label={`Hear ${card.text}`} onClick={() => speak(card.text, scene.languageCode)}><SpeakerIcon /></IconButton> : null}
      </div>)}
    </div></Card> : null}
    {savedChecks.isLoading ? <InlineLoader compact label="Restoring your place…" /> : null}
    {savedChecks.isError ? <p role="alert">We couldn't restore your saved answers. Try refreshing this page.</p> : null}
    {content.questions.map((question, position) => {
      if (position !== activeIndex) return null;
      const questionMarkers = question.roleplayPremise
        ? questionMarkerObjects(
          question.sceneObjectId,
          session?.sceneObjects ?? [],
          scene.items,
        )
        : undefined;
      const groupObjects = question.groupObjectIds
        ?.map(id => session?.sceneObjects.find(object => object.id === id))
        .filter((object): object is SceneObject => Boolean(object));
      const markers = question.roleplayPremise ? [] : markerChoices(question, scene);
      // A0 counting questions highlight the group without marker numbers that would give the count away.
      const countQuestion = content.practiceLevel === "A0" && Boolean(groupObjects?.length || question.displayCount);
      const section = question.section && question.section !== content.questions[position - 1]?.section
        ? question.section : null;
      return <div key={question.questionId} className="learning-section">
        {section ? <h2 className="learning-section__title">{section}</h2> : null}
        <Card plain><div className="stack">
      {content.questions.length > 1 ? <span className="label muted">Question {position + 1} of {content.questions.length}</span> : null}
      {question.instruction ? <p className="small lesson-instruction">{question.instruction}</p> : null}
      <LessonAudioPrompt question={question} languageCode={scene.languageCode}
        revealed={Boolean(revealed[question.questionId])}
        graded={results[question.questionId] !== undefined}
        onReveal={() => setRevealed(value => ({ ...value, [question.questionId]: true }))} />
      {question.displayCount ? <CountBoard count={question.displayCount} sceneImageUrl={sceneImageUrl}
        imageSize={boardImageSize} onImageSize={setBoardImageSize}
        boardObject={session?.sceneObjects.find(object => object.id === question.boardObjectId)} /> : null}
      {question.sceneObjectId ? <ObjectPreview scene={scene} label={question.objectLabel ?? ""}
        object={session?.sceneObjects.find(object => object.id === question.sceneObjectId)}
        group={groupObjects?.length ? groupObjects : undefined}
        markers={questionMarkers}
        hideNumbers={countQuestion}
        reference={session?.sceneObjects.find(object => object.id === question.referenceObjectId)}
        referenceLabel={question.referenceLabel} /> : null}
      {question.roleplayPremise ? <div className="roleplay-premise" role="note">
        <p className="roleplay-premise__text"><strong>Scenario:</strong> {roleplayScenario(question.roleplayPremise)}</p>
      </div> : null}
      {question.interactionType === "sentenceBuilding" ? <>
        {question.promptTranslation
          ? <PromptTranslation source={question.prompt} text={question.promptTranslation} lang={scene.languageCode} />
          : question.translation ? <h2>{question.translation}</h2> : null}
        <div className="sentence-builder__answer" aria-label="Your sentence">
          {restored?.answers?.[question.questionId] ? <span>{restored.answers[question.questionId]}</span> : (builtTokenIndexes[question.questionId] ?? []).length ? (builtTokenIndexes[question.questionId] ?? []).map((tokenIndex, tokenPosition) => <button key={`${tokenIndex}-${tokenPosition}`} className="sentence-builder__token" disabled={terminal || practiceSaving}
            onClick={() => setBuiltTokenIndexes(value => ({ ...value, [question.questionId]: (value[question.questionId] ?? []).filter((_, index) => index !== tokenPosition) }))}>{question.tokenBank[tokenIndex]}</button>) : <span className="muted">Choose the words to build your sentence.</span>}
        </div>
        <div className="chip-row" aria-label="Sentence building words">{question.tokenBank.map((token, tokenIndex) => {
          const used = (builtTokenIndexes[question.questionId] ?? []).includes(tokenIndex);
          if (used) return null;
          return <button key={`${token}-${tokenIndex}`} className="chip" disabled={terminal || practiceSaving}
            onClick={() => setBuiltTokenIndexes(value => ({ ...value, [question.questionId]: [...(value[question.questionId] ?? []), tokenIndex] }))}>{token}</button>;
        })}</div>
      </> : <>
        {writtenPromptShown(question, { revealed: Boolean(revealed[question.questionId]), graded: results[question.questionId] !== undefined, audio })
          ? question.promptTranslation
            ? <PromptTranslation source={content.focus === "sceneDescription" ? question.translation || "Choose the sentence that describes the scene." : question.prompt}
              text={question.promptTranslation} lang={question.audioText ? scene.languageCode : undefined} />
            : <h2 lang={question.audioText ? scene.languageCode : undefined}>{content.focus === "sceneDescription" ? question.translation || "Choose the sentence that describes the scene." : question.prompt}</h2>
          : <h2 className="muted">Listen to the word.</h2>}
        {question.boardCounts ? <PracticeBoards question={question} sceneImageUrl={sceneImageUrl}
          imageSize={boardImageSize} onImageSize={setBoardImageSize}
          boardObject={session?.sceneObjects.find(object => object.id === question.boardObjectId)}
          ordered={question.options}
          chosen={chosen[question.questionId]} graded={results[question.questionId]}
          solution={solutions[question.questionId]}
          disabled={terminal || practiceSaving || checking || results[question.questionId] !== undefined}
          onChoose={optionId => setAnswers(value => ({ ...value, [question.questionId]: optionId }))} />
        : <>{markers.length ? <div className="mission-markers"><ScenePhoto scene={scene} hideWords
          items={markers.map(marker => marker.item)}
          activeItemId={markers.find(marker => marker.option.optionId === (results[question.questionId] !== undefined
            ? solutions[question.questionId] : chosen[question.questionId]))?.item.id ?? null}
          guessItemId={results[question.questionId] === false
            ? markers.find(marker => marker.option.optionId === chosen[question.questionId])?.item.id ?? null : null}
          onMarkerClick={terminal || practiceSaving || checking || results[question.questionId] !== undefined ? undefined
            : item => {
              const marker = markers.find(candidate => candidate.item.id === item.id);
              if (marker) setAnswers(value => ({ ...value, [question.questionId]: marker.option.optionId }));
            }} /></div> : null}
        <div className="choice-grid">{questionOptions(question, `${task.id}:${question.questionId}`).map(option => {
          const selected = chosen[question.questionId] === option.optionId;
          const graded = results[question.questionId];
          const state = graded !== undefined && solutions[question.questionId] === option.optionId ? " choice--correct"
            : !selected ? ""
              : graded === undefined ? " choice--selected" : graded ? " choice--correct" : " choice--incorrect";
          return <button key={option.optionId} className={`choice${state}`} aria-pressed={selected} disabled={terminal || practiceSaving || checking || graded !== undefined}
            onClick={() => setAnswers(value => ({ ...value, [question.questionId]: option.optionId }))}>
            {optionText(question, option.label)}</button>;
        })}</div></>}
      </>}
      {results[question.questionId] !== undefined ? <>
        <Feedback tone={results[question.questionId] ? "good" : "warn"}><p role="status">{results[question.questionId]
          ? <>Correct!{outcomeFor[question.questionId]?.correctNote
            ? ` ${outcomeFor[question.questionId]?.correctNote}` : ""}</>
          : <>Not quite.{solutions[question.questionId] ? (() => {
            const label = question.options.find(option => option.optionId === solutions[question.questionId])?.label;
            const solution = label ? optionText(question, label) : solutions[question.questionId];
            return <> The correct answer is <strong>{solution}</strong>{sentenceEnding(solution)}</>;
          })() : null}</>}</p></Feedback>
        {question.slotTemplate && solutions[question.questionId] ? (() => {
          const form = question.options.find(option => option.optionId === solutions[question.questionId])?.label ?? "";
          const chunk = question.completeChunk ?? completeSlot(question.slotTemplate, form);
          return <div className="lesson-audio"><p>Complete: <strong lang={scene.languageCode}>{chunk}</strong></p>
            {audio ? <IconButton label={`Hear ${chunk}`} onClick={() => speak(chunk, scene.languageCode)}><SpeakerIcon /></IconButton> : null}</div>;
        })() : null}
        {question.quantityWord && question.boardCounts ? <p className="small">
          {question.quantityWord} = {question.boardCounts[solutions[question.questionId] ?? ""] ?? "?"}
        </p> : null}
        <QuestionOutcomeNotes outcome={outcomeFor[question.questionId]} />
      </> : null}
    </div></Card>{results[question.questionId] !== undefined ? <ReportIssueLink reportType="Grammar answer" fields={[
      ["Task ID", task.id],
      ["Question ID", question.questionId],
      ["Prompt", question.translation || question.prompt],
      ["Your answer", answerFor(question)],
      ["Displayed solution", question.options.find(option => option.optionId === solutions[question.questionId])?.label ?? solutions[question.questionId]],
    ]} /> : null}</div>;
    })}
    {checking ? <InlineLoader compact label="Checking your answer…" /> : null}
    {checkError ? <p role="alert">{checkError}</p> : null}
    {feedback ?? restored?.feedback ?? earnedText ? <Feedback><div className="stack-2" role="status">{feedback ?? restored?.feedback ? <p>{feedback ?? restored?.feedback}</p> : null}{earnedText ? <strong>{earnedText}</strong> : null}</div></Feedback> : null}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    {terminal ? <Button block onClick={onNext}>{index < total - 1 ? "Next task" : lastStep}</Button> : <>
      {activeResult === undefined
        ? <Button block disabled={!activeAnswer || practiceSaving || checking} onClick={() => void check()}>Check answer</Button>
        : activeIndex < content.questions.length - 1
          ? <Button block disabled={checking} onClick={() => setActiveIndex(value => value + 1)}>Next question</Button>
          : <Button block disabled={!answered || !allChecked || practiceSaving || checking} onClick={() => void submit()}>Finish task</Button>}
      <Button variant="quiet" block disabled={practiceSaving} onClick={async () => { if (await actOnTask(task.id, "skip")) onNext(); }}>Skip task</Button>
    </>}
  </div>;
}

function VocabularyLearningCard({ word, languageCode }: { word: VocabularyLearningWord; languageCode: string }) {
  return <article className="flashcard learning-card vocabulary-learning-card">
    <div className="spread"><span className="label muted learning-card__meta">{word.termType === "relationship" ? "relationship" : word.partOfSpeech}{word.gender ? ` · ${word.gender}` : ""}</span>
      <IconButton className="learning-card__audio" label={`Hear ${word.targetText}`} onClick={() => speak(word.targetText, languageCode)}><SpeakerIcon /></IconButton></div>
    <div className="learning-card__word"><h2>{word.targetText}</h2><p className="muted">{word.translation}</p></div>
    {word.pluralForm ? <p className="small"><strong>Plural:</strong> {word.pluralForm}</p> : null}
    {word.phoneticText ? <p className="small muted" aria-label="Pronunciation">{word.phoneticText}</p> : null}
  </article>;
}

const BOARD_TILE = 26;

function PracticeBoards({ question, sceneImageUrl, imageSize, onImageSize, boardObject, ordered, chosen, graded, solution, disabled, onChoose }: {
  question: GrammarLessonQuestion;
  sceneImageUrl: string | null;
  imageSize: { width: number; height: number } | null;
  onImageSize: (size: { width: number; height: number }) => void;
  boardObject?: SceneObject;
  ordered: { optionId: string; label: string }[];
  chosen: string | undefined;
  graded: boolean | undefined;
  solution: string | undefined;
  disabled: boolean;
  onChoose: (optionId: string) => void;
}) {
  const crop = imageSize ? squareCrop(boardObject?.boundingBox, imageSize.width, imageSize.height) : null;
  return <div className="practice-boards">
    <p className="small muted">Choose the board that matches the sentence.</p>
    {sceneImageUrl && !imageSize ? <img className="practice-boards__preload" src={sceneImageUrl} alt="" aria-hidden="true"
      onLoad={event => onImageSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} /> : null}
    <div className="practice-boards__row">
      {ordered.map(option => {
        const count = question.boardCounts?.[option.optionId] ?? 0;
        const selected = chosen === option.optionId;
        const state = graded !== undefined && solution === option.optionId ? " choice--correct"
          : !selected ? ""
            : graded === undefined ? " choice--selected" : graded ? " choice--correct" : " choice--incorrect";
        const tile = crop && sceneImageUrl ? {
          backgroundImage: `url(${sceneImageUrl})`,
          backgroundSize: `${imageSize!.width * BOARD_TILE / crop.size}px ${imageSize!.height * BOARD_TILE / crop.size}px`,
          backgroundPosition: `-${crop.x * BOARD_TILE / crop.size}px -${crop.y * BOARD_TILE / crop.size}px`,
        } : undefined;
        return <button key={option.optionId} type="button" className={`choice practice-board${state}`}
          aria-label={option.label} aria-pressed={selected} disabled={disabled} onClick={() => onChoose(option.optionId)}>
          <span className="practice-board__tiles" aria-hidden="true">
            {boardRows(count).map((row, rowIndex) => <span key={rowIndex} className="practice-board__tile-row">
              {Array.from({ length: row }, (_, tileIndex) => <span key={tileIndex}
                className={`practice-board__tile${tile ? "" : " practice-board__tile--fallback"}`} style={tile} />)}
            </span>)}
          </span>
          <span className="practice-board__meta">
            <span className="practice-board__label">{option.label}</span>
            {graded !== undefined ? <span className="practice-board__count">{count}</span> : null}
          </span>
        </button>;
      })}
    </div>
  </div>;
}

/** A practice board of `count` cropped copies of one object, shown without numbers. */
const COUNT_TILE = 72;

function CountBoard({ count, sceneImageUrl, imageSize, onImageSize, boardObject }: {
  count: number;
  sceneImageUrl: string | null;
  imageSize: { width: number; height: number } | null;
  onImageSize: (size: { width: number; height: number }) => void;
  boardObject?: SceneObject;
}) {
  const crop = imageSize ? squareCrop(boardObject?.boundingBox, imageSize.width, imageSize.height) : null;
  const tile = crop && sceneImageUrl && imageSize ? {
    width: COUNT_TILE, height: COUNT_TILE,
    backgroundImage: `url(${sceneImageUrl})`,
    backgroundSize: `${imageSize.width * COUNT_TILE / crop.size}px ${imageSize.height * COUNT_TILE / crop.size}px`,
    backgroundPosition: `-${crop.x * COUNT_TILE / crop.size}px -${crop.y * COUNT_TILE / crop.size}px`,
  } : undefined;
  return <div className="practice-boards" aria-label="Practice board">
    {sceneImageUrl && !imageSize ? <img className="practice-boards__preload" src={sceneImageUrl} alt="" aria-hidden="true"
      onLoad={event => onImageSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} /> : null}
    <div className="practice-board count-board" aria-hidden="true"><span className="practice-board__tiles">
      {boardRows(count).map((row, rowIndex) => <span key={rowIndex} className="practice-board__tile-row">
        {Array.from({ length: row }, (_, tileIndex) => <span key={tileIndex}
          className={`practice-board__tile${tile ? "" : " practice-board__tile--fallback"}`} style={tile ?? { width: COUNT_TILE, height: COUNT_TILE }} />)}
      </span>)}
    </span></div>
  </div>;
}

function useLastStepLabel() {
  const { session } = useAppState();
  if (session && finishesAfterLearning(session.tasks)) return "Finish lesson";
  return "Go to I-Spy";
}

function QuestionOutcomeNotes({ outcome }: { outcome?: QuestionOutcome }) {
  if (!outcome) return null;
  return <>
    {outcome.mistakes.map((mistake, position) => mistake.explanation ? <p key={position} className="small">{mistake.explanation}</p> : null)}
    {outcome.optionNotes?.length ? <div className="stack-2 small">
      <p className="muted">Why the other options don't fit:</p>
      <ul>{outcome.optionNotes.map((note, i) => <li key={i}>{note}</li>)}</ul>
    </div> : null}
    {outcome.assistance.includes("wordBank") ? <p className="small muted">Supported practice: built with the word bank.</p> : null}
  </>;
}

function roleplayScenario(text: string) {
  const direct = text
    .replace(/^let(?:'|’)s pretend(?: that)?\s+/i, "")
    .replace(/^pretend(?: that)?\s+/i, "")
    .trim();
  return direct ? direct.charAt(0).toUpperCase() + direct.slice(1) : text;
}

function PromptTranslation({ text, source, lang }: { text?: string | null; source?: ReactNode; lang?: string }) {
  const [shown, setShown] = useState(false);
  if (!text) return null;
  const toggle = <IconButton className="prompt-translation__toggle" label={shown ? "Hide translation" : "Show translation"}
      aria-expanded={shown} onClick={() => setShown(value => !value)}>
      {shown ? <EyeIcon size={20} /> : <EyeOffIcon size={20} />}
    </IconButton>;
  if (source) return <span className="prompt-translation prompt-translation--with-source">
    <span className="prompt-translation__source"><h2 lang={lang}>{source}</h2>{toggle}</span>
    {shown ? <span className="small muted">{text}</span> : null}
  </span>;
  return <span className="prompt-translation">
    {shown ? <span className="small muted">{text}</span> : null}{toggle}
  </span>;
}

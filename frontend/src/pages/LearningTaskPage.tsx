import { useRefreshBasil } from "../state/gamification";
import { QuestionBasil } from "../components/MissionProgress";
import { basilEarnedText } from "../lib/gamification";
import { InlineLoader } from "../components/LoadingScreen";
import { useEffect, useRef, useState, type ReactNode, type TouchEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { friendlyError, queryKeys } from "../lib/queryKeys";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { BasilReward, Button, Card, Feedback, IconButton, ProgressTrail } from "../components/ui";
import { ArrowLeftIcon, ArrowRightIcon, CheckIcon, CloseIcon, EyeIcon, EyeOffIcon, SpeakerIcon } from "../components/icons";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { builtSentence, choiceOrder, markerChoices, nextLearningStep, optionText, practiceStages, questionOptions, sentenceEnding, taskDone, taskTitle } from "../lib/practiceTasks";
import type { LearningStep } from "../lib/practiceTasks";
import { checkLessonAnswer, checkVocabularyAnswer, checkVocabularyTyping, getVocabularyChecks, getLatestAttempt, getLessonChecks, requestLessonAssistance, reviewDetails, updateMissionScenario, type GrammarLessonQuestion, type LessonAnswerCheck, type SceneObject, type SessionTask, type QuestionOutcome, type TaskActionResult, type TaskAnswer, type TaskContent, type VocabularyLearningWord } from "../lib/api";
import { TargetLanguageContext, useTargetLanguage } from "../state/targetLanguage";
import { mergeLessonChecks, visibleLessonQuestionIndex } from "../lib/missionLessonFlow";
import { isM06ScenarioVisible, lessonCheckFinished, nextAssistanceStep, retryTokens, unlockedRetryResumeIndex } from "../lib/missionM06";
import { ReportIssueLink } from "../components/ReportIssueLink";
import { ObjectPreview } from "../components/ObjectPreview";
import { ScenePhoto } from "../components/ScenePhoto";
import { useResolvedImageUrl } from "../components/SceneImage";
import { boardRows, practiceBoardCrop } from "../lib/practiceBoard";
import { questionMarkerObjects } from "../lib/missionMarkers";
import { completeSlot, writtenPromptShown } from "../lib/missionA0";
import { trackAction } from "../lib/analytics.ts";
import { fillMissionGap } from "../lib/missionGaps";
import { playAnswerSound } from "../lib/answerSound";
import { learningFeedback } from "../lib/learningFeedback";
import { vocabularyRecapSteps } from "../lib/vocabularyRecap";
import { MissionCheatSheetLauncher } from "../components/MissionCheatSheet";
import { VOCABULARY_SECTIONS, vocabularyReviewGroups, wordMatchesMarker } from "../lib/vocabularyReview";

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
  const isVocabularyTask = task.kind === "vocabularyIntroduction";
  const generating = session.session.status === "generatingTasks";
  const goTo = (step: LearningStep) => {
    if (step.to === "task") navigate(`${base}/learn/${step.taskId}`);
    else if (step.to === "tasks") navigate(`${base}/learn`);
    else if (step.to === "ispy") navigate(`${base}/ispy-1`);
    else if (completeSession()) navigate(`${base}/summary`);
  };
  const skipM06RolePlay = () => {
    const lastM06 = tasks.filter(item => item.publicContent.missionId === "M06").at(-1) ?? task;
    // The role-play tasks were just skipped; this render's session predates those replies.
    goTo(nextLearningStep(session.tasks, lastM06.id, generating,
      item => taskDone(item) || item.publicContent.missionId === "M06"));
  };
  return <TargetLanguageContext.Provider value={task.publicContent.languageContext ?? null}><div className="stack learning-task-page"><LearningTaskContent key={task.id} task={task} index={index} total={tasks.length}
    onScenarioChange={() => loadSession(session.session.id)}
    onSkipRolePlay={skipM06RolePlay}
    onNext={() => {
      if (isVocabularyTask) {
        navigate(`${base}/learn`);
        return;
      }
      if (index === tasks.length - 1) {
        trackAction("task_finished_to_list", { taskId: task.id, kind: task.kind });
        navigate(`${base}/learn`);
        return;
      }
      goTo(nextLearningStep(session.tasks, task.id, generating));
    }} onClose={() => navigate(`${base}/learn`)} onExit={() => navigate("/home")} /></div></TargetLanguageContext.Provider>;
}

/** A completed scene can be revisited without reopening its finished lesson. */
export function VocabularySceneReview() {
  const { session } = useAppState();
  const navigate = useNavigate();
  if (!session) return null;
  const task = session.tasks.find(item => item.kind === "vocabularyIntroduction");
  if (!task) return <Navigate to="/vocabulary" replace />;
  return <TargetLanguageContext.Provider value={task.publicContent.languageContext ?? null}><div className="stack learning-task-page"><VocabularyLearningFlow task={task} index={0} total={1} revisiting
    onNext={() => navigate("/vocabulary")} onClose={() => navigate("/vocabulary")} onExit={() => navigate("/vocabulary")} /></div></TargetLanguageContext.Provider>;
}

function LearningTaskContent({ task, index, total, onNext, onClose, onExit, onScenarioChange, onSkipRolePlay }: {
  task: SessionTask; index: number; total: number; onNext: () => void; onClose: () => void; onExit: () => void;
  onScenarioChange: () => Promise<unknown>; onSkipRolePlay: () => void;
}) {
  const { speak } = useTargetLanguage();
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
        if (reading) {
          trackAction("task_completed", { taskId: task.id, kind: content.kind });
          setFeedback(result.attempt?.feedback?.message ?? "Task complete.");
        } else {
          trackAction("task_answer_checked", { taskId: task.id, isCorrect: result.attempt?.isCorrect, kind: content.kind });
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
  const earnedText = basilEarnedText(actionResult?.basilEarned);
  return <div className="stack">
    <div className="vocabulary-flow__progress"><ProgressTrail value={1} total={1} label="Question 1 of 1" /></div>
    <div className="learning-title-row"><div className="vocabulary-flow__title"><IconButton className="vocabulary-flow__back" label="Back to tasks" onClick={onClose}><ArrowLeftIcon size={20} /></IconButton></div><ExitToHome onExit={onExit} /></div>
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
    {(actionResult && task.status !== "skipped") || feedback ? <>
      <Feedback tone={answerCorrect === false ? "warn" : "good"}><div className="stack-2" role="status" aria-atomic="true">
        {actionResult && task.status !== "skipped" ? <strong>{learningFeedback(answerCorrect === null ? "saved" : answerCorrect ? "correct" : "incorrect", task.id)}</strong> : null}
        {feedback ? <p>{feedback}</p> : null}</div></Feedback>
    </> : null}
    <BasilReward text={earnedText} />
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    {terminal ? <Button block disabled={practiceSaving} onClick={onNext}>{index < total - 1 ? "Next task" : "Finish task"}</Button> : <>
      <Button block disabled={practiceSaving || checking || (!reading && !(content.kind === "grammarPractice" ? choice : text.trim()))} onClick={() => void submit()}>{reading ? "Mark complete" : "Submit answer"}</Button>
      <Button variant="quiet" block disabled={practiceSaving} onClick={async () => { if (await actOnTask(task.id, "skip")) onNext(); }}>Skip task</Button>
    </>}
    {feedback || earnedText ? <div className="learning-question-report"><ReportIssueLink reportType={taskTitle(task)} fields={[
      ["Task ID", task.id],
      ["Prompt", "prompt" in content ? content.prompt : taskTitle(task)],
      ["Your answer", content.kind === "grammarPractice" ? choice : text],
      ["Displayed feedback", feedback],
      ["Language", scene.languageCode],
    ]} /></div> : null}
  </div>;
}

function ExitToHome({ onExit }: { onExit: () => void }) {
  return <Button variant="quiet" className="learning-exit" onClick={onExit}><CloseIcon size={18} /> Exit</Button>;
}

function VocabularyLearningFlow({ task, index, total, onNext, onClose, onExit, revisiting = false }: { task: SessionTask; index: number; total: number; onNext: () => void; onClose: () => void; onExit: () => void; revisiting?: boolean }) {
  const refreshBasil = useRefreshBasil();
  const { nativeProps, speak, speechAvailable } = useTargetLanguage();
  const scene = useScene();
  const { actOnTask, practiceSaving, practiceError, session } = useAppState();
  const content = task.publicContent;
  const [stage, setStage] = useState<"review" | "quiz" | "typing" | "complete">("review");
  const [recapIndex, setRecapIndex] = useState(0);
  const [page, setPage] = useState(0);
  const [selectedMarkerId, setSelectedMarkerId] = useState<string | null>(null);
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
  const [typingCheck, setTypingCheck] = useState<{ isCorrect: boolean; isClose: boolean; correctAnswer: string; revealed: boolean; basilEarned: number } | null>(null);
  const requestKey = useRef(crypto.randomUUID());
  const swipeStart = useRef<{ x: number; y: number } | null>(null);
  const [basilByQuestion, setBasilByQuestion] = useState<Record<string, number>>({});
  const [questionError, setQuestionError] = useState<string | null>(null);
  const restoredNavigation = useRef(false);
  const restored = useQuery({ queryKey: queryKeys.vocabularyChecks(task.id),
    queryFn: ({ signal }) => getVocabularyChecks(task.id, signal), enabled: !revisiting });
  useEffect(() => {
    if (revisiting) return;
    if (!restored.data?.checks) return;
    const checks = restored.data.checks;
    setAnswers(value => ({ ...value, ...Object.fromEntries(checks.map(item => [item.questionId, item.acceptedOptionId])) }));
    setQuestionResults(value => ({ ...value, ...Object.fromEntries(checks.map(item => [item.questionId, item.isCorrect])) }));
    setCorrectOptionIds(value => ({ ...value, ...Object.fromEntries(checks.map(item => [item.questionId, item.correctOptionId])) }));
    setBasilByQuestion(value => ({ ...value, ...Object.fromEntries(checks.map(item => [item.questionId, item.basilEarned])) }));
    if (!restoredNavigation.current) {
      restoredNavigation.current = true;
      if (!checks.length) return;
      const questions = task.publicContent.kind === "vocabularyIntroduction" ? task.publicContent.questions : [];
      const first = questions.findIndex(item => !checks.some(check => check.questionId === item.questionId));
      // Typing progress is local, so resume from the second recognition answer
      // before continuing through the interleaved recognition/typing sequence.
      setQuestionIndex(first === 0 ? 0 : Math.min(1, Math.max(0, questions.length - 1)));
      setStage("quiz");
    }
  }, [restored.data, revisiting, task.publicContent]);
  useEffect(() => {
    if (content.kind !== "vocabularyIntroduction" || stage !== "review") return;
    const words = vocabularyReviewGroups(content.words)[page] ?? [];
    words.forEach(word => trackAction("vocabulary_flashcard_viewed", {
      taskId: task.id,
      position: page + 1,
      termType: word.termType,
      hasSceneObject: Boolean(word.sceneObjectId),
      groupedCardCount: words.length,
    }));
  }, [content, page, stage, task.id]);
  if (content.kind !== "vocabularyIntroduction") return null;
  const terminal = taskDone(task);
  const revision = task.status === "skipped";
  const active = !terminal || revision || revisiting;
  const reviewing = active && stage === "review";
  const reviewGroups = vocabularyReviewGroups(content.words);
  const pageCount = reviewGroups.length;
  const reviewWords = reviewGroups.map(group => group[0]);
  const visibleWords = reviewGroups[page] ?? [];
  const reviewWord = visibleWords[0];
  const objectMarkers = scene.items.filter(item => reviewWords.some(word => wordMatchesMarker(word, item.id)));
  const markerSelectedForWord = reviewWord && selectedMarkerId && wordMatchesMarker(reviewWord, selectedMarkerId)
    ? selectedMarkerId : null;
  const question = content.questions[questionIndex];
  const typingWord = content.words[typingIndex];
  const typingKey = typingWord ? typingWord.learningKey ?? typingWord.vocabularyItemId ?? typingWord.targetText : "";
  const earnedText = basilEarnedText(actionResult?.basilEarned);
  const submit = async (typingAnswers = typedAnswers) => {
    if (revisiting) { setFeedback("Review complete."); return; }
    const result = await actOnTask(task.id, "attempts", { inputMode: "vocabularyReview", answers, typedAnswers: typingAnswers }, requestKey.current);
    if (result) {
      setActionResult(result);
      setFeedback(result.attempt?.feedback?.message ?? "Vocabulary practice saved.");
      setQuestionResults(reviewDetails(result.attempt)?.questionResults ?? {});
    }
  };
  const recap = vocabularyRecapSteps(content.questions.length, content.allowTypingPractice ? content.words.length : 0);
  const questionTotal = Math.max(1, content.questions.length);
  const questionPosition = stage === "complete"
    ? questionTotal
    : stage === "quiz"
      ? Math.min(questionIndex + 1, questionTotal)
      : stage === "typing"
        ? Math.min(typingIndex + 2, questionTotal)
        : 1;
  const advanceRecap = (nextIndex = recapIndex + 1) => {
    setFeedback(null);
    const next = recap[nextIndex];
    if (!next) {
      setStage("complete");
      trackAction("vocabulary_recap_completed", { questionCount: content.questions.length, wordCount: content.words.length });
      return;
    }
    setRecapIndex(nextIndex);
    setStage(next.kind);
    if (next.kind === "quiz") setQuestionIndex(next.index);
    else setTypingIndex(next.index);
  };
  const hasExercises = revisiting ? recap.length > 0 : content.questions.length > 0;
  const exercisesBlocked = practiceSaving || (!revisiting && !restored.isSuccess);
  const startExercises = (source: "shortcut" | "cardsComplete") => {
    if (revision || !hasExercises || exercisesBlocked) return;
    setSelectedMarkerId(null);
    trackAction("vocabulary_exercises_started", {
      taskId: task.id, source, revisiting,
      questionCount: content.questions.length, wordCount: content.words.length,
    });
    if (revisiting) {
      trackAction("vocabulary_recap_started", { questionCount: content.questions.length, wordCount: content.words.length });
      advanceRecap(0);
    } else setStage("quiz");
  };
  const finishReview = () => {
    setSelectedMarkerId(null);
    if (page < pageCount - 1) { setPage(value => value + 1); return; }
    startExercises("cardsComplete");
  };
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
    setSelectedMarkerId(null);
    if (horizontal < 0 && page < pageCount - 1) setPage(value => value + 1);
    if (horizontal > 0 && page > 0) setPage(value => value - 1);
  };
  const finishQuestion = () => {
    if (revisiting) { advanceRecap(); return; }
    if (questionIndex === 0 && content.questions.length > 1) {
      setQuestionIndex(1);
      return;
    }
    setTypingIndex(Math.max(0, questionIndex - 1));
    setStage("typing");
  };
  const chooseAnswer = async (optionId: string) => {
    if (!question || answers[question.questionId] || checkingQuestion || restored.isLoading || restored.isError) return;
    setCheckingQuestion(true);
    setQuestionError(null);
    setPendingOptionId(optionId);
    try {
      const result = await checkVocabularyAnswer(task.id, question.questionId, optionId, revisiting);
      setAnswers(value => ({ ...value, [question.questionId]: result.acceptedOptionId }));
      setQuestionResults(value => ({ ...value, [question.questionId]: result.isCorrect }));
      setCorrectOptionIds(value => ({ ...value, [question.questionId]: result.correctOptionId }));
      setBasilByQuestion(value => ({ ...value, [question.questionId]: result.basilEarned }));
      setPendingOptionId(null);
      if (revisiting) trackAction("vocabulary_recap_answer_checked", { kind: "recognition", isCorrect: result.isCorrect });
      refreshBasil();
      playAnswerSound(result.isCorrect);
    } catch {
      setQuestionError("We couldn’t save this answer. Try again when you’re connected.");
    } finally {
      setCheckingQuestion(false);
    }
  };
  const checkTyping = async (reveal = false) => {
    if (!typingWord || checkingTyping) return;
    if (revisiting) setFeedback(null);
    setCheckingTyping(true);
    try {
      const result = await checkVocabularyTyping(task.id, typingKey, typedAnswers[typingKey] ?? "", reveal);
      setTypingCheck(result);
      trackAction("vocabulary_typing_checked", {
        taskId: task.id,
        termType: typingWord.termType,
        isCorrect: result.isCorrect,
        isClose: result.isClose,
        revealed: result.revealed,
        basilEarned: result.basilEarned,
      });
      if (result.basilEarned > 0) refreshBasil();
      if (revisiting) trackAction("vocabulary_recap_answer_checked", { kind: "recall", isCorrect: result.isCorrect, revealed: result.revealed });
      if (result.isCorrect) playAnswerSound(true);
    } catch (error) {
      setFeedback(friendlyError(error));
    } finally {
      setCheckingTyping(false);
    }
  };
  const advanceTyping = (skip = false) => {
    setTypingCheck(null);
    setFeedback(null);
    const remainingAnswers = skip
      ? Object.fromEntries(Object.entries(typedAnswers).filter(([key]) => key !== typingKey))
      : typedAnswers;
    if (skip) {
      setTypedAnswers(remainingAnswers);
      trackAction("vocabulary_typing_skipped", { taskId: task.id, termType: typingWord?.termType, revisiting });
    }
    if (revisiting) { advanceRecap(); return; }
    const nextQuestionIndex = typingIndex + 2;
    if (nextQuestionIndex < content.questions.length) {
      setQuestionIndex(nextQuestionIndex);
      setStage("quiz");
    } else if (typingIndex < content.words.length - 1) {
      setTypingIndex(value => value + 1);
    } else {
      void submit(remainingAnswers);
    }
  };
  return <div className="stack vocabulary-flow">
    <div className="vocabulary-flow__header">
      <div className="vocabulary-flow__progress"><ProgressTrail value={questionPosition} total={questionTotal} label={`Question ${questionPosition} of ${questionTotal}`} /><QuestionBasil amount={stage === "quiz" && question ? basilByQuestion[question.questionId] : stage === "typing" ? typingCheck?.basilEarned : undefined} /></div>
      <div className="learning-title-row"><div className="vocabulary-flow__title"><IconButton className="vocabulary-flow__back" label="Back to tasks" onClick={onClose}><ArrowLeftIcon size={20} /></IconButton><h1>{content.title}</h1></div><ExitToHome onExit={onExit} /></div>
    </div>
    {restored.isLoading ? <InlineLoader compact label="Restoring word answers…" /> : null}
    {restored.isError ? <div role="alert"><p>We couldn’t restore your word answers.</p><Button variant="quiet" onClick={() => void restored.refetch()}>Retry saved answers</Button></div> : null}
    {questionError ? <div role="alert"><p>{questionError}</p><Button variant="secondary" disabled={checkingQuestion || !pendingOptionId} onClick={() => pendingOptionId && void chooseAnswer(pendingOptionId)}>Retry answer</Button></div> : null}
    {active && stage === "review" ? <>
      {revision ? <div className="panel-note" role="status"><strong>Saved for revision</strong><p className="small muted">You skipped this practice earlier, but these words will stay here whenever you want to review them.</p></div> : null}
      {reviewWord ? <div className="vocabulary-review-section">
        <h2 aria-live="polite">{reviewWord.termType === "object" ? "Objects and adjectives" : VOCABULARY_SECTIONS[reviewWord.termType]}</h2>
        <p className="small muted">{reviewWord.termType === "object"
          ? speechAvailable() ? "Tap a number to see and hear its word, or use Next to keep exploring." : "Tap a number to see its word. Pronunciation isn't available in this browser for this language."
          : speechAvailable() ? "Listen with the speaker button. The photo shows the context." : "The photo shows the context. Pronunciation isn't available in this browser for this language."}</p>
      </div> : null}
    </> : null}
      <div className="vocabulary-learning-scene" aria-label={reviewing && reviewWord ? `${reviewWord.termType === "relationship" ? "Objects related by" : "Location of"} ${reviewWord.translation} in your photo` : "Your photo"}>
        <ScenePhoto
          scene={scene}
          items={!reviewing ? [] : reviewWord?.termType === "object" ? objectMarkers : scene.items.filter(item => item.id === reviewWord?.sceneObjectId || reviewWord?.relatedSceneObjectIds?.includes(item.id))}
          activeItemId={reviewing ? markerSelectedForWord ?? reviewWord?.sceneObjectId : null}
          activeItemIds={reviewing && !markerSelectedForWord ? reviewWord?.relatedSceneObjectIds : []}
          onMarkerClick={reviewing && reviewWord?.termType === "object" ? item => {
            const exactPage = reviewWords.findIndex(word => word.termType === "object" && word.sceneObjectId === item.id);
            const nextPage = exactPage >= 0 ? exactPage : reviewWords.findIndex(word => wordMatchesMarker(word, item.id));
            if (nextPage < 0) return;
            const word = reviewWords[nextPage];
            setPage(nextPage);
            setSelectedMarkerId(item.id);
            if (speechAvailable()) speak(word.targetText, scene.languageCode);
            trackAction("vocabulary_marker_clicked", { taskId: task.id, marker: item.marker, audioAvailable: speechAvailable() });
          } : undefined}
        />
      </div>
    {reviewing ? <>
      <div className={`vocabulary-learning-grid vocabulary-learning-grid--swipe${visibleWords.length > 1 ? " vocabulary-learning-grid--paired" : ""}`} aria-live="polite" onTouchStart={handleCardTouchStart} onTouchEnd={handleCardTouchEnd}>{visibleWords.map((word, cardIndex) => <VocabularyLearningCard key={`${word.learningKey ?? word.vocabularyItemId ?? word.targetText}:${cardIndex}`} word={word} languageCode={scene.languageCode} />)}</div>
      <div className="vocabulary-flow__actions">
        <Button disabled={page === 0} onClick={() => { setSelectedMarkerId(null); setPage(value => value - 1); }}><ArrowLeftIcon size={18} /> Previous</Button>
        {revision && page === pageCount - 1
          ? <Button variant="secondary" onClick={onClose}>Back to tasks</Button>
          : <Button variant="secondary" disabled={page === pageCount - 1 && (exercisesBlocked || !hasExercises)} onClick={finishReview}>{page < pageCount - 1 ? <>Next <ArrowRightIcon /></> : "Start quick quiz"}</Button>}
      </div>
      {!revision && hasExercises ? <Button variant="quiet" block disabled={exercisesBlocked} onClick={() => startExercises("shortcut")}>Go to exercises</Button> : null}
    </> : null}
    {active && stage === "quiz" && question ? <><Card plain><div className="stack">
      <h2>{question.prompt}</h2>
      <div className="choice-grid">{choiceOrder(question.options, `${task.id}:${question.questionId}`, option => option.optionId).map(option => {
        const selected = answers[question.questionId] === option.optionId || pendingOptionId === option.optionId;
        const result = questionResults[question.questionId];
        const isCorrectOption = correctOptionIds[question.questionId] === option.optionId;
        const state = result !== undefined && isCorrectOption ? " choice--correct"
          : !selected ? ""
            : result === undefined ? " choice--selected" : result ? " choice--correct" : " choice--incorrect";
        return <button key={option.optionId} className={`choice${state}`} aria-pressed={selected} disabled={!!answers[question.questionId] || checkingQuestion || !!feedback || restored.isLoading || restored.isError} onClick={() => void chooseAnswer(option.optionId)}><span {...nativeProps}>{option.label}</span>{question.romanizations?.[option.label] ? <small lang="und-Latn" dir="ltr"> {question.romanizations[option.label]}</small> : null}</button>;
      })}</div>
      {checkingQuestion ? <InlineLoader compact label="Checking your answer…" /> : null}
      {answers[question.questionId] ? <>
        <Feedback tone={questionResults[question.questionId] ? "good" : "warn"}><div className="stack-2" role="status" aria-atomic="true">
          <strong>{learningFeedback(questionResults[question.questionId] ? "correct" : "incorrect", `${task.id}:${question.questionId}`)}</strong>
          <p>{questionResults[question.questionId] ? "Correct!" : (() => {
          const answer = question.options.find(option => option.optionId === correctOptionIds[question.questionId])?.label ?? "";
          return <>Incorrect. The correct answer is <strong>{answer}</strong>{answer ? sentenceEnding(answer) : ""}</>;
        })()}</p></div></Feedback>
      </> : null}
      <Button block disabled={!answers[question.questionId]} onClick={finishQuestion}>{revisiting ? recapIndex < recap.length - 1 ? "Continue" : "Finish review" : "Next question"}</Button>
    </div></Card></> : null}
    {active && stage === "typing" && typingWord ? <Card plain><div className="stack">
      <div><h2>Type “{typingWord.translation}”</h2></div>
      <input {...nativeProps} className="input" aria-label={`Type ${typingWord.translation}`} value={typedAnswers[typingKey] ?? ""} disabled={typingCheck?.isCorrect || typingCheck?.isClose || typingCheck?.revealed} onChange={event => { setTypedAnswers(value => ({ ...value, [typingKey]: event.target.value })); setTypingCheck(null); }} />
      {checkingTyping ? <InlineLoader compact label="Checking your word…" /> : null}
      {typingCheck ? <Feedback tone={typingCheck.isCorrect ? "good" : typingCheck.isClose || typingCheck.revealed ? "neutral" : "warn"}><div className="stack-2" role="status"><p>{typingCheck.isCorrect ? "That’s right!" : typingCheck.isClose ? <>Close! You’re missing some accents. Write it as <strong>{typingCheck.correctAnswer}</strong>.</> : typingCheck.revealed ? <>No worries, the answer is <strong>{typingCheck.correctAnswer}</strong>.</> : "Not quite. Give it another try."}</p></div></Feedback> : null}
      {typingCheck?.isCorrect || typingCheck?.isClose || typingCheck?.revealed
        ? <Button block disabled={practiceSaving} onClick={() => advanceTyping()}>{revisiting ? recapIndex < recap.length - 1 ? "Continue" : "Finish review" : typingIndex < content.words.length - 1 || typingIndex + 2 < content.questions.length ? "Next question" : "Finish task"}</Button>
        : <Button block disabled={!typedAnswers[typingKey]?.trim() || practiceSaving || checkingTyping} onClick={() => void checkTyping()}>Check answer</Button>}
      {!typingCheck?.isCorrect && !typingCheck?.isClose && !typingCheck?.revealed ? <Button variant="quiet" block className="typing-forgot-action" disabled={practiceSaving || checkingTyping} onClick={() => void checkTyping(true)}>I forgot, lift the lid</Button> : null}
      {!typingCheck?.isCorrect && !typingCheck?.isClose && !typingCheck?.revealed ? <Button variant="quiet" block disabled={practiceSaving || checkingTyping} onClick={() => advanceTyping(true)}>Skip typing</Button> : null}
    </div></Card> : null}
    {revisiting && stage === "complete" ? <Card plain><div className="stack">
      <h2>Review complete</h2><p>You practised these words again.</p>
      <Button block onClick={onNext}>Back to vocabulary</Button>
    </div></Card> : null}
    {(actionResult && task.status !== "skipped") || feedback ? <Feedback><div className="stack-2" role="status" aria-atomic="true">
      {actionResult && task.status !== "skipped" ? <strong>{learningFeedback("saved", task.id)}</strong> : null}
      {feedback ? <p>{feedback}</p> : null}</div></Feedback> : null}
    <BasilReward text={earnedText} />
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    {terminal && !revision && !revisiting ? <Button block onClick={onNext}>{session?.session.status === "generatingTasks" ? "Back to tasks" : index < total - 1 ? "Next task" : "Finish task"}</Button> : null}
    {!terminal ? <Button variant="quiet" block disabled={practiceSaving} onClick={async () => { if (await actOnTask(task.id, "skip")) onNext(); }}>Skip vocabulary review</Button> : null}
    {!terminal && stage === "quiz" && question && answers[question.questionId] ? <div className="learning-question-report"><ReportIssueLink reportType="Vocabulary answer" fields={[
      ["Task ID", task.id],
      ["Question ID", question.questionId],
      ["Prompt", question.prompt],
      ["Your answer", question.options.find(option => option.optionId === answers[question.questionId])?.label],
      ["Displayed solution", question.options.find(option => option.optionId === correctOptionIds[question.questionId])?.label],
      ["Language", scene.languageCode],
    ]} /></div> : null}
  </div>;
}

function MissionSnapshotFacts({ task, scene }: { task: SessionTask; scene: ReturnType<typeof useScene> }) {
  const content = task.publicContent;
  if (content.kind !== "grammarLesson" || !content.missionSnapshot) return null;
  const snapshot = content.missionSnapshot;
  const objectLabel = (id?: string | null) => {
    const item = scene.items.find(item => item.id === id);
    return item ? `${item.translation} (marker ${item.marker})` : id;
  };
  const focus = snapshot.ownedObjectId ?? snapshot.chosenObjectId ?? snapshot.preferenceObjectIds?.[0];
  return <section className="mission-planning-facts" aria-label="Your mission facts">
    <strong>{focus ? `${snapshot.pretend ? "Practice scenario" : snapshot.missionId === "M05" ? "Your preference" : "Your choice"}: ${objectLabel(focus)}` : "Your choice"}</strong>
    <ul>
      {focus && snapshot.missionId === "M04" ? <li>It's yours.</li> : null}
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

function LessonAudioPrompt({ question, languageCode, revealed, graded, onReveal, showAudioText = false, inlineAudio = false }: {
  question: GrammarLessonQuestion;
  languageCode: string;
  revealed: boolean;
  graded: boolean;
  onReveal: () => void;
  showAudioText?: boolean;
  inlineAudio?: boolean;
}) {
  const { speak, speechAvailable, nativeProps } = useTargetLanguage();
  const audio = speechAvailable();
  const written = writtenPromptShown(question, { revealed, graded, audio });
  if (!question.audioText) return null;
  return <>
    {audio && (!inlineAudio || (question.listenFirst && !written)) ? <div className="lesson-audio">
      <IconButton label={question.listenFirst ? "Play the word" : `Hear ${question.audioText}`}
        onClick={() => speak(question.audioText ?? "", languageCode)}><SpeakerIcon /></IconButton>
      {question.listenFirst && !written
        ? <Button variant="quiet" onClick={onReveal}>Show the written word</Button> : null}
    </div> : null}
    {question.listenFirst && !audio
      ? <p className="small muted" role="note">Audio isn't available here, so read the word instead.</p> : null}
    {showAudioText && written ? <p {...nativeProps} lang={nativeProps.lang ?? languageCode}>{question.audioText}</p> : null}
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
  const { speak, speechAvailable, nativeProps } = useTargetLanguage();
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
      label={question.objectLabel ?? ""} /> : <ScenePhoto scene={scene} items={[]} />}
    {scenario ? <div className="roleplay-premise" role="note">
      <p className="roleplay-premise__text"><strong>Scenario:</strong> {roleplayScenario(scenario)}</p>
    </div> : null}
    <LessonAudioPrompt question={question} languageCode={scene.languageCode} revealed={revealed}
      graded={Boolean(checked)} onReveal={() => setRevealed(true)} showAudioText />
    {question.translation
      ? <PromptTranslation source={question.prompt} text={question.translation} lang={scene.languageCode} romanization={question.romanizations?.[question.prompt]} />
      : <><h2 {...nativeProps}>{question.prompt}</h2>{question.romanizations?.[question.prompt] ? <p className="muted" lang="und-Latn" dir="ltr">{question.romanizations[question.prompt]}</p> : null}</>}
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
      {typedMode ? <input {...nativeProps} className="input" aria-label="Type the missing words" value={typedAnswer}
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
  const refreshBasil = useRefreshBasil();
  const { speak, speechAvailable, nativeProps } = useTargetLanguage();
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
    ? builtSentence(tokenIndexes.map(position => question.tokenBank[position]), question.sentenceJoinModes) : "";
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
  const earnedText = basilEarnedText(actionResult?.basilEarned);
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
      refreshBasil();
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
      if (!taskDone(item) && !await actOnTask(item.id, "skip")) return;
    }
    onSkipRolePlay();
  };

  const submit = async () => {
    if (!allChecked || practiceSaving || checking || saved.isLoading || saved.isError) return;
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
    <div className="vocabulary-flow__progress"><ProgressTrail value={activeIndex + 1} total={content.questions.length} label={`Question ${activeIndex + 1} of ${content.questions.length}`} /><QuestionBasil amount={storedCheck?.basilEarned} /></div>
    <div className="learning-title-row"><div className="vocabulary-flow__title"><IconButton className="vocabulary-flow__back" label="Back to tasks" onClick={onClose}><ArrowLeftIcon size={20} /></IconButton><h1>{content.title}</h1></div><div className="learning-title-actions"><MissionCheatSheetLauncher missionId={content.missionId} practiceLevel={content.practiceLevel} contentVersion={content.contentVersion} languageCode={scene.languageCode} /><ExitToHome onExit={onExit} /></div></div>
    {saved.isLoading ? <InlineLoader compact label="Restoring checked answers…" /> : null}
    {saved.isError ? <div role="alert"><p>Unable to restore checked answers.</p>
      <Button variant="quiet" onClick={() => void refetchChecks()}>Retry</Button></div> : null}
    {question ? <div className="learning-section">
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
        {question.dialogue?.length ? <div className="mission-dialogue" aria-label="Conversation so far">
          {question.dialogue.map((turn, turnIndex) => <p key={`${turn.speaker}-${turnIndex}`}
            className={`mission-dialogue__turn mission-dialogue__turn--${turn.speaker}`}>
            <strong>{turn.speaker === "linguini" ? "Linguini" : turn.speaker === "server" ? "Server" : "You"}</strong>
            <span lang={scene.languageCode}>{turn.text}</span>
            {turn.translation ? <small>{turn.translation}</small> : null}
          </p>)}
        </div> : null}
        {question.planningFacts?.length ? <section className="mission-planning-facts" aria-label="Your facts">
          <strong>Your facts</strong><ul>{question.planningFacts.map((fact, position) => <li key={`${position}-${fact}`}>{fact}</li>)}</ul>
        </section> : null}
        <MissionSnapshotFacts task={task} scene={scene} />
        {isSituation && question.gapType && question.interactionType !== "sentenceBuilding" ? <A0MissionGapQuestion key={question.questionId}
          question={question} scene={scene} sceneObjects={session?.sceneObjects ?? []}
          selectedOptionId={answers[question.questionId] ?? ""}
          typedMode={Boolean(typedMode[question.questionId])}
          typedAnswer={typedAnswers[question.questionId] ?? ""}
          checked={checks[question.questionId]} retryPassed={Boolean(retryPassed[question.questionId])}
          checking={checking || saved.isLoading || saved.isError}
          scenario={question.roleplayPremise ?? undefined}
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
        <div className="mission-markers"><ScenePhoto
          scene={scene} hideWords items={markers.length ? markers.map(marker => marker.item) : questionObjects}
          activeItemId={markers.find(marker => marker.option.optionId === (checks[question.questionId]
            ? checks[question.questionId]?.isCorrect
              ? checks[question.questionId]?.answer
              : question.options.find(option => option.label === checks[question.questionId]?.correctAnswer)?.optionId
            : answers[question.questionId]))?.item.id ?? null}
          onMarkerClick={!isChecked && !checking && markers.length
            ? item => {
              const marker = markers.find(candidate => candidate.item.id === item.id);
              if (marker) {
                setAnswers(value => ({ ...value, [question.questionId]: marker.option.optionId }));
                trackAction("lesson_marker_selected", { taskId: task.id, questionId: question.questionId, marker: item.marker });
              }
            } : undefined}
        /></div>
        {question.roleplayPremise ? <div className="roleplay-premise" role="note" aria-label={`Scenario: ${roleplayScenario(question.roleplayPremise)}`}>
          <p className="roleplay-premise__text"><strong>Scenario:</strong> {roleplayScenario(question.roleplayPremise)}</p>
        </div> : null}
        {question.audioText && speechAvailable() ? <div className="spread">
          <p className="muted">{question.listenFirst && !showWritten ? "Listen before reading the prompt." : "Listen to the phrase."}</p>
          <IconButton label="Play audio" onClick={() => speak(question.audioText ?? "", scene.languageCode)}><SpeakerIcon /></IconButton>
        </div> : null}
        {question.audioText && !speechAvailable() ? <>
          <p className="small muted" role="note">Audio isn't available here, so read the phrase instead.</p>
          <p {...nativeProps} lang={nativeProps.lang ?? scene.languageCode}>{question.audioText}</p>
        </> : null}
        {question.listenFirst && !showWritten ? <Button variant="quiet" onClick={() => setRevealedPrompts(value => ({
          ...value, [question.questionId]: true,
        }))}>Show written prompt</Button> : null}
        {showWritten ? question.translation
          ? <PromptTranslation source={question.prompt} text={question.translation} lang={scene.languageCode} romanization={question.romanizations?.[question.prompt]} />
          : <><h2 {...nativeProps}>{question.prompt}</h2>{question.romanizations?.[question.prompt] ? <p className="muted" lang="und-Latn" dir="ltr">{question.romanizations[question.prompt]}</p> : null}</> : null}
        {slotText && showWritten ? <p className="mission-slot-template">
          {slotText}
        </p> : null}
        {question.interactionType === "sentenceBuilding" ? <>
          <div {...nativeProps} className="sentence-builder__answer" aria-label="Your sentence">
            {tokenIndexes.length ? tokenIndexes.map((tokenIndex, position) => <button key={`${tokenIndex}-${position}`}
              className="sentence-builder__token" disabled={isChecked || checking}
              onClick={() => setBuiltTokenIndexes(value => ({
                ...value, [question.questionId]: (value[question.questionId] ?? []).filter((_, itemIndex) => itemIndex !== position),
              }))}><span {...nativeProps}>{question.tokenBank[tokenIndex]}</span>{question.romanizations?.[question.tokenBank[tokenIndex]] ? <small lang="und-Latn" dir="ltr"> {question.romanizations[question.tokenBank[tokenIndex]]}</small> : null}</button>) : <span className="muted" dir={nativeProps.dir ? "ltr" : undefined} lang={nativeProps.lang ? "en" : undefined}>Choose the words to build your sentence.</span>}
          </div>
          <div {...nativeProps} className="chip-row" aria-label="Sentence building words">{question.tokenBank.map((token, tokenIndex) => {
            const used = tokenIndexes.includes(tokenIndex);
            return <button key={`${token}-${tokenIndex}`} className="chip" disabled={used || isChecked || checking}
              onClick={() => setBuiltTokenIndexes(value => ({
                ...value, [question.questionId]: [...(value[question.questionId] ?? []), tokenIndex],
              }))}><span {...nativeProps}>{token}</span>{question.romanizations?.[token] ? <small lang="und-Latn" dir="ltr"> {question.romanizations[token]}</small> : null}</button>;
          })}</div>
        </> : question.interactionType === "textCloze" ? <div className="field">
          <label className="field__label" htmlFor={`mission-answer-${question.questionId}`}>Your reply</label>
          <input {...nativeProps} id={`mission-answer-${question.questionId}`} className="input"
            placeholder={question.slotTemplate ?? ""}
            value={answers[question.questionId] ?? ""}
            disabled={isChecked || checking || saved.isLoading || saved.isError}
            onChange={event => setAnswers(value => ({ ...value, [question.questionId]: event.target.value }))} />
        </div> : markers.length ? null : <div className="choice-grid">{questionOptions(question, `${task.id}:${question.questionId}`).map(option => {
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
            <span {...nativeProps}>{optionText(question, option.label)}</span>{question.romanizations?.[option.label] ? <small lang="und-Latn" dir="ltr"> {question.romanizations[option.label]}</small> : null}</button>;
        })}</div>}
        {storedCheck && !retrying ? <>
          <Feedback tone={storedCheck.isCorrect || (isSituation && Boolean(retryPassed[question.questionId])) ? "good" : "warn"}>
            <div className="stack-2" role="status" aria-atomic="true">
            {task.status !== "skipped" ? <strong>{learningFeedback(storedCheck.outcome.outcome === "unassessed" ? "saved" : storedCheck.isCorrect ? "correct" : "incorrect", `${task.id}:${question.questionId}`)}</strong> : null}
            <p>{storedCheck.outcome.outcome === "unassessed" ? storedCheck.feedback ?? "Answer saved." : storedCheck.isCorrect
              ? question.correctNote ?? <>Correct!{storedCheck.outcome.correctNote ? ` ${storedCheck.outcome.correctNote}` : ""}</>
              : isSituation && retryPassed[question.questionId]
                ? "That's right. Try the phrase again."
                : isSituation
                  ? <>Not quite. The correct answer is <strong>{storedCheck.correctAnswer}</strong>{sentenceEnding(storedCheck.correctAnswer ?? "")} Tap it to try again.</>
                  : storedCheck.attemptsLeft
                    ? storedCheck.feedback ?? "Not quite. Try another answer."
                    : <>Not quite. The correct answer is <strong>{storedCheck.correctAnswer}</strong>{sentenceEnding(storedCheck.correctAnswer ?? "")}</>}</p>
            {storedCheck.feedback && storedCheck.outcome.outcome !== "unassessed" && (storedCheck.isCorrect || !storedCheck.attemptsLeft) ? <p>{storedCheck.feedback}</p> : null}
            </div>
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
    </div> : null}
    {checking ? <InlineLoader compact label="Checking your answer…" /> : null}
    {checkError ? <p role="alert">{checkError}</p> : null}
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    {actionResult && task.status !== "skipped" ? <Feedback><div className="stack-2" role="status" aria-atomic="true">
      <strong>{learningFeedback("saved", task.id)}</strong>
      {actionResult.attempt?.feedback?.message ? <p>{actionResult.attempt.feedback.message}</p> : null}
    </div></Feedback> : null}
    <BasilReward text={earnedText} />
    {terminal ? <Button block onClick={onNext}>{index < total - 1 ? "Next task" : "Finish task"}</Button>
      : question && !isChecked
        ? <Button block disabled={!answer || checking || saved.isLoading || saved.isError || practiceSaving}
          onClick={() => void check()}>{retrying ? "Check again" : "Check answer"}</Button>
      : question && activeIndex < content.questions.length - 1
        ? <Button block disabled={checking || practiceSaving || saved.isLoading || saved.isError}
          onClick={() => setActiveIndex(activeIndex + 1)}>Next question</Button>
        : <Button block disabled={!allChecked || checking || practiceSaving || saved.isLoading || saved.isError}
          onClick={() => void submit()}>Finish task</Button>}
    {!terminal ? <Button variant="quiet" block disabled={practiceSaving || checking}
      onClick={async () => { if (await actOnTask(task.id, "skip")) onNext(); }}>Skip task</Button> : null}
    {question && storedCheck && (!storedCheck.isCorrect || storedCheck.correctAnswer) ? <div className="learning-question-report"><ReportIssueLink reportType="Grammar answer" fields={[
      ["Task ID", task.id], ["Question ID", question.questionId], ["Prompt", question.prompt],
      ["Your answer", storedCheck.answer], ["Displayed solution", storedCheck.correctAnswer],
    ]} /></div> : null}
  </div>;
}

function GrammarLessonFlow({ task, index, total, onNext, onClose, onExit }: { task: SessionTask; index: number; total: number; onNext: () => void; onClose: () => void; onExit: () => void }) {
  const refreshBasil = useRefreshBasil();
  const [questionBasil, setQuestionBasil] = useState<Record<string, number>>({});
  const { speak, nativeProps, speechAvailable } = useTargetLanguage();
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
    enabled: content.kind === "grammarLesson",
  });
  const restorable = content.kind === "grammarLesson" && Boolean(content.missionId) && task.status === "completed";
  const saved = useQuery({
    queryKey: queryKeys.latestAttempt(task.id),
    queryFn: ({ signal }) => getLatestAttempt(task.id, signal),
    enabled: restorable && !Object.keys(questionResults).length,
  }).data?.attempt;
  const terminal = taskDone(task);
  const earnedText = basilEarnedText(actionResult?.basilEarned);
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
    setQuestionBasil(value => ({ ...value, ...Object.fromEntries(stored.map(item => [item.questionId, item.basilEarned ?? 0])) }));
    if (task.status === "completed") return;
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
  }, [savedChecks.data, content, task.status]);
  if (content.kind !== "grammarLesson") return null;
  const answerFor = (question: typeof content.questions[number]) => question.interactionType === "sentenceBuilding"
    ? builtSentence((builtTokenIndexes[question.questionId] ?? []).map(index => question.tokenBank[index]), question.sentenceJoinModes)
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
      setQuestionBasil(value => ({ ...value, [result.questionId]: result.basilEarned ?? 0 }));
      refreshBasil();
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
    <div className="vocabulary-flow__progress"><ProgressTrail value={activeIndex + 1} total={content.questions.length} label={`Question ${activeIndex + 1} of ${content.questions.length}`} /><QuestionBasil amount={activeQuestion ? questionBasil[activeQuestion.questionId] : undefined} /></div>
    <div className="learning-title-row"><div className="vocabulary-flow__title"><IconButton className="vocabulary-flow__back" label="Back to tasks" onClick={onClose}><ArrowLeftIcon size={20} /></IconButton><h1>{content.title}</h1></div><div className="learning-title-actions"><MissionCheatSheetLauncher missionId={content.missionId} practiceLevel={content.practiceLevel} contentVersion={content.contentVersion} languageCode={scene.languageCode} /><ExitToHome onExit={onExit} /></div></div>
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
      return <div key={question.questionId} className="learning-section">
        <Card plain><div className="stack">
      {question.instruction ? <p className="small lesson-instruction">{question.instruction}</p> : null}
      <LessonAudioPrompt question={question} languageCode={scene.languageCode}
        revealed={Boolean(revealed[question.questionId])}
        graded={results[question.questionId] !== undefined}
        onReveal={() => setRevealed(value => ({ ...value, [question.questionId]: true }))}
        inlineAudio={Boolean(question.promptTranslation)} />
      {!question.sceneObjectId && !question.displayCount && !question.boardCounts
        && (!markers.length || question.interactionType === "sentenceBuilding")
        ? <ScenePhoto scene={scene} items={[]} /> : null}
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
          ? <PromptTranslation source={question.prompt} text={question.promptTranslation} lang={scene.languageCode} audioText={question.audioText ?? question.prompt} romanization={question.romanizations?.[question.prompt]} />
          : question.translation ? <h2>{question.translation}</h2> : null}
        <div {...nativeProps} className="sentence-builder__answer" aria-label="Your sentence">
          {restored?.answers?.[question.questionId] ? <span {...nativeProps}>{restored.answers[question.questionId]}</span> : (builtTokenIndexes[question.questionId] ?? []).length ? (builtTokenIndexes[question.questionId] ?? []).map((tokenIndex, tokenPosition) => <button key={`${tokenIndex}-${tokenPosition}`} className="sentence-builder__token" disabled={terminal || practiceSaving}
            onClick={() => setBuiltTokenIndexes(value => ({ ...value, [question.questionId]: (value[question.questionId] ?? []).filter((_, index) => index !== tokenPosition) }))}><span {...nativeProps}>{question.tokenBank[tokenIndex]}</span>{question.romanizations?.[question.tokenBank[tokenIndex]] ? <small lang="und-Latn" dir="ltr"> {question.romanizations[question.tokenBank[tokenIndex]]}</small> : null}</button>) : <span className="muted" dir={nativeProps.dir ? "ltr" : undefined} lang={nativeProps.lang ? "en" : undefined}>Choose the words to build your sentence.</span>}
        </div>
        <div {...nativeProps} className="chip-row" aria-label="Sentence building words">{question.tokenBank.map((token, tokenIndex) => {
          const used = (builtTokenIndexes[question.questionId] ?? []).includes(tokenIndex);
          if (used) return null;
          return <button key={`${token}-${tokenIndex}`} className="chip" disabled={terminal || practiceSaving}
            onClick={() => setBuiltTokenIndexes(value => ({ ...value, [question.questionId]: [...(value[question.questionId] ?? []), tokenIndex] }))}><span {...nativeProps}>{token}</span>{question.romanizations?.[token] ? <small lang="und-Latn" dir="ltr"> {question.romanizations[token]}</small> : null}</button>;
        })}</div>
      </> : <>
        {writtenPromptShown(question, { revealed: Boolean(revealed[question.questionId]), graded: results[question.questionId] !== undefined, audio })
          ? question.promptTranslation
            ? <PromptTranslation source={content.focus === "sceneDescription" ? question.translation || "Choose the sentence that describes the scene." : question.prompt}
              text={question.promptTranslation} lang={question.audioText ? scene.languageCode : undefined} audioText={question.audioText ?? question.prompt} romanization={question.romanizations?.[question.prompt]} />
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
              if (marker) {
                setAnswers(value => ({ ...value, [question.questionId]: marker.option.optionId }));
                trackAction("lesson_marker_selected", { taskId: task.id, questionId: question.questionId, marker: item.marker });
              }
            }} /></div> : null}
        {!markers.length ? <div className="choice-grid">{questionOptions(question, `${task.id}:${question.questionId}`).map(option => {
          const selected = chosen[question.questionId] === option.optionId;
          const graded = results[question.questionId];
          const state = graded !== undefined && solutions[question.questionId] === option.optionId ? " choice--correct"
            : !selected ? ""
              : graded === undefined ? " choice--selected" : graded ? " choice--correct" : " choice--incorrect";
          return <button key={option.optionId} className={`choice${state}`} aria-pressed={selected} disabled={terminal || practiceSaving || checking || graded !== undefined}
            onClick={() => setAnswers(value => ({ ...value, [question.questionId]: option.optionId }))}>
            <span {...nativeProps}>{optionText(question, option.label)}</span>{question.romanizations?.[option.label] ? <small lang="und-Latn" dir="ltr"> {question.romanizations[option.label]}</small> : null}</button>;
        })}</div> : null}</>}
      </>}
      {results[question.questionId] !== undefined ? <>
        <Feedback tone={results[question.questionId] ? "good" : "warn"}><div className="stack-2" role={terminal ? undefined : "status"} aria-atomic={terminal ? undefined : true}>
          {!terminal ? <strong>{learningFeedback(outcomeFor[question.questionId]?.outcome === "unassessed" ? "saved" : results[question.questionId] ? "correct" : "incorrect", `${task.id}:${question.questionId}`)}</strong> : null}
          <p>{results[question.questionId]
          ? <>Correct!{outcomeFor[question.questionId]?.correctNote
            ? ` ${outcomeFor[question.questionId]?.correctNote}` : ""}</>
          : <>Not quite.{solutions[question.questionId] ? (() => {
            const label = question.options.find(option => option.optionId === solutions[question.questionId])?.label;
            const solution = label ? optionText(question, label) : solutions[question.questionId];
            return <> The correct answer is <strong>{solution}</strong>{sentenceEnding(solution)}</>;
          })() : null}</>}</p></div></Feedback>
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
    </div></Card></div>;
    })}
    {checking ? <InlineLoader compact label="Checking your answer…" /> : null}
    {checkError ? <p role="alert">{checkError}</p> : null}
    {(task.status !== "skipped" && (actionResult || restored || feedback)) || feedback || restored?.feedback ? <Feedback><div className="stack-2" role="status" aria-atomic="true">
      {task.status !== "skipped" ? <strong>{learningFeedback("saved", task.id)}</strong> : null}
      {feedback ?? restored?.feedback ? <p>{feedback ?? restored?.feedback}</p> : null}</div></Feedback> : null}
    <BasilReward text={earnedText} />
    {practiceError ? <p role="alert">{practiceError}</p> : null}
    {terminal ? <Button block onClick={onNext}>{index < total - 1 ? "Next task" : "Finish task"}</Button> : <>
      {activeResult === undefined
        ? <Button block disabled={!activeAnswer || practiceSaving || checking} onClick={() => void check()}>Check answer</Button>
        : activeIndex < content.questions.length - 1
          ? <Button block disabled={checking} onClick={() => setActiveIndex(value => value + 1)}>Next question</Button>
          : <Button block disabled={!answered || !allChecked || practiceSaving || checking} onClick={() => void submit()}>Finish task</Button>}
      <Button variant="quiet" block disabled={practiceSaving} onClick={async () => { if (await actOnTask(task.id, "skip")) onNext(); }}>Skip task</Button>
    </>}
    {activeQuestion && activeResult !== undefined ? <div className="learning-question-report"><ReportIssueLink reportType="Grammar answer" fields={[
      ["Task ID", task.id],
      ["Question ID", activeQuestion.questionId],
      ["Prompt", activeQuestion.translation || activeQuestion.prompt],
      ["Your answer", answerFor(activeQuestion)],
      ["Displayed solution", activeQuestion.options.find(option => option.optionId === solutions[activeQuestion.questionId])?.label ?? solutions[activeQuestion.questionId]],
    ]} /></div> : null}
  </div>;
}

function VocabularyLearningCard({ word, languageCode }: { word: VocabularyLearningWord; languageCode: string }) {
  const { speak, nativeProps, settings, speechAvailable } = useTargetLanguage();
  return <article className="flashcard learning-card vocabulary-learning-card">
    <div className="spread"><span className="label muted learning-card__meta">{word.termType === "relationship" ? "relationship" : word.partOfSpeech}{word.gender ? ` · ${word.gender}` : ""}</span>
      {(!settings || speechAvailable()) ? <IconButton className="learning-card__audio" label={`Hear ${word.targetText}`} onClick={() => {
        speak(word.targetText, languageCode);
        trackAction("vocabulary_pronunciation_clicked", { termType: word.termType });
      }}><SpeakerIcon /></IconButton> : null}</div>
    <div className="learning-card__word"><h2 {...nativeProps}>{word.targetText}</h2>{word.romanization ? <p className="muted" lang="und-Latn" dir="ltr" aria-label="Latin spelling">{word.romanization}</p> : null}<p className="muted">{word.translation}</p></div>
    {word.pluralForm ? <p className="small"><strong>Plural:</strong> {word.pluralForm}</p> : null}
    {word.phoneticText ? <p className="small muted" aria-label={settings ? "English-sound pronunciation" : "Pronunciation"}>{word.phoneticText}</p> : null}
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
  const crop = imageSize ? practiceBoardCrop(boardObject, imageSize.width, imageSize.height) : null;
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
  const crop = imageSize ? practiceBoardCrop(boardObject, imageSize.width, imageSize.height) : null;
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

function PromptTranslation({ text, source, lang, audioText, romanization }: { text?: string | null; source?: ReactNode; lang?: string; audioText?: string; romanization?: string }) {
  const { speak, speechAvailable, nativeProps } = useTargetLanguage();
  const [shown, setShown] = useState(false);
  if (!text) return null;
  const toggle = <IconButton className="prompt-translation__toggle" label={shown ? "Hide translation" : "Show translation"}
      aria-expanded={shown} onClick={() => setShown(value => !value)}>
      {shown ? <EyeIcon size={20} /> : <EyeOffIcon size={20} />}
    </IconButton>;
  const audio = audioText && lang && speechAvailable() ? <IconButton className="prompt-translation__toggle" label={`Hear ${audioText}`}
    onClick={() => speak(audioText, lang)}><SpeakerIcon size={20} /></IconButton> : null;
  if (source) return <span className="prompt-translation prompt-translation--with-source">
    <span className="prompt-translation__source"><h2 lang={lang && (nativeProps.lang ?? lang)} dir={lang && nativeProps.dir}>{source}</h2>{audio}{toggle}</span>
    {romanization ? <span className="muted" lang="und-Latn" dir="ltr">{romanization}</span> : null}
    {shown ? <span className="small muted">{text}</span> : null}
  </span>;
  return <span className="prompt-translation">
    {shown ? <span className="small muted">{text}</span> : null}{toggle}
  </span>;
}

import { Navigate, useNavigate } from "react-router-dom";
import { Button, XpPill } from "../components/ui";
import { ArrowRightIcon, BookIcon, ChatIcon, CheckIcon, CloseIcon, CountIcon, EyeIcon, HandIcon, HeartIcon, JournalIcon, MarkerIcon, PlayIcon } from "../components/icons";
import { SessionPersonalization } from "../components/SessionPersonalization";
import { ScenePhoto } from "../components/ScenePhoto";
import { useScene } from "../state/useScene";
import { finishesAfterLearning, practiceStages, taskDone, taskTitle, taskXp } from "../lib/practiceTasks";
import { useAppState } from "../state/useAppState";
import { learningFeedback } from "../lib/learningFeedback";
import { trackAction } from "../lib/analytics.ts";

function TaskAimIcon({ task }: { task: ReturnType<typeof practiceStages>["learning"][number] }) {
  const missionIcons = {
    M01: EyeIcon,
    M02: MarkerIcon,
    M03: CountIcon,
    M04: HandIcon,
    M05: HeartIcon,
    M06: ChatIcon,
  } as const;
  const MissionIcon = task.publicContent.missionId ? missionIcons[task.publicContent.missionId as keyof typeof missionIcons] : undefined;
  if (MissionIcon) return <MissionIcon size={20} />;
  if (task.kind === "sentenceBuilding" || task.kind === "syntaxExplanation") return <JournalIcon size={20} />;
  return <BookIcon size={20} />;
}

export function Learn() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, practiceSaving, practiceError, practiceStalled, retryProcessing, completeSession } = useAppState();
  if (!session) return null;
  const base = `/practice/sessions/${scene.sessionId}`;
  if (session.session.status === "completed") return <Navigate to={`${base}/summary`} replace />;
  if (["abandoned", "failed"].includes(session.session.status)) return <div className="stack"><h1>Session closed</h1><Button onClick={() => navigate("/practice")}>Choose an image</Button></div>;
  const learningTasks = practiceStages(session.tasks).learning;
  const vocabularyTask = learningTasks.find(task => task.kind === "vocabularyIntroduction");
  const vocabularyDone = vocabularyTask ? taskDone(vocabularyTask) : true;
  const vocabularySkipped = vocabularyTask?.status === "skipped";
  const vocabularyWordCount = vocabularyTask?.publicContent.kind === "vocabularyIntroduction"
    ? vocabularyTask.publicContent.words.length
    : scene.items.length;
  const tasks = learningTasks.filter(task => task.kind !== "vocabularyIntroduction");
  const completed = tasks.filter(taskDone);
  const generating = session.session.status === "generatingTasks";
  const allDone = tasks.length > 0 && tasks.every(taskDone) && !generating;
  const nextTask = tasks.find(task => !taskDone(task));

  const openTask = (taskId: string) => {
    trackAction("task_opened", { taskId });
    navigate(`${base}/learn/${taskId}`);
  };

  return (
    <div className="stack learn-page">
      <div className="stack-2">
        <div className="learning-title-row">
          <h1>Your lesson</h1>
          <Button variant="quiet" className="learning-exit" onClick={() => { trackAction("learning_exit_clicked"); navigate("/home"); }}>
            <CloseIcon size={18} /> Exit
          </Button>
        </div>
        <p className="muted">Review the words, then use them in short missions.</p>
      </div>

      {practiceError ? <p role="alert">{practiceError}</p> : null}

      <section className="lesson-scene-summary" aria-label={`${scene.title} lesson`}>
        <ScenePhoto scene={scene} items={[]} />
        <p><strong>{scene.title}</strong><span aria-hidden="true"> · </span><span>{learningTasks.length} {learningTasks.length === 1 ? "activity" : "activities"}</span></p>
      </section>

      <div className="lesson-path">
      {vocabularyTask ? <section className={`learn-words-intro${vocabularyDone && !vocabularySkipped ? " learn-words-intro--done" : ""}`} aria-label="Word review">
        <div className="learn-words-intro__heading">
          <span className="learn-words-intro__start">{vocabularyDone && !vocabularySkipped ? "Words reviewed" : "Start here"}</span>
          <div className="spread"><h2>Review the words</h2>{vocabularyDone && !vocabularySkipped ? <span className="pill pill--mastered"><CheckIcon size={16} /> Done</span> : <span className="learn-words-intro__required">Recommended first</span>}</div>
          <p className="muted">Learn the vocabulary used in your missions.</p>
          <p className="learn-words-intro__meta"><BookIcon size={18} /> {vocabularyWordCount} {vocabularyWordCount === 1 ? "word" : "words"}{taskXp(vocabularyTask) ? <><span aria-hidden="true"> · </span><XpPill {...taskXp(vocabularyTask)!} /></> : null}</p>
        </div>
        <Button block variant={vocabularyDone || vocabularySkipped ? "secondary" : undefined}
          disabled={practiceSaving || (!vocabularyDone && !vocabularySkipped && !session.translationPreview)}
          onClick={() => {
            trackAction("vocabulary_preview_started");
            navigate(vocabularyDone || vocabularySkipped ? `${base}/learn/${vocabularyTask.id}` : `${base}/learn/vocabulary-preview`);
          }}>
          <PlayIcon /> {vocabularyDone && !vocabularySkipped ? "Review again" : vocabularySkipped ? "Review words" : "Start word review"}
        </Button>
      </section> : null}

      {tasks.length ? <section className="stack-3 learn-missions" aria-label="Learning missions">
        <div className="learn-missions__heading"><h2>{vocabularyDone ? "Continue with missions" : "Then practise with missions"}</h2><p className="muted">Use the words in these short activities. You can open any mission.</p></div>
        <div className="task-list" aria-label="Learning tasks">
        {tasks.map(task => {
          const isDone = taskDone(task);
          const reward = !isDone ? taskXp(task) : null;
          return (
            <button
              key={task.id}
              type="button"
              className={`task-row${isDone ? " task-row--done" : ""}`}
              onClick={() => openTask(task.id)}
            >
              <span className={`task-row__icon`}>
                {isDone ? <CheckIcon size={18} /> : <TaskAimIcon task={task} />}
              </span>
              <span className="grow stack-2">
                <strong>{taskTitle(task)}</strong>
              </span>
              {isDone ? <span className="pill pill--mastered">{task.status === "skipped" ? "Skipped" : ""}</span> : <>
                {reward ? <XpPill {...reward} /> : null}
                <PlayIcon />
              </>}
            </button>
          );
        })}
        </div>
      </section> : null}
      </div>

      <SessionPersonalization personalization={session.personalization} languageCode={scene.languageCode} />
      {session.missionGuidance?.length ? <section className="panel-note" role="note">
        <p><strong>This photo didn't fit a mission</strong>, so this is the regular lesson.</p>
        <p className="small muted">For a mission next time: {session.missionGuidance.join(" ")}</p>
      </section> : null}

      {generating ? <section className="panel-note" role="status">
        <h2>{learningFeedback("preparing", session.session.id)}</h2>
        <p>Preparing the remaining tasks...</p>
        <p>You can learn and practise your words now.</p>
        {practiceStalled ? <div className="stack-2">
          <p>We're unable to generate more tasks right now. We'll keep working on them, so you can come back later.</p>
          <Button variant="secondary" block onClick={() => retryProcessing(session.session.id)}>Check again</Button>
        </div> : null}
      </section> : null}

      {vocabularyDone && allDone ? (
        finishesAfterLearning(session.tasks) ? <Button block disabled={practiceSaving} onClick={() => { trackAction("finish_lesson_clicked"); if (completeSession()) navigate(`${base}/summary`); }}>
          Finish lesson <ArrowRightIcon />
        </Button> : <Button block disabled={practiceSaving} onClick={() => { trackAction("play_ispy_clicked"); navigate(`${base}/ispy-1`); }}>
          Play I-Spy <ArrowRightIcon />
        </Button>
      ) : vocabularyDone ? (
        <Button block disabled={practiceSaving || !nextTask} onClick={() => nextTask && openTask(nextTask.id)}>
          {!nextTask ? "Preparing remaining tasks..." : completed.length === 0 ? "Begin tasks" : "Continue tasks"} <ArrowRightIcon />
        </Button>
      ) : null}

    </div>
  );
}

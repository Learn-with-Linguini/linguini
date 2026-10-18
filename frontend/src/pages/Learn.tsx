import { Navigate, useNavigate } from "react-router-dom";
import { Button, XpPill } from "../components/ui";
import { ArrowRightIcon, BookIcon, ChatIcon, CheckIcon, CloseIcon, CountIcon, EyeIcon, HandIcon, HeartIcon, JournalIcon, MarkerIcon, PlayIcon } from "../components/icons";
import { SessionPersonalization } from "../components/SessionPersonalization";
import { ScenePhoto } from "../components/ScenePhoto";
import { useScene } from "../state/useScene";
import { finishesAfterLearning, practiceStages, taskDone, taskTitle, taskXp } from "../lib/practiceTasks";
import { useAppState } from "../state/useAppState";

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
  const tasks = learningTasks.filter(task => task.kind !== "vocabularyIntroduction");
  const completed = tasks.filter(taskDone);
  const generating = session.session.status === "generatingTasks";
  const allDone = tasks.length > 0 && tasks.every(taskDone) && !generating;
  const nextTask = tasks.find(task => !taskDone(task));

  const openTask = (taskId: string) => {
    navigate(`${base}/learn/${taskId}`);
  };

  return (
    <div className="stack learn-page">
      <div className="stack-2">
        <div className="learning-title-row">
          <h1>Learning tasks</h1>
          <Button variant="quiet" className="learning-exit" onClick={() => navigate("/home")}>
            <CloseIcon size={18} /> Exit
          </Button>
        </div>
        <p className="muted">Build confidence with each short task.</p>
      </div>

      {practiceError ? <p role="alert">{practiceError}</p> : null}

      {!vocabularyDone && vocabularyTask ? <div className="learn-words-intro">
        <div className="learn-words-intro__photo"><ScenePhoto scene={scene} items={[]} />{taskXp(vocabularyTask) ? <XpPill {...taskXp(vocabularyTask)!} /> : null}</div>
        <Button block disabled={practiceSaving || !session.translationPreview} onClick={() => navigate(`${base}/learn/vocabulary-preview`)}>
          <PlayIcon /> Learn the words
        </Button>
      </div> : null}

      {tasks.length ? <section className="stack-3 learn-missions" aria-label="Learning missions">
        {!vocabularyDone ? <div><h2>Next missions</h2><p className="muted">Choose any mission to continue.</p></div> : null}
        <div className="task-list" aria-label="Learning tasks">
        {tasks.map(task => {
          const isDone = taskDone(task);
          const reward = !isDone ? taskXp(task) : null;
          const missionIconClass = task.publicContent.missionId ? ` task-row__icon--${task.publicContent.missionId.toLowerCase()}` : "";
          return (
            <button
              key={task.id}
              type="button"
              className={`task-row${isDone ? " task-row--done" : ""}`}
              onClick={() => openTask(task.id)}
            >
              <span className={`task-row__icon${missionIconClass}`}>
                {isDone ? <CheckIcon size={18} /> : <TaskAimIcon task={task} />}
              </span>
              <span className="grow stack-2">
                <strong>{taskTitle(task)}</strong>
              </span>
              {isDone ? <span className="pill pill--mastered">{task.status === "skipped" ? "Skipped" : ""}</span> : <>
                {reward ? <XpPill {...reward} /> : null}
                <ArrowRightIcon />
              </>}
            </button>
          );
        })}
        </div>
      </section> : null}

      <SessionPersonalization personalization={session.personalization} languageCode={scene.languageCode} />
      {session.missionGuidance?.length ? <section className="panel-note" role="note">
        <p><strong>This photo didn't fit a mission</strong>, so this is the regular lesson.</p>
        <p className="small muted">For a mission next time: {session.missionGuidance.join(" ")}</p>
      </section> : null}

      {generating ? <section className="panel-note" role="status">
        <h2>Preparing the remaining tasks...</h2>
        <p>You can learn and practise your words now.</p>
        {practiceStalled ? <Button variant="secondary" onClick={() => retryProcessing(session.session.id)}>Check again</Button> : null}
      </section> : null}

      {vocabularyDone && allDone ? (
        finishesAfterLearning(session.tasks) ? <Button block disabled={practiceSaving} onClick={() => { if (completeSession()) navigate(`${base}/summary`); }}>
          Finish lesson <ArrowRightIcon />
        </Button> : <Button block disabled={practiceSaving} onClick={() => navigate(`${base}/ispy-1`)}>
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

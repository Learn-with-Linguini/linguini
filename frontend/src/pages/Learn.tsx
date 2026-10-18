import { Navigate, useNavigate } from "react-router-dom";
import { Button, Card, XpPill } from "../components/ui";
import { ArrowRightIcon, CheckIcon, CloseIcon } from "../components/icons";
import { TranslationPreview } from "../components/TranslationPreview";
import { SessionPersonalization } from "../components/SessionPersonalization";
import { useScene } from "../state/useScene";
import { finishesAfterLearning, practiceStages, taskDone, taskTitle, taskXp } from "../lib/practiceTasks";
import { useAppState } from "../state/useAppState";

export function Learn() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, practiceSaving, practiceError, practiceStalled, retryProcessing, completeSession } = useAppState();
  if (!session) return null;
  const base = `/practice/sessions/${scene.sessionId}`;
  if (session.session.status === "completed") return <Navigate to={`${base}/summary`} replace />;
  if (["abandoned", "failed"].includes(session.session.status)) return <div className="stack"><h1>Session closed</h1><Button onClick={() => navigate("/practice")}>Choose an image</Button></div>;
  const tasks = practiceStages(session.tasks).learning;
  const completed = tasks.filter(taskDone);
  const generating = session.session.status === "generatingTasks";
  const allDone = tasks.length > 0 && tasks.every(taskDone) && !generating;
  const nextTask = tasks.find(task => !taskDone(task));
  const nextTaskIndex = nextTask ? tasks.findIndex(task => task.id === nextTask.id) : -1;

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

      <div className="learn-overview">
        <div className="learn-overview__scene">
          {session.translationPreview ? <TranslationPreview preview={session.translationPreview} scene={scene} /> : null}
          <SessionPersonalization personalization={session.personalization} languageCode={scene.languageCode} />
          {session.missionGuidance?.length ? <section className="panel-note" role="note">
            <p><strong>This photo didn't fit a mission</strong>, so this is the regular lesson.</p>
            <p className="small muted">For a mission next time: {session.missionGuidance.join(" ")}</p>
          </section> : null}
        </div>

        <section className="learn-overview__journey" aria-labelledby="lesson-journey-title">
          {nextTask ? <Card lifted className="learn-next-task">
            <span className="learn-next-task__eyebrow">Up next · {nextTaskIndex + 1} of {tasks.length}</span>
            <div className="learn-next-task__heading"><div><h2>{taskTitle(nextTask)}</h2><p>One short activity at a time.</p></div>{taskXp(nextTask) ? <XpPill {...taskXp(nextTask)!} /> : null}</div>
            <Button block disabled={practiceSaving} onClick={() => openTask(nextTask.id)}>
              {completed.length === 0 ? "Begin tasks" : "Continue lesson"} <ArrowRightIcon />
            </Button>
          </Card> : null}

          <div className="lesson-path">
            <div className="lesson-path__heading"><div><span className="small muted">Your route</span><h2 id="lesson-journey-title">Lesson journey</h2></div><strong>{completed.length}/{tasks.length}</strong></div>
            <div className="lesson-path__steps" aria-label="Learning tasks">
              {tasks.map((task, index) => {
                const isDone = taskDone(task);
                const isNext = task.id === nextTask?.id;
                return <button key={task.id} type="button" className={`lesson-path__step${isDone ? " is-done" : ""}${isNext ? " is-next" : ""}`} onClick={() => openTask(task.id)}>
                  <span className="lesson-path__marker">{isDone ? <CheckIcon size={16} /> : index + 1}</span>
                  <span><strong>{taskTitle(task)}</strong><small>{isDone ? task.status === "skipped" ? "Skipped" : "Complete" : isNext ? "Ready now" : "Coming up"}</small></span>
                  <ArrowRightIcon />
                </button>;
              })}
            </div>
          </div>

          {generating ? <section className="panel-note" role="status">
            <h2>Preparing the remaining tasks...</h2>
            <p>You can learn and practise your words now.</p>
            {practiceStalled ? <Button variant="secondary" onClick={() => retryProcessing(session.session.id)}>Check again</Button> : null}
          </section> : null}

          {allDone ? finishesAfterLearning(session.tasks) ? <Button block disabled={practiceSaving} onClick={() => { if (completeSession()) navigate(`${base}/summary`); }}>
            Finish lesson <ArrowRightIcon />
          </Button> : <Button block disabled={practiceSaving} onClick={() => navigate(`${base}/ispy-1`)}>
            Play I-Spy <ArrowRightIcon />
          </Button> : null}
        </section>
      </div>

    </div>
  );
}

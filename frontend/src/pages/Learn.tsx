import { Navigate, useNavigate } from "react-router-dom";
import { Button } from "../components/ui";
import { ArrowRightIcon, CheckIcon, CloseIcon } from "../components/icons";
import { TranslationPreview } from "../components/TranslationPreview";
import { useScene } from "../state/useScene";
import { practiceStages, taskDone, taskTitle } from "../lib/practiceTasks";
import { useAppState } from "../state/useAppState";

export function Learn() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, practiceSaving, practiceError, practiceStalled, retryProcessing } = useAppState();
  if (!session) return null;
  const base = `/practice/sessions/${scene.sessionId}`;
  if (session.session.status === "completed") return <Navigate to={`${base}/summary`} replace />;
  if (["abandoned", "failed"].includes(session.session.status)) return <div className="stack"><h1>Session closed</h1><Button onClick={() => navigate("/practice")}>Choose an image</Button></div>;
  const tasks = practiceStages(session.tasks).learning;
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

      {session.translationPreview ? <TranslationPreview preview={session.translationPreview} scene={scene} /> : null}

      <div className="task-list" aria-label="Learning tasks">
        {tasks.map((task, index) => {
          const isDone = taskDone(task);
          return (
            <button
              key={task.id}
              type="button"
              className={`task-row${isDone ? " task-row--done" : ""}`}
              onClick={() => openTask(task.id)}
            >
              <span className="task-row__index">
                {isDone ? <CheckIcon size={16} /> : index + 1}
              </span>
              <span className="grow stack-2">
                <strong>{taskTitle(task)}</strong>
              </span>
              {isDone ? <span className="pill pill--mastered">{task.status === "skipped" ? "Skipped" : ""}</span> : <ArrowRightIcon />}
            </button>
          );
        })}
      </div>

      {generating ? <section className="panel-note" role="status">
        <h2>Preparing the remaining tasks...</h2>
        <p>You can learn and practise your words now.</p>
        {practiceStalled ? <Button variant="secondary" onClick={() => retryProcessing(session.session.id)}>Check again</Button> : null}
      </section> : null}

      {allDone ? (
        <Button block disabled={practiceSaving} onClick={() => navigate(`${base}/ispy-1`)}>
          Play I-Spy <ArrowRightIcon />
        </Button>
      ) : (
        <Button block disabled={practiceSaving || !nextTask} onClick={() => nextTask && openTask(nextTask.id)}>
          {!nextTask ? "Preparing remaining tasks..." : completed.length === 0 ? "Begin tasks" : "Continue tasks"} <ArrowRightIcon />
        </Button>
      )}

    </div>
  );
}

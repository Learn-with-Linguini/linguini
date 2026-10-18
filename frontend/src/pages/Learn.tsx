import { Navigate, useNavigate } from "react-router-dom";
import { Button, XpPill } from "../components/ui";
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
  const generating = session.session.status === "generatingTasks";
  const allDone = tasks.length > 0 && tasks.every(taskDone) && !generating;
  const nextTask = tasks.find(task => !taskDone(task));
  const foundationTask = tasks[0];
  const foundationDone = foundationTask ? taskDone(foundationTask) : false;
  const practiceTasks = tasks.slice(1);
  const completedPractice = practiceTasks.filter(taskDone);

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
          {session.translationPreview ? <TranslationPreview preview={session.translationPreview} scene={scene} learningAction={foundationTask ? <div className={`learn-photo-action${foundationDone ? " is-complete" : ""}`}>
            <div className="learn-photo-action__copy">
              <span className="learn-photo-action__eyebrow">{foundationDone ? "Words ready" : "Recommended first"}</span>
              <div><strong>{taskTitle(foundationTask)}</strong><p>{foundationDone ? "You’re ready to use these words in context." : "The easiest place to begin—but every activity is open."}</p></div>
            </div>
            {foundationDone ? <span className="learn-foundation-check"><CheckIcon size={20} /></span> : <div className="learn-photo-action__controls">{taskXp(foundationTask) ? <XpPill {...taskXp(foundationTask)!} /> : null}<Button disabled={practiceSaving} onClick={() => openTask(foundationTask.id)}>Learn the words <ArrowRightIcon /></Button></div>}
          </div> : null} /> : null}
          <SessionPersonalization personalization={session.personalization} languageCode={scene.languageCode} />
          {session.missionGuidance?.length ? <section className="panel-note" role="note">
            <p><strong>This photo didn't fit a mission</strong>, so this is the regular lesson.</p>
            <p className="small muted">For a mission next time: {session.missionGuidance.join(" ")}</p>
          </section> : null}
        </div>

        <section className="learn-overview__journey" aria-labelledby="lesson-journey-title">
          {practiceTasks.length ? <div className="lesson-path">
            <div className="lesson-path__heading"><div><span className="small muted">Practice activities</span><h2 id="lesson-journey-title">Try them in the scene</h2><p>You can start any activity.</p></div><strong>{completedPractice.length}/{practiceTasks.length}</strong></div>
            {foundationDone && nextTask ? <Button block className="lesson-path__action" disabled={practiceSaving} onClick={() => openTask(nextTask.id)}>
              Continue practice <ArrowRightIcon />
            </Button> : null}
            <div className="lesson-path__steps" aria-label="Practice activities">
              {practiceTasks.map((task, index) => {
                const isDone = taskDone(task);
                const isNext = task.id === nextTask?.id;
                return <button key={task.id} type="button" className={`lesson-path__step${isDone ? " is-done" : ""}${isNext ? " is-next" : ""}`} onClick={() => openTask(task.id)}>
                  <span className="lesson-path__marker">{isDone ? <CheckIcon size={16} /> : index + 1}</span>
                  <span><strong>{taskTitle(task)}</strong><small>{isDone ? task.status === "skipped" ? "Skipped" : "Complete" : "Ready to try"}</small></span>
                  <ArrowRightIcon />
                </button>;
              })}
            </div>
          </div> : null}

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

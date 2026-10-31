import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Button } from "../components/ui";
import { BasilIcon, BookIcon, ChatIcon, CheckIcon, CloseIcon, CountIcon, EyeIcon, HandIcon, HeartIcon, JournalIcon, MarkerIcon, PlayIcon } from "../components/icons";
import { SessionPersonalization } from "../components/SessionPersonalization";
import { SceneImage } from "../components/SceneImage";
import { useScene } from "../state/useScene";
import { finishesAfterLearning, practiceStages, taskDone, taskTitle } from "../lib/practiceTasks";
import { useAppState } from "../state/useAppState";
import { useGamification } from "../state/gamification";
import { learningFeedback } from "../lib/learningFeedback";
import { trackAction } from "../lib/analytics.ts";
import type { SessionTask } from "../lib/api";
import "./Learn.css";

type IconComponent = ComponentType<{ size?: number }>;
type MissionState = "done" | "current" | "upcoming";
interface PathMission { task: SessionTask; title: string; subtitle: string; Icon: IconComponent; state: MissionState }

const MISSION_ICONS: Record<string, IconComponent> = {
  M01: EyeIcon, M02: MarkerIcon, M03: CountIcon, M04: HandIcon, M05: HeartIcon, M06: ChatIcon,
};

function missionIcon(task: SessionTask): IconComponent {
  if (task.kind === "vocabularyIntroduction") return BookIcon;
  const missionIconFor = task.publicContent.missionId ? MISSION_ICONS[task.publicContent.missionId] : undefined;
  if (missionIconFor) return missionIconFor;
  return task.kind === "sentenceBuilding" || task.kind === "syntaxExplanation" ? JournalIcon : BookIcon;
}

const STATE_LABEL: Record<MissionState, string> = { done: "done", current: "next mission", upcoming: "not started" };

export function Learn() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, practiceSaving, practiceError, practiceStalled, retryProcessing, completeSession } = useAppState();
  const badges = useGamification();
  if (!session) return null;
  const base = `/practice/sessions/${scene.sessionId}`;
  if (session.session.status === "completed") return <Navigate to={`${base}/summary`} replace />;
  if (["abandoned", "failed"].includes(session.session.status)) return <div className="stack"><h1>Session closed</h1><Button onClick={() => navigate("/practice")}>Choose an image</Button></div>;

  const learningTasks = practiceStages(session.tasks).learning;
  // Word review always leads the path and is recommended first; any mission can still be opened.
  const ordered = [
    ...learningTasks.filter(task => task.kind === "vocabularyIntroduction"),
    ...learningTasks.filter(task => task.kind !== "vocabularyIntroduction"),
  ];
  const skills = new Map(badges.data?.missions.map(mission => [mission.missionId, mission.skill]) ?? []);
  const currentIndex = ordered.findIndex(task => !taskDone(task));
  const missions: PathMission[] = ordered.map((task, index) => {
    const content = task.publicContent;
    const words = content.kind === "vocabularyIntroduction" ? content.words?.length ?? scene.items.length : 0;
    return {
      task,
      title: task.kind === "vocabularyIntroduction" ? "Learn the words" : taskTitle(task),
      subtitle: task.kind === "vocabularyIntroduction"
        ? `${words} new ${words === 1 ? "word" : "words"} for this scene`
        : (content.missionId && skills.get(content.missionId)) || ("explanation" in content && content.explanation) || "",
      Icon: missionIcon(task),
      state: taskDone(task) ? "done" : index === currentIndex ? "current" : "upcoming",
    };
  });
  const generating = session.session.status === "generatingTasks";

  return <MissionPath
    sceneTitle={scene.title}
    sceneImageUrl={scene.imageUrl}
    sessionId={session.session.id}
    missions={missions}
    generating={generating}
    saving={practiceSaving}
    onExit={() => { trackAction("learning_exit_clicked"); navigate("/home"); }}
    onOpen={mission => {
      if (mission.task.kind === "vocabularyIntroduction") {
        trackAction("vocabulary_review_started", { taskId: mission.task.id, revisiting: mission.state === "done" });
      } else {
        trackAction("task_opened", { taskId: mission.task.id });
      }
      navigate(`${base}/learn/${mission.task.id}`);
    }}
    onFinish={() => {
      if (finishesAfterLearning(session.tasks)) {
        trackAction("finish_lesson_clicked");
        if (completeSession()) navigate(`${base}/summary`);
      } else {
        trackAction("play_ispy_clicked");
        navigate(`${base}/ispy-1`);
      }
    }}
    finishLabel={finishesAfterLearning(session.tasks) ? "Done" : "Play I-Spy"}
  >
    {practiceError ? <p role="alert">{practiceError}</p> : null}
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
  </MissionPath>;
}

function MissionPath({ sceneTitle, sceneImageUrl, sessionId, missions, generating, saving, onExit, onOpen, onFinish, finishLabel, children }: {
  sceneTitle: string; sceneImageUrl: string | null; sessionId: string; missions: PathMission[];
  generating: boolean; saving: boolean; finishLabel: string; children: ReactNode;
  onExit: () => void; onOpen: (mission: PathMission) => void; onFinish: () => void;
}) {
  const current = missions.find(mission => mission.state === "current");
  const doneIds = missions.filter(mission => mission.state === "done").map(mission => mission.task.id);
  const allDone = !current && !generating && missions.length > 0;
  const earned = missions.reduce((sum, mission) => sum + (mission.task.status === "completed" ? mission.task.xpReward : 0), 0);
  const total = missions.reduce((sum, mission) => sum + mission.task.xpReward, 0);

  // Missions finished since this screen was last shown animate into their new state once.
  const seenKey = `linguini_mission_path_${sessionId}`;
  const [justDone] = useState<Set<string>>(() => {
    try {
      const seen = sessionStorage.getItem(seenKey);
      if (seen === null) return new Set();
      const before = new Set<string>(JSON.parse(seen));
      return new Set(doneIds.filter(id => !before.has(id)));
    } catch { return new Set(); }
  });
  const doneKey = doneIds.join(",");
  useEffect(() => {
    try { sessionStorage.setItem(seenKey, JSON.stringify(doneKey ? doneKey.split(",") : [])); } catch { /* animation is a nicety */ }
  }, [seenKey, doneKey]);

  const primaryLabel = allDone ? finishLabel : !current ? "Preparing remaining tasks..." : doneIds.length === 0 ? "Start" : "Continue";

  return <div className="mission-path-page">
    <div className="mission-path__topbar">
      <Button variant="quiet" className="learning-exit" onClick={onExit}><CloseIcon size={18} /> Return home</Button>
      {total > 0 ? <span className={`pill pill--xp mission-path__leaves${justDone.size ? " is-updated" : ""}`} aria-label={`${earned} of ${total} Basil earned in this scene`}>
        <BasilIcon size={18} />{earned} / {total}
      </span> : null}
    </div>

    <header className="mission-path__header">
      <h1 className="mission-path__title">{sceneTitle}</h1>
      <div className="mission-path__scene">
        <SceneImage scene={{ title: sceneTitle, imageUrl: sceneImageUrl }} className="mission-path__photo" />
      </div>
    </header>

    <ol className="mission-path" aria-label="Missions">
      {missions.map(mission => {
        const { task, Icon, state } = mission;
        const animated = justDone.has(task.id);
        return <li key={task.id} className={`mission-step mission-step--${state}${animated ? " is-just-done" : ""}${state === "current" && justDone.size ? " is-just-next" : ""}`}>
          {/* The disc and its card are one control, so either opens the mission. */}
          <button
            type="button"
            className="mission-step__button"
            aria-label={`${mission.title}, ${STATE_LABEL[state]}`}
            aria-describedby={`mission-${task.id}-detail`}
            disabled={saving}
            onClick={() => onOpen(mission)}
          >
            <span className="mission-step__column">
              <span className="mission-step__icon">
                {state === "done" ? <CheckIcon size={26} /> : <Icon size={state === "current" ? 28 : 24} />}
              </span>
            </span>
            <span className="mission-step__text">
              <strong>{mission.title}</strong>
              <span id={`mission-${task.id}-detail`}>{state === "done" ? "Done · Tap to redo" : mission.subtitle}</span>
            </span>
          </button>
        </li>;
      })}
    </ol>

    {children}

    <div className="mission-path__cta">
      <Button block disabled={saving || (!allDone && !current)} onClick={() => {
        trackAction("mission_path_primary_clicked", { label: primaryLabel });
        if (allDone) onFinish();
        else if (current) onOpen(current);
      }}><PlayIcon /> {primaryLabel}</Button>
    </div>

  </div>;
}

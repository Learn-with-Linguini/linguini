import { Navigate, useNavigate } from "react-router-dom";
import { ArrowRightIcon, CloseIcon } from "../components/icons";
import { TranslationPreview } from "../components/TranslationPreview";
import { Button } from "../components/ui";
import { practiceStages, taskDone } from "../lib/practiceTasks";
import { useAppState } from "../state/useAppState";
import { useScene } from "../state/useScene";

export function VocabularyPreview() {
  const navigate = useNavigate();
  const scene = useScene();
  const { session, practiceSaving } = useAppState();
  if (!session) return null;
  const base = `/practice/sessions/${scene.sessionId}`;
  const vocabularyTask = practiceStages(session.tasks).learning.find(task => task.kind === "vocabularyIntroduction");
  if (session.session.status === "completed") return <Navigate to={`${base}/summary`} replace />;
  if (!session.translationPreview || !vocabularyTask || taskDone(vocabularyTask)) return <Navigate to={`${base}/learn`} replace />;

  return <div className="stack vocabulary-preview-page">
    <div className="learning-title-row">
      <div><h1>Vocabulary preview</h1><p className="muted">Take a quick look, then learn each word one by one.</p></div>
      <Button variant="quiet" className="learning-exit" onClick={() => navigate("/home")}><CloseIcon size={18} /> Exit</Button>
    </div>
    <TranslationPreview preview={session.translationPreview} scene={scene} />
    <Button block disabled={practiceSaving} onClick={() => navigate(`${base}/learn/${vocabularyTask.id}`)}>
      Learn one by one <ArrowRightIcon />
    </Button>
  </div>;
}

import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui";
import { BookIcon } from "../components/icons";
import { LoadingScreen } from "../components/LoadingScreen";
import { ErrorState } from "../components/ErrorState";
import { useAppState } from "../state/useAppState";
import { useVocabularyQuery } from "../state/queries";

export function Progress() {
  const navigate = useNavigate();
  const { progress, progressLoading, progressError } = useAppState();
  const { vocabulary, vocabularyLoading, vocabularyError } = useVocabularyQuery();
  if (vocabularyLoading || progressLoading) return <LoadingScreen label="Loading progress..." />;
  if (vocabularyError || progressError || !progress) return <ErrorState title="We couldn't load your progress" message={vocabularyError ?? progressError ?? "Your progress isn't available just now."} retry={() => window.location.reload()} />;
  const snapshot = { words: vocabulary.length, mastered: vocabulary.filter(item => item.status === "mastered").length,
    scenes: new Set(progress.scenarios.map(item => item.sceneId || item.mediaAssetId)).size };

  return (
    <div className="stack progress-page">
      <div className="progress-page__header">
        <h2>Progress</h2>
      </div>
      <Button
          variant="secondary"
        className="progress-page__vocabulary"
        onClick={() => navigate("/vocabulary")}
      >
          <span className="progress-page__vocabulary-icon" aria-hidden="true">
            <BookIcon size={30} />
          </span>
          <span>My Vocabulary →</span>
        </Button>
      <p className="small muted">All-time progress</p>

      <section className="progress-overview" aria-live="polite">
        <div className="progress-overview__metric">
          <strong>{snapshot.words}</strong>
          <span>Words learned</span>
        </div>
        <div className="progress-overview__metric">
          <strong>{snapshot.mastered}</strong>
          <span>Mastered</span>
        </div>
        <div className="progress-overview__metric">
          <strong>{snapshot.scenes}</strong>
          <span>Scenes</span>
        </div>
      </section>
    </div>
  );
}

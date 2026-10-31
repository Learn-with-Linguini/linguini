import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChallengeHeadline, ChallengeTimer } from "../components/DailyChallenge";
import { ImageUpload } from "../components/ImageUpload";
import { BasilIcon } from "../components/icons";
import { InlineLoader } from "../components/LoadingScreen";
import { Button, Card } from "../components/ui";
import { createPractice } from "../lib/api";
import { trackAction } from "../lib/analytics.ts";
import { DAILY_CHALLENGE_FINISHER_BASIL, dailyChallengeKey, getDailyChallenge } from "../lib/dailyChallenge";
import { gameResourceKeys } from "../lib/gameResources";
import { friendlyError } from "../lib/queryKeys";
import { sessionDestination } from "../lib/sessionRoute";
import { useAppState } from "../state/useAppState";
import "../components/dailyChallenge.css";

export function DailyChallengePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { learner, user, activeProfile } = useAppState();
  const [uploading, setUploading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<{ asset: string; key: string } | null>(null);
  const key = dailyChallengeKey(user?.id ?? "");
  const query = useQuery({ queryKey: key, queryFn: ({ signal }) => getDailyChallenge(signal), enabled: Boolean(user?.id) });
  const data = query.data;
  const start = async (asset: string) => {
    if (starting || !activeProfile || !data) return;
    setStarting(true); setError(null);
    if (request.current?.asset !== asset) request.current = { asset, key: crypto.randomUUID() };
    trackAction("daily_challenge_session_started", { sceneKey: data.sceneKey, assetId: asset });
    try {
      const detail = await createPractice(activeProfile.id, asset, request.current.key, data.challengeDay);
      void queryClient.invalidateQueries({ queryKey: key });
      navigate(sessionDestination(detail).path);
    } catch (reason) {
      setError(friendlyError(reason));
      // A challenge that ended while the photo uploaded shows the new day's scene.
      void query.refetch();
    } finally {
      setStarting(false);
      void queryClient.invalidateQueries({ queryKey: gameResourceKeys(user?.id ?? "") });
    }
  };
  if (query.isPending) return <InlineLoader label="Loading today’s challenge" />;
  if (!data) return <div className="stack"><p role="alert">We couldn’t load today’s challenge.</p>
    <Button variant="quiet" onClick={() => { trackAction("daily_challenge_retry_clicked"); void query.refetch(); }}>Retry challenge</Button></div>;
  return <div className="daily-challenge-page">
    <Card lifted className="daily-challenge">
      <ChallengeTimer dayEndsAt={data.dayEndsAt} onEnded={() => void query.refetch()} />
      <div className="daily-challenge__body">
        <div className="daily-challenge__join">
          <ChallengeHeadline challenge={data} as="h1" />
          {data.status === "completed" ? <>
            <p className="daily-challenge__done">You’re on today’s board. Come back tomorrow for a new scene.</p>
            <Button variant="secondary" onClick={() => navigate("/ispy")}>See today’s board</Button>
          </> : <>
            <ImageUpload compact disabled={starting || !activeProfile} cameraEnabled={learner.cameraOn} onBusyChange={setUploading}
              dropzoneLabel={`Add a photo taken ${data.scenePhrase}`}
              onUploaded={image => { trackAction("daily_challenge_photo_uploaded", { sceneKey: data.sceneKey, assetId: image.id }); void start(image.id); }} />
            {starting && !uploading ? <InlineLoader label="Starting your challenge" /> : null}
            <p className="daily-challenge__note"><BasilIcon size={18} />Finish the lesson to earn at least {DAILY_CHALLENGE_FINISHER_BASIL} Basil. Rare finds earn more.</p>
          </>}
          {error ? <p role="alert">{error}</p> : null}
        </div>
      </div>
    </Card>
  </div>;
}

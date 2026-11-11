import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CHALLENGE_DETAILS_ID, ChallengeBoard, ChallengeHeadline, ChallengePrizes, ChallengeTimer, useChallengeResume } from "../components/DailyChallenge";
import { ImageUpload } from "../components/ImageUpload";
import { BasilIcon, CheckIcon, TrophyIcon } from "../components/icons";
import { InlineLoader } from "../components/LoadingScreen";
import { Button } from "../components/ui";
import { createPractice } from "../lib/api";
import { trackAction } from "../lib/analytics.ts";
import { DAILY_CHALLENGE_FINISHER_BASIL, dailyChallengeKey, getDailyChallenge, lastResultText, STEPS_CAMPAIGN_KEY } from "../lib/dailyChallenge";
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
  const query = useQuery({ queryKey: key, queryFn: ({ signal }) => getDailyChallenge(signal), enabled: Boolean(user?.id), refetchInterval: 30_000 });
  const data = query.data;
  const { resume, resumeError } = useChallengeResume(data?.sceneKey ?? "");
  const { hash } = useLocation();
  const loaded = Boolean(data);
  // "View details" on Play opens this page at the prizes and board.
  useEffect(() => {
    if (loaded && hash === `#${CHALLENGE_DETAILS_ID}`) document.getElementById(CHALLENGE_DETAILS_ID)?.scrollIntoView();
  }, [loaded, hash]);
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
  const result = lastResultText(data.lastResult);
  const isStepsCampaign = data.sceneKey === STEPS_CAMPAIGN_KEY;
  return <main className="daily-challenge-page">
    <section className="daily-challenge">
      <ChallengeTimer dayEndsAt={data.dayEndsAt} onEnded={() => void query.refetch()} />
      <div className="daily-challenge__body">
        <div className="daily-challenge__join">
          <ChallengeHeadline challenge={data} as="h1" />
          {isStepsCampaign ? <p className="daily-challenge__campaign-prize"><TrophyIcon size={22} /><span><strong>Rare finds win Grab vouchers</strong><small>Complete the lesson and get on the board.</small></span></p> : null}
          {data.status === "completed" ? <>
            <p className="daily-challenge__done"><CheckIcon size={20} /><span>You’re on the board with {data.yourWordCount} {data.yourWordCount === 1 ? "word" : "words"}. Bonuses land when the day ends. Come back tomorrow for a new scene.</span></p>
          </> : data.status === "inProgress" && data.sessionId ? <Button block onClick={() => void resume(data.sessionId!)}>Continue your challenge</Button> : <>
            <ImageUpload disabled={starting || !activeProfile} cameraEnabled={learner.cameraOn} onBusyChange={setUploading}
              onUploaded={image => { trackAction("daily_challenge_photo_uploaded", { sceneKey: data.sceneKey, assetId: image.id }); void start(image.id); }} />
            {starting && !uploading ? <InlineLoader label="Starting your challenge" /> : null}
            <p className="daily-challenge__note"><BasilIcon size={18} />Finish the lesson to earn at least {DAILY_CHALLENGE_FINISHER_BASIL} Basil. Rare finds earn more.</p>
          </>}
          {error ? <p role="alert">{error}</p> : null}
          {resumeError ? <p role="alert">{resumeError}</p> : null}
          {result ? <p className="daily-challenge__result"><TrophyIcon size={18} />{result}</p> : null}
        </div>
        <div id={CHALLENGE_DETAILS_ID} className="daily-challenge__details">
          <section className="daily-challenge__rewards" aria-labelledby="challenge-rewards-title">
            <h2 id="challenge-rewards-title">Today’s rewards</h2>
            <ChallengePrizes campaign={isStepsCampaign} />
          </section>
          <ChallengeBoard challenge={data} />
        </div>
      </div>
    </section>
  </main>;
}

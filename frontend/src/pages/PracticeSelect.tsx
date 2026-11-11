import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "../components/ui";
import { ImageUpload } from "../components/ImageUpload";
import { createPractice, getActivePractice, retryPracticeAnalysis } from "../lib/api";
import { SceneVisual } from "../components/SceneVisual";
import { SceneCatalogStatus } from "../components/SceneCatalogStatus";
import { trackAction } from "../lib/analytics.ts";
import { sessionDestination } from "../lib/sessionRoute";
import { friendlyError, queryError, queryKeys } from "../lib/queryKeys";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAppState } from "../state/useAppState";
import { useScenesQuery } from "../state/queries";
import { WalkthroughCoachmark } from "../components/WalkthroughCoachmark";
import { FIRST_LESSON_WALKTHROUGH_VERSION, needsFirstLessonWalkthrough } from "../lib/walkthrough";
import { gameResourceKeys } from "../lib/gameResources";
import { canStartNewPractice } from "../lib/practiceAvailability";
import { AnalysisScan } from "../components/AnalysisScan";
import { SceneProcessingProgress } from "../components/SceneProcessingProgress";
import type { SceneSummary } from "../data/types";

export function PracticeSelect() {
  const navigate = useNavigate();
  const location = useLocation();
  const { practiceNotice: notice, retrySessionId } = (location.state as { practiceNotice?: string; retrySessionId?: string } | null) ?? {};
  const { learner, user, activeProfile, profileSaving, saveUser } = useAppState();
  const { scenes } = useScenesQuery();
  const [sceneCollection, setSceneCollection] = useState<"nus" | "others">("nus");
  const hasNusScenes = scenes.some(scene => scene.id.startsWith("nus-"));
  const catalogScenes = hasNusScenes
    ? scenes.filter(scene => scene.id.startsWith("nus-") === (sceneCollection === "nus"))
    : scenes;
  const activeProfileId = activeProfile?.id;
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startingScene, setStartingScene] = useState<SceneSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dismissedSessionId, setDismissedSessionId] = useState<string | null>(null);
  const [walkthroughStep, setWalkthroughStep] = useState<2 | 3>(2);
  const [walkthroughDismissed, setWalkthroughDismissed] = useState(false);
  const [walkthroughError, setWalkthroughError] = useState<string | null>(null);
  const busy = useRef(false);
  const captureRef = useRef<HTMLDivElement>(null);
  const readyScenesRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const dialogTitleId = useId();
  const request = useRef<{ asset: string; key: string } | null>(null);
  const queryClient = useQueryClient();
  // Mount check consumes the shared cache; only the flows below force a fresh fetch.
  const activeCheck = useQuery({
    queryKey: queryKeys.activeSession(activeProfileId ?? ""),
    queryFn: () => getActivePractice(),
    enabled: !!activeProfileId,
  });
  const activeSession = activeProfileId ? activeCheck.data ?? null : null;
  const activeSessionId = activeSession?.session.id ?? null;
  const sessionLimitReached = (activeSession?.activeSessionCount ?? 0) >= 3;
  const resumeDialogOpen = activeSessionId !== null && dismissedSessionId !== activeSessionId && !sessionLimitReached;
  const activeCheckError = queryError(activeCheck.error);
  const activeFetch = useCallback(() => queryClient.fetchQuery({
    queryKey: queryKeys.activeSession(activeProfileId ?? ""),
    queryFn: () => getActivePractice(),
    staleTime: 0,
  }), [queryClient, activeProfileId]);
  const interactionDisabled = !canStartNewPractice({
    hasActiveProfile: !!activeProfile,
    selected,
    starting,
    sessionLimitReached,
  });
  useEffect(() => {
    if (sessionLimitReached) trackAction("practice_session_limit_shown", { openSessionCount: activeSession?.activeSessionCount ?? 3 });
  }, [activeSession?.activeSessionCount, sessionLimitReached]);
  useEffect(() => {
    if (!resumeDialogOpen) return;
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !starting) setDismissedSessionId(activeSessionId);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [activeSessionId, resumeDialogOpen, starting]);
  const start = async (asset: string) => {
    if (busy.current || !activeProfile || sessionLimitReached) return;
    busy.current = true; setSelected(true); setStarting(true); setError(null);
    if (request.current?.asset !== asset) request.current = { asset, key: crypto.randomUUID() };
    trackAction("practice_session_started", { assetId: asset });
    try {
      const detail = await createPractice(activeProfile.id, asset, request.current.key);
      navigate(sessionDestination(detail).path);
    } catch (reason) {
      setError(friendlyError(reason));
    }
    finally {
      busy.current = false; setStarting(false);
      void queryClient.invalidateQueries({ queryKey: gameResourceKeys(user?.id ?? "") });
    }
  };
  const continueActive = async () => {
    trackAction("practice_session_resumed");
    try {
      const fresh = await activeFetch();
      if (!fresh) return;
      navigate(sessionDestination(fresh).path);
    } catch (reason) { setError(friendlyError(reason)); }
  };
  const retrySaved = async (sessionId: string) => {
    if (busy.current) return;
    busy.current = true; setStarting(true); setError(null);
    trackAction("practice_analysis_retried", { sessionId });
    try {
      const detail = await retryPracticeAnalysis(sessionId);
      navigate(sessionDestination(detail).path);
    } catch (reason) {
      setError(friendlyError(reason));
    }
    finally {
      busy.current = false; setStarting(false);
      void queryClient.invalidateQueries({ queryKey: gameResourceKeys(user?.id ?? "") });
    }
  };
  const finishWalkthrough = async () => {
    setWalkthroughError(null);
    const saved = await saveUser({ walkthroughVersionSeen: FIRST_LESSON_WALKTHROUGH_VERSION });
    if (saved) setWalkthroughDismissed(true);
    else setWalkthroughError("We couldn't save this choice. Please try again.");
  };
  const walkthroughOpen = !walkthroughDismissed
    && !activeCheck.isPending
    && !activeCheckError
    && !sessionLimitReached
    && !resumeDialogOpen
    && Boolean(user?.onboardingCompleted)
    && needsFirstLessonWalkthrough(user?.walkthroughVersionSeen);
  const chooseAsset = (asset: string) => void start(asset);
  if (starting && startingScene) return <div className="stack analysis-page">
    <h1 className="analysis-progress-title">Scene analysis</h1>
    <section className="analysis-loading">
      <SceneProcessingProgress />
      <AnalysisScan scene={startingScene} />
    </section>
  </div>;
  return <div className="stack practice-select">
    <h1>Capture a scene</h1>
    {notice ? <div className="stack-2"><p role="alert">{notice}</p>{retrySessionId ? <Button variant="secondary" disabled={interactionDisabled || uploading} onClick={() => void retrySaved(retrySessionId)}>Try this photo again</Button> : null}</div> : null}
    <p className="muted">Take a photo of the world around you, or start from a ready scene.</p>
    {activeCheckError ? <p role="alert">{activeCheckError} You can still begin a new practice.</p> : null}
    {sessionLimitReached ? <div className="error-notice" role="alert">
      <div className="error-notice__copy"><strong>Finish an open practice first</strong>
        <p>You already have three unfinished practices. Continue one before uploading or choosing another scene.</p></div>
      <Button variant="secondary" onClick={() => void continueActive()}>Continue practice</Button>
    </div> : null}
    <div ref={captureRef}>
      <ImageUpload disabled={interactionDisabled} cameraEnabled={learner.cameraOn}
        onBusyChange={setUploading} onUploaded={image => { setStartingScene(null); trackAction("practice_photo_uploaded", { assetId: image.id }); chooseAsset(image.id); }} />
    </div>
    {error ? <div className="stack-2"><p role="alert">{error}</p><Button disabled={starting || uploading} onClick={() => request.current && void start(request.current.asset)}>Retry</Button></div> : null}
    {!activeProfile ? <p role="alert">Choose a learning language in Profile to start.</p> : null}
    <div className="spread practice-select__scenes-heading">
      <h2>Or practise with the below</h2>
      {hasNusScenes ? <div className="chip-row" role="group" aria-label="Scene collection">
        {(["nus", "others"] as const).map(collection => <button key={collection} type="button"
          className={`chip${sceneCollection === collection ? " chip--selected" : ""}`}
          aria-pressed={sceneCollection === collection}
          onClick={() => { setSceneCollection(collection); trackAction("practice_scene_collection_toggled", { collection }); }}>
          {collection === "nus" ? "NUS" : "Others"}
        </button>)}
      </div> : null}
    </div>
    <SceneCatalogStatus />
    <div ref={readyScenesRef} className="grid-2">
      {catalogScenes.map(scene => <button key={scene.id} type="button" className="scene-pick"
        disabled={interactionDisabled || uploading} aria-label={`Choose ${scene.title}`} onClick={() => { setStartingScene(scene); trackAction("practice_scene_selected", { sceneId: scene.id, title: scene.title }); chooseAsset(scene.mediaAssetId); }}>
        <SceneVisual scene={scene} />
        <span className="small items-center justify-center" style={{ fontWeight: 700 }}>{scene.title}</span>
      </button>)}
    </div>
    {resumeDialogOpen && activeSession ? <div className="help-modal__backdrop" onMouseDown={() => !starting && setDismissedSessionId(activeSessionId)}>
      <section ref={dialogRef} className="help-modal leave-session__dialog" role="dialog" aria-modal="true" aria-labelledby={dialogTitleId} onMouseDown={event => event.stopPropagation()}>
        <h2 id={dialogTitleId}>Continue your practice?</h2>
       
        <div className="leave-session__actions">
           <Button variant="secondary" block disabled={starting} onClick={() => setDismissedSessionId(activeSessionId)}>Begin New Practice</Button>
      
          <Button block disabled={starting} onClick={() => void continueActive()}>Continue Practice</Button>
        </div>
      </section>
    </div> : null}
    {walkthroughOpen ? (
      <WalkthroughCoachmark
        targetRef={walkthroughStep === 2 ? captureRef : readyScenesRef}
        step={walkthroughStep}
        totalSteps={3}
        title={walkthroughStep === 2 ? "Make your surroundings the lesson" : "Or start instantly"}
        description={walkthroughStep === 2
          ? "Take a photo or choose one from your device. Linguini will find useful words in the scene."
          : "Choose a ready-made scene whenever you want to practise without taking a photo."}
        nextLabel={walkthroughStep === 2 ? "Next" : "Start practising"}
        saving={profileSaving}
        error={walkthroughError}
        onBack={() => walkthroughStep === 2 ? navigate("/home") : setWalkthroughStep(2)}
        onNext={() => walkthroughStep === 2 ? setWalkthroughStep(3) : void finishWalkthrough()}
        onSkip={() => void finishWalkthrough()}
      />
    ) : null}
  </div>;
}

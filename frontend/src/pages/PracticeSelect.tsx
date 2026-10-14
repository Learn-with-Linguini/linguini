import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "../components/ui";
import { CameraIcon } from "../components/icons";
import { ImageUpload } from "../components/ImageUpload";
import { createPractice, getActivePractice, retryPracticeAnalysis } from "../lib/api";
import { SceneVisual } from "../components/SceneVisual";
import { SceneCatalogStatus } from "../components/SceneCatalogStatus";
import { sessionDestination } from "../lib/sessionRoute";
import { friendlyError, queryError, queryKeys } from "../lib/queryKeys";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAppState } from "../state/useAppState";
import { useScenesQuery } from "../state/queries";
import { WalkthroughCoachmark } from "../components/WalkthroughCoachmark";
import { FIRST_LESSON_WALKTHROUGH_VERSION, needsFirstLessonWalkthrough } from "../lib/walkthrough";
import { gameResourceKeys } from "../lib/gameResources";

export function PracticeSelect() {
  const navigate = useNavigate();
  const location = useLocation();
  const { practiceNotice: notice, retrySessionId } = (location.state as { practiceNotice?: string; retrySessionId?: string } | null) ?? {};
  const { learner, user, activeProfile, profileSaving, saveUser } = useAppState();
  const { scenes } = useScenesQuery();
  const activeProfileId = activeProfile?.id;
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState(false);
  const [starting, setStarting] = useState(false);
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
  const resumeDialogOpen = activeSessionId !== null && dismissedSessionId !== activeSessionId;
  const activeCheckError = queryError(activeCheck.error);
  const activeFetch = useCallback(() => queryClient.fetchQuery({
    queryKey: queryKeys.activeSession(activeProfileId ?? ""),
    queryFn: () => getActivePractice(),
    staleTime: 0,
  }), [queryClient, activeProfileId]);
  const interactionDisabled = selected || starting || !!activeCheckError || !activeProfile;
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
    if (busy.current || !activeProfile || activeCheckError) return;
    busy.current = true; setSelected(true); setStarting(true); setError(null);
    if (request.current?.asset !== asset) request.current = { asset, key: crypto.randomUUID() };
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
    try {
      const fresh = await activeFetch();
      if (!fresh) return;
      navigate(sessionDestination(fresh).path);
    } catch (reason) { setError(friendlyError(reason)); }
  };
  const retrySaved = async (sessionId: string) => {
    if (busy.current) return;
    busy.current = true; setStarting(true); setError(null);
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
    && !resumeDialogOpen
    && Boolean(user?.onboardingCompleted)
    && needsFirstLessonWalkthrough(user?.walkthroughVersionSeen);
  const chooseAsset = (asset: string) => void start(asset);
  return <div className="stack practice-select">
    <h1>Capture a scene</h1>
    {notice ? <div className="stack-2"><p role="alert">{notice}</p>{retrySessionId ? <Button variant="secondary" disabled={interactionDisabled || uploading} onClick={() => void retrySaved(retrySessionId)}>Try this photo again</Button> : null}</div> : null}
    <p className="muted">Take a photo of the world around you, or start from a ready scene.</p>
    <Button variant="secondary" disabled={starting || uploading} onClick={() => navigate("/ispy/friends")}>I Spy with a friend</Button>
    {activeCheckError ? <p role="alert">{activeCheckError} Reload to resume an open practice.</p> : null}
    <div ref={captureRef} className="dashed-capture">
      <span style={{ color: "var(--teal-dark)" }}><CameraIcon size={44} /></span>
      <ImageUpload compact disabled={interactionDisabled} cameraEnabled={learner.cameraOn}
        onBusyChange={setUploading} onUploaded={image => chooseAsset(image.id)} />
    </div>
    {starting ? <p role="status">Starting analysis...</p> : null}
    {error ? <div className="stack-2"><p role="alert">{error}</p><Button disabled={starting || uploading} onClick={() => request.current && void start(request.current.asset)}>Retry</Button></div> : null}
    {!activeProfile ? <p role="alert">Choose a learning language in Profile to start.</p> : null}
    <h2>Or practise with the below</h2>
    <SceneCatalogStatus />
    <div ref={readyScenesRef} className="grid-2">
      {scenes.map(scene => <button key={scene.id} type="button" className="scene-pick"
        disabled={interactionDisabled || uploading} aria-label={`Choose ${scene.title}`} onClick={() => chooseAsset(scene.mediaAssetId)}>
        <SceneVisual scene={scene} />
        <span className="small items-center justify-center" style={{ fontWeight: 700 }}>{scene.title}</span>
      </button>)}
    </div>
    {resumeDialogOpen && activeSession ? <div className="help-modal__backdrop" onMouseDown={() => !starting && setDismissedSessionId(activeSessionId)}>
      <section ref={dialogRef} className="help-modal leave-session__dialog" role="dialog" aria-modal="true" aria-labelledby={dialogTitleId} onMouseDown={event => event.stopPropagation()}>
        <h2 id={dialogTitleId}>Continue your practice?</h2>
        <p>You have a practice waiting for you. Continue where you left off, or choose a new photo.</p>
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

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, getActiveISpyGame, startISpyGame } from "../lib/api";
import type { PracticeDetail } from "../lib/api";
import { getQuickPlayPhoto, quickPlayKeys } from "../lib/homeQuickPlay";
import { gameStartError, queryError, queryKeys } from "../lib/queryKeys";
import { sessionDestination } from "../lib/sessionRoute";
import { trackAction } from "../lib/analytics";
import { MediaImage } from "./MediaImage";
import { InlineLoader } from "./LoadingScreen";
import { EyeIcon } from "./icons";
import { Button } from "./ui";
import "./HomeQuickPlay.css";

export function HomeQuickPlay({ owner, profileId }: { owner: string; profileId: string }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const mounted = useRef(true);
  const busy = useRef(false);
  const request = useRef<{ assetId: string; key: string } | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [pendingPhoto, setPendingPhoto] = useState<{ assetId: string; title: string } | null>(null);
  const photos = useQuery({ queryKey: quickPlayKeys.photos(owner, profileId), queryFn: ({ signal }) => getQuickPlayPhoto(signal),
    enabled: Boolean(owner && profileId), retry: false });
  const active = useQuery({ queryKey: quickPlayKeys.active(owner, profileId), queryFn: ({ signal }) => getActiveISpyGame(signal),
    enabled: Boolean(owner && profileId), retry: false });
  const selected = photos.data ?? null;
  const current = active.data;
  const assetId = pendingPhoto?.assetId ?? current?.session.sceneMediaAssetId ?? selected?.mediaAsset.id;
  const title = pendingPhoto?.title ?? current?.title ?? selected?.title;
  const ready = Boolean(owner && profileId);
  const loading = ready && (active.isPending || (!current && photos.isPending));
  const loadError = queryError(active.error ?? (!current ? photos.error : null));
  const empty = ready && !loading && !loadError && !current && !selected;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const open = (detail: PracticeDetail) => {
    if (!mounted.current) return;
    client.setQueryData(quickPlayKeys.active(owner, profileId), detail);
    client.setQueryData(queryKeys.activeGame(profileId), detail);
    const destination = sessionDestination(detail);
    navigate(destination.path, { state: destination.notice ? { practiceNotice: destination.notice } : undefined });
  };
  const play = async () => {
    if (!owner || !profileId || busy.current) return;
    busy.current = true; setStarting(true); setStartError(null);
    try {
      if (!request.current) {
        const existing = await getActiveISpyGame();
        if (!mounted.current) return;
        if (existing) { trackAction("home_explore_ispy_clicked", { action: "resume" }); open(existing); return; }
        client.setQueryData(quickPlayKeys.active(owner, profileId), null);
        if (!selected) return;
        request.current = { assetId: selected.mediaAsset.id, key: crypto.randomUUID() };
        setPendingPhoto({ assetId: selected.mediaAsset.id, title: selected.title });
        trackAction("home_explore_ispy_clicked", { action: "start" });
      } else trackAction("home_explore_ispy_clicked", { action: "retry" });
      const detail = await startISpyGame(profileId, request.current.assetId, request.current.key);
      request.current = null;
      open(detail);
    } catch (reason) {
      if (!mounted.current) return;
      if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500 && ![408, 429].includes(reason.status)) { request.current = null; setPendingPhoto(null); }
      setStartError(gameStartError(reason));
    } finally { busy.current = false; if (mounted.current) setStarting(false); }
  };
  const reload = () => {
    trackAction("home_quick_play_retried", { stage: active.error ? "active" : "photos" });
    if (active.error) void active.refetch();
    if (photos.error) void photos.refetch();
  };
  return <div className="home-explore-card home-quick-play">
    <button type="button" className="home-quick-play__open" disabled={starting || loading || Boolean(loadError) || empty || !profileId}
      aria-label={current ? "Continue your I-Spy game" : "Start I-Spy with your photo"} aria-busy={starting || loading} onClick={() => void play()}>
      <div className="home-explore-card__image">{assetId && title ? <MediaImage assetId={assetId} title={title} width={640} lazy /> :
        <div className="home-quick-play__placeholder" aria-hidden="true"><EyeIcon size={40} /></div>}</div>
      <div className="home-explore-card__body"><span className="home-tag home-tag--play"><EyeIcon size={14} /> Quick play</span>
        <strong>{current ? "Continue your I-Spy" : "I-Spy challenge"}</strong>
        <span>{!ready ? "Choose a learning language in Profile" : starting ? "Setting up your game…" : loading ? "Loading your photo…" : loadError ? "Your photo is unavailable" : empty ? "Add a photo to play" : title}</span>
      </div>
    </button>
    {loading ? <div className="home-quick-play__status"><InlineLoader compact label="Finding a photo for I-Spy…" /></div> : null}
    {loadError ? <div className="home-quick-play__status"><p role="alert">{loadError}</p><Button variant="quiet" onClick={reload}>Reload quick play</Button></div> : null}
    {startError ? <div className="home-quick-play__status"><p role="alert">{startError}</p><Button variant="quiet" disabled={starting} onClick={() => { trackAction("home_quick_play_retried", { stage: "start" }); void play(); }}>Retry quick play</Button></div> : null}
    {empty ? <div className="home-quick-play__status"><p className="small muted">Use one of your photos in a lesson and confirm its scene first.</p>
      <Button variant="quiet" onClick={() => { trackAction("home_quick_play_photo_lesson_clicked"); navigate("/practice"); }}>Start a photo lesson</Button></div> : null}
  </div>;
}

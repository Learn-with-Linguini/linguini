import { InlineLoader, LoadingScreen } from "../components/LoadingScreen";
import { useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Button, Card, Tabs } from "../components/ui";
import { MediaImage } from "../components/MediaImage";
import { SceneVisual } from "../components/SceneVisual";
import { SceneCatalogStatus } from "../components/SceneCatalogStatus";
import { getISpyPhotos, startISpyGame } from "../lib/api";
import { gameStartError, queryError, queryKeys } from "../lib/queryKeys";
import { sessionDestination } from "../lib/sessionRoute";
import { useAppState } from "../state/useAppState";
import { useScenesQuery } from "../state/queries";

type PhotoSource = "mine" | "preloaded";

const SOURCES: { id: PhotoSource; label: string }[] = [
  { id: "mine", label: "My photos" },
  { id: "preloaded", label: "Preloaded scenes" },
];

export function ISpyPlay() {
  const navigate = useNavigate();
  const location = useLocation();
  const notice = (location.state as { practiceNotice?: string } | null)?.practiceNotice;
  const { activeProfile } = useAppState();
  const { scenes } = useScenesQuery();
  const [source, setSource] = useState<PhotoSource>("mine");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<{ asset: string; key: string } | null>(null);
  const photos = useInfiniteQuery({
    queryKey: queryKeys.ispyPhotos(activeProfile?.id ?? ""),
    queryFn: ({ pageParam, signal }) => getISpyPhotos(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: page => page.nextCursor,
    enabled: !!activeProfile,
    staleTime: 0,
  });
  const mine = photos.data?.pages.flatMap(page => page.photos) ?? [];
  const photosError = queryError(photos.error);
  const disabled = starting || !activeProfile;
  const start = async (asset: string) => {
    if (!activeProfile || starting) return;
    setStarting(true); setError(null);
    // A network retry reuses the key; a later game on the same photo gets a fresh one.
    if (request.current?.asset !== asset) request.current = { asset, key: crypto.randomUUID() };
    try {
      const detail = await startISpyGame(activeProfile.id, asset, request.current.key);
      request.current = null;
      navigate(sessionDestination(detail).path);
    } catch (reason) {
      setError(gameStartError(reason));
    } finally { setStarting(false); }
  };
  return <div className="stack practice-select ispy-photo-picker">
    <div className="row gap-10-px">
      <h1>Choose a photo</h1>
      <div className="ispy-photo-picker__tabs">
        <Tabs options={SOURCES} value={source} onChange={setSource} />
      </div>
    </div>
    
    {!activeProfile ? <p role="alert">Choose a learning language in Profile to start.</p> : null}
    {starting ? <LoadingScreen label="Setting up your game…" /> : null}
    {error ? <p role="alert">{error}</p> : null}
    {source === "mine" ? <>
      {photos.isPending && activeProfile ? <InlineLoader label="Loading your photos…" /> : null}
      {photosError ? <div className="stack-2"><p role="alert">{photosError}</p><Button variant="secondary" onClick={() => void photos.refetch()}>Try again</Button></div> : null}
      {photos.isSuccess && !mine.length ? <Card className="ispy-photo-picker__empty"><h2>Your photos will appear here</h2><p>Use a photo in a lesson first, or choose a ready-made scene.</p><Link to="/practice">Start a photo lesson</Link></Card> : null}
      <div className="grid-2 ispy-photo-grid">
        {mine.map(photo => <button key={photo.mediaAsset.id} type="button" className={`scene-pick${photo.playable ? "" : " scene-pick--unavailable"}`}
          disabled={disabled || !photo.playable} aria-label={photo.playable ? `Play with ${photo.title}` : `${photo.title} is unavailable. Finish its scene review in a lesson before playing.`}
          onClick={() => void start(photo.mediaAsset.id)}>
          <span className="ispy-photo-grid__visual">
            <MediaImage assetId={photo.mediaAsset.id} title={photo.title} width={320} lazy />
            {!photo.playable ? <small className="ispy-photo-grid__unavailable">Finish this photo’s scene review before playing.</small> : null}
          </span>
          <span className="ispy-photo-grid__caption"><strong>{photo.title}</strong></span>
        </button>)}
      </div>
      {photos.hasNextPage ? <Button variant="secondary" disabled={photos.isFetchingNextPage} onClick={() => void photos.fetchNextPage()}>
        {photos.isFetchingNextPage ? "Loading more photos..." : "Show more photos"}
      </Button> : null}
    </> : <>
      <SceneCatalogStatus />
      <div className="grid-2 ispy-photo-grid">
        {scenes.map(scene => <button key={scene.id} type="button" className="scene-pick"
          disabled={disabled} aria-label={`Play with ${scene.title}`} onClick={() => void start(scene.mediaAssetId)}>
          <SceneVisual scene={scene} />
          <span className="ispy-photo-grid__caption"><strong>{scene.title}</strong></span>
        </button>)}
      </div>
    </>}
  </div>;
}

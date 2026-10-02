import { practiceScene } from "../lib/practiceScene";
import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, Outlet, useLocation, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getPractice, mediaImageUrl } from "../lib/api";
import type { PracticeDetail } from "../lib/api";
import { isPreTaskStep, isSessionRouteAllowed, sessionDestination, sessionLoadingCopy } from "../lib/sessionRoute";
import { queryError, queryKeys } from "../lib/queryKeys";
import { useAppState } from "../state/useAppState";
import type { Scene } from "../data/types";
import { LoadingScreen } from "./LoadingScreen";
import { ErrorState } from "./ErrorState";
import { AnalysisScan } from "./AnalysisScan";
import { TranslationPreview } from "./TranslationPreview";

export function SessionRoute() {
  const { sessionId = "" } = useParams();
  return <SessionLoader key={sessionId} id={sessionId} />;
}
function SessionLoader({ id }: { id: string }) {
  const { loadSession, learner, session, flushLearningChanges } = useAppState();
  // Leaving the session flushes deferred learning invalidations once, not per task.
  useEffect(() => () => flushLearningChanges(), [flushLearningChanges]);
  const [preview, setPreview] = useState<Scene | null>(null);
  const [detail, setDetail] = useState<PracticeDetail | null>(null);
  const location = useLocation();
  // The guard validates every navigation against the latest canonical
  // destination. Task pages are not re-validated while the pathname stays the
  // same — a learner reading their answer feedback must keep it — but the
  // pre-task steps (analysis, mic check) forward automatically when the
  // session advances so nobody is stranded on a stale waiting screen.
  const checked = useRef<{ path: string; canonical: string | null; allowed: boolean } | null>(null);
  const load = useCallback(async (signal?: AbortSignal): Promise<Scene> => {
    const initial = await getPractice(id);
    if (!signal?.aborted) setPreview(practiceScene(initial, mediaImageUrl(initial.mediaAsset.id, 1280), learner.language));
    const loaded = await loadSession(id, initial);
    setDetail(loaded);
    return practiceScene(loaded, mediaImageUrl(loaded.mediaAsset.id, 1280), learner.language);
  }, [id, loadSession, learner.language]);
  // Side-effecting session resolution: never served from or retained in cache.
  const { data, isPending: loading, error: queryErrorValue } = useQuery({
    queryKey: queryKeys.sessionScene(id),
    queryFn: ({ signal }) => load(signal),
    staleTime: 0, gcTime: 0, retry: false, refetchOnMount: "always",
  });
  const error = queryError(queryErrorValue);
  const copy = sessionLoadingCopy(location.pathname, session?.session.id === id ? session.session.status : undefined);
  const earlyReady = session?.session.id === id && ["generatingTasks", "ready", "inProgress"].includes(session.session.status)
    && session.tasks.some(task => task.kind === "vocabularyIntroduction");
  if (loading && !earlyReady && session?.session.id === id && session.session.status === "generatingTasks" && session.translationPreview) return <div className="stack analysis-page">
    <h1>Scene analysis</h1>
    <TranslationPreview preview={session.translationPreview} scene={preview ?? undefined} />
    <section role="status" className="panel-note"><h2>Generating tasks...</h2><p className="muted">Explore your translations while we prepare your practice.</p></section>
  </div>;
  if (loading && !earlyReady) return copy.scan && preview ? <div className="stack analysis-page">
    <h1>{copy.title}</h1>
    <section className="analysis-loading" aria-live="polite" aria-busy="true">
      <AnalysisScan scene={preview} />
      <div className="analysis-loading__copy"><h2>{copy.heading}</h2><p className="muted">{copy.support ?? "This will only take a moment."}</p></div>
    </section>
  </div> : <LoadingScreen label={copy.heading} />;
  if ((!data && !earlyReady) || error) return <ErrorState title="We couldn't open this practice" message={error ?? "This practice isn't available right now."} retry={() => window.location.reload()} backTo="/practice" backLabel="Choose another image" />;
  const current = session?.session.id === id
    ? practiceScene(session, mediaImageUrl(session.mediaAsset.id, 1280), learner.language)
    : data;
  const authoritative = session?.session.id === id ? session : detail;
  const canonical = authoritative ? sessionDestination(authoritative).path : null;
  const revalidate = checked.current?.path !== location.pathname
    || (checked.current.canonical !== canonical && isPreTaskStep(location.pathname));
  if (authoritative && revalidate) {
    checked.current = { path: location.pathname, canonical, allowed: isSessionRouteAllowed(authoritative, location.pathname) };
  }
  if (checked.current && !checked.current.allowed) {
    const dest = sessionDestination(authoritative!);
    return <Navigate to={dest.path} replace state={dest.notice ? { practiceNotice: dest.notice } : undefined} />;
  }
  return <Outlet context={current} />;
}

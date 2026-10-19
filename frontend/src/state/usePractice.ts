import { useCallback, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { analyzePractice, ApiError, completePractice, createPractice, getPractice, getPracticeSummary, getSceneDetail, retryPracticeAnalysis, reviewPractice, taskAction } from "../lib/api";
import type { PracticeReview } from "../lib/api";
import type { ConfirmGuessBody, PracticeDetail, SessionStatus, TaskAnswer, TaskActionResult } from "../lib/api";
import { applyTaskResult, keepClientProgress } from "../lib/practiceUpdates";
import { friendlyError, queryKeys } from "../lib/queryKeys";
import { gamificationKeys } from "../lib/gamification";
import { gameResourceKeys } from "../lib/gameResources";

const PROCESSING = ["analyzingScene", "generatingTasks"];
// Games and partly built lessons wait out slower clue calls; a fresh lesson polls quickly for task 1.
const patient = (detail: PracticeDetail) => detail.tasks.length > 0 || detail.session.mode === "ispy";

export function usePractice(userId: string, profileId: string, onLearningChanged: (scope: "task" | "session") => void) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<PracticeDetail | null>(null);
  const sessionRef = useRef<PracticeDetail | null>(null);
  const [practiceSaving, setSaving] = useState(false);
  const [practiceError, setError] = useState<string | null>(null);
  const [practiceStalled, setStalled] = useState(false);
  const busy = useRef(false);
  const completing = useRef(false);
  const learningDirty = useRef(false);
  const [completionError, setCompletionError] = useState<string | null>(null);
  const loadVersion = useRef(0);
  const sessionLoads = useRef(new Map<string, Promise<PracticeDetail>>());
  const creation = useRef<{ asset: string; key: string } | null>(null);
  const [micReady, setMicReady] = useState(false);
  const applySession = useCallback((update: PracticeDetail | null | ((current: PracticeDetail | null) => PracticeDetail | null)) => {
    const next = typeof update === "function" ? update(sessionRef.current) : update;
    sessionRef.current = next;
    setSession(next);
  }, []);
  const withClientProgress = useCallback((incoming: PracticeDetail) => keepClientProgress(sessionRef.current, incoming), []);
  const loadSession = useCallback((id: string, initial?: PracticeDetail) => {
    const existing = sessionLoads.current.get(id);
    if (existing) return existing;
    const request = (async () => {
    const version = ++loadVersion.current;
    setStalled(false);
    let data = withClientProgress(initial ?? await getPractice(id));
    if (data.session.status === "created") {
      try { data = withClientProgress(await analyzePractice(id)); }
      catch (error) {
        // Another request may have claimed the session; fall back to polling.
        if (!(error instanceof ApiError && error.status === 409)) throw error;
        data = withClientProgress(await getPractice(id));
      }
    }
    // Once task 1 is usable, keep checking in the background through slower
    // lesson/clue calls and their retries (up to five minutes).
    if (version === loadVersion.current) applySession(data);
    // Scene analysis can legitimately take a little while for a phone photo.
    // Keep its scan visible for two minutes; only a returned failure or that
    // timeout should offer a retry.
    const maxAttempts = data.session.status === "analyzingScene" ? 400 : patient(data) ? 200 : 40;
    for (let attempt = 0; attempt < maxAttempts && PROCESSING.includes(data.session.status); attempt += 1) {
      // Poll quickly until the first vocabulary task is committed, then use a
      // slower cadence while the remaining AI calls finish in the background.
      await new Promise(resolve => setTimeout(resolve, patient(data) ? 1500 : 300));
      if (version !== loadVersion.current) break;
      data = withClientProgress(await getPractice(id));
      if (version === loadVersion.current) applySession(data);
    }
    if (version === loadVersion.current) {
      applySession(data);
      setStalled(PROCESSING.includes(data.session.status));
      void queryClient.invalidateQueries({ queryKey: gameResourceKeys(userId) });
      void queryClient.invalidateQueries({ queryKey: gamificationKeys.account(userId) });
    }
    return data;
    })();
    sessionLoads.current.set(id, request);
    const clear = () => {
      if (sessionLoads.current.get(id) === request) sessionLoads.current.delete(id);
    };
    void request.then(clear, clear);
    return request;
  }, [applySession, withClientProgress, queryClient, userId]);
  const retryProcessing = useCallback(async (id: string) => {
    setError(null);
    try { await loadSession(id); }
    catch (error) {
      setError(friendlyError(error));
      setStalled(true);
    }
  }, [loadSession]);
  const retryAnalysis = useCallback(async (id: string) => {
    if (busy.current) return;
    busy.current = true; setSaving(true); setError(null);
    let data: PracticeDetail;
    try {
      try { data = await retryPracticeAnalysis(id); }
      catch (error) {
        // A concurrent retry or a changed session: show its current state.
        if (!(error instanceof ApiError && error.code === "practice_conflict")) throw error;
        data = await getPractice(id);
      }
    } catch (error) {
      setError(friendlyError(error));
      return;
    } finally {
      busy.current = false; setSaving(false);
      void queryClient.invalidateQueries({ queryKey: gameResourceKeys(userId) });
      void queryClient.invalidateQueries({ queryKey: gamificationKeys.account(userId) });
    }
    try { await loadSession(id, data); }
    catch (error) { setError(friendlyError(error)); }
  }, [loadSession, queryClient, userId]);
  const startSession = useCallback(async (sceneId: string) => {
    const scene = await getSceneDetail(sceneId);
    if (creation.current?.asset !== scene.mediaAssetId) creation.current = { asset: scene.mediaAssetId, key: crypto.randomUUID() };
    const result = await createPractice(profileId, scene.mediaAssetId, creation.current.key);
    void queryClient.invalidateQueries({ queryKey: gameResourceKeys(userId) });
      void queryClient.invalidateQueries({ queryKey: gamificationKeys.account(userId) });
    creation.current = null;
    return result;
  }, [profileId, queryClient, userId]);
  const actOnTask = useCallback(async (taskId: string, action: "complete" | "skip" | "attempts" | "confirm-guess", answer?: TaskAnswer | ConfirmGuessBody, key?: string): Promise<TaskActionResult | null> => {
    if (!session || busy.current) return null;
    busy.current = true; setSaving(true); setError(null);
    try {
      const result = await taskAction(taskId, action, answer ? { ...answer, idempotencyKey: key } : {});
      applySession(value => applyTaskResult(value, session.session.id, result));
      learningDirty.current = true;
      void queryClient.invalidateQueries({ queryKey: gameResourceKeys(userId) });
      void queryClient.invalidateQueries({ queryKey: gamificationKeys.account(userId) });
      return result;
    } catch (e) {
      setError(friendlyError(e));
      if (e instanceof ApiError && e.code === "task_conflict" && sessionRef.current?.session.id === session.session.id) {
        try {
          const refreshed = await loadSession(session.session.id);
          const status = refreshed.tasks.find(task => task.id === taskId)?.status;
          if (status === "completed" || status === "skipped") setError(null);
        } catch {
          // Keep the conflict visible when the saved task cannot be recovered.
        }
      }
      return null;
    }
    finally { busy.current = false; setSaving(false); }
  }, [session, applySession, loadSession, queryClient, userId]);
  const flushLearningChanges = useCallback(() => {
    if (learningDirty.current) {
      learningDirty.current = false;
      onLearningChanged("session");
    }
  }, [onLearningChanged]);
  const completion = useMutation({
    mutationFn: ({ sessionId }: { sessionId: string; previousStatus: SessionStatus }) => completePractice(sessionId),
    onError: (error, { sessionId, previousStatus }) => {
      applySession(current => current?.session.id === sessionId
        ? { ...current, session: { ...current.session, status: previousStatus } }
        : current);
      setCompletionError(friendlyError(error));
    },
    onSuccess: (completed, { sessionId }) => {
      applySession(current => current?.session.id === completed.id
        ? { ...current, session: { ...current.session, status: completed.status as SessionStatus } }
        : current);
      flushLearningChanges();
      void queryClient.invalidateQueries({ queryKey: gameResourceKeys(userId) });
      void queryClient.invalidateQueries({ queryKey: gamificationKeys.account(userId) });
      // Refetch the final reward total, and warm the cache when the summary screen has
      // not mounted yet so it renders without a visible fetch.
      void queryClient.invalidateQueries({ queryKey: queryKeys.sessionSummary(sessionId) });
      void queryClient.prefetchQuery({
        queryKey: queryKeys.sessionSummary(sessionId),
        queryFn: () => getPracticeSummary(sessionId),
      });
    },
    onSettled: () => { completing.current = false; },
  });
  const startCompletion = useCallback(() => {
    if (!session || completing.current) return false;
    completing.current = true;
    setCompletionError(null);
    const previousStatus = session.session.status;
    // The route guard only sends /summary when status is "completed", so the
    // optimistic status must land synchronously before the caller navigates.
    applySession(current => current?.session.id === session.session.id
      ? { ...current, session: { ...current.session, status: "completed" } }
      : current);
    completion.mutate({ sessionId: session.session.id, previousStatus });
    return true;
  }, [session, completion.mutate, applySession]);
  const completeSession = startCompletion;
  const retryCompletion = useCallback(() => { startCompletion(); }, [startCompletion]);
  const saveReview = useCallback(async (review: PracticeReview) => {
    if (!session || busy.current) return false;
    busy.current = true; setSaving(true); setError(null);
    const previous = session;
    applySession(current => current?.session.id === session.session.id
      ? { ...current, session: { ...current.session, status: "generatingTasks" } }
      : current);
    try {
      // The review response can still report awaitingObjectReview while the
      // backend commits; keeping the optimistic status stops the word list
      // from flashing back in.
      const detail = withClientProgress(await reviewPractice(session.session.id, review));
      applySession(current => current?.session.id === detail.session.id ? detail : current);
      // Poll in the background while analysis displays the translating screen.
      // SessionRoute forwards to the mic check when this resolves as ready.
      if (PROCESSING.includes(detail.session.status)) void loadSession(session.session.id);
      return true;
    } catch (error) {
      applySession(current => current?.session.id === previous.session.id ? previous : current);
      setError(friendlyError(error));
      return false;
    } finally { busy.current = false; setSaving(false); }
  }, [session, loadSession, applySession, withClientProgress]);
  return { session, practiceSaving, practiceError, practiceStalled, startSession, loadSession, retryProcessing, retryAnalysis, actOnTask, completeSession, completionPending: completion.isPending, completionError, retryCompletion, flushLearningChanges, saveReview, micReady, setMicReady };
}

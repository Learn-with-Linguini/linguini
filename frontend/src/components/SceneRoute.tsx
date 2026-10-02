import { useCallback } from "react";
import { Navigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getActivePractice } from "../lib/api";
import { sessionDestination } from "../lib/sessionRoute";
import { queryError, queryKeys } from "../lib/queryKeys";
import { useAppState } from "../state/useAppState";
import { LoadingScreen } from "./LoadingScreen";
import { ErrorState } from "./ErrorState";

export function SceneRoute() {
  const { sceneId = "" } = useParams();
  const { startSession } = useAppState();
  const load = useCallback(async () => {
    const active = await getActivePractice();
    return active?.sceneId === sceneId ? active : await startSession(sceneId);
  }, [sceneId, startSession]);
  // Side-effecting session resolution: never served from or retained in cache.
  const { data, error: queryErrorValue } = useQuery({
    queryKey: queryKeys.sceneSession(sceneId),
    queryFn: load,
    staleTime: 0, gcTime: 0, retry: false, refetchOnMount: "always",
  });
  const error = queryError(queryErrorValue);
  if (error) return <ErrorState title="We couldn't open that scene" message={error} retry={() => window.location.reload()} backTo="/practice" backLabel="Choose another image" />;
  if (!data) return <LoadingScreen label="Loading session..." />;
  return <Navigate replace to={sessionDestination(data).path} />;
}

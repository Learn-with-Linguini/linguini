import { useQuery, useQueryClient } from "@tanstack/react-query";
import { gameResourceKeys } from "../lib/gameResources";
import { gamificationKeys, getChefStandings, getGamification, getMissionProgress } from "../lib/gamification";
import { useAppState } from "./useAppState";

export function useGamification() {
  const { user, activeProfile } = useAppState();
  return useQuery({
    queryKey: gamificationKeys.summary(user?.id ?? "", activeProfile?.id ?? ""),
    queryFn: ({ signal }) => getGamification(activeProfile!.id, signal),
    enabled: Boolean(user?.id && activeProfile?.id), refetchInterval: 60_000,
  });
}

export function useMissionProgress(sessionId: string, enabled = true) {
  const { user } = useAppState();
  return useQuery({
    queryKey: gamificationKeys.mission(user?.id ?? "", sessionId),
    queryFn: ({ signal }) => getMissionProgress(sessionId, signal),
    enabled: Boolean(user?.id && sessionId) && enabled,
  });
}

export function useChefStandings() {
  const { user } = useAppState();
  return useQuery({
    queryKey: gamificationKeys.chefs(user?.id ?? ""),
    queryFn: ({ signal }) => getChefStandings(signal),
    enabled: Boolean(user?.id), refetchInterval: 60_000,
    refetchOnWindowFocus: true, refetchOnReconnect: true,
  });
}

export function useRefreshBasil() {
  const { user } = useAppState();
  const client = useQueryClient();
  return () => {
    if (!user?.id) return;
    void client.invalidateQueries({ queryKey: gamificationKeys.account(user.id) });
    void client.invalidateQueries({ queryKey: gameResourceKeys(user.id) });
  };
}

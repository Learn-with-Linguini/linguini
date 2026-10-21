import { useQuery } from "@tanstack/react-query";
import { getJournals, getScenes, getVocabulary } from "../lib/api";
import { queryError, queryKeys } from "../lib/queryKeys";
import { useAppState } from "./useAppState";

export function useVocabularyQuery() {
  const { activeProfile } = useAppState();
  const query = useQuery({
    queryKey: queryKeys.vocabulary(activeProfile?.id ?? ""),
    queryFn: ({ signal }) => getVocabulary(signal),
  });
  return {
    vocabulary: query.data ?? [],
    vocabularyLoading: query.isPending,
    vocabularyError: queryError(query.error),
  };
}

export function useJournalsQuery() {
  const { activeProfile } = useAppState();
  const query = useQuery({
    queryKey: queryKeys.journals(activeProfile?.id ?? ""),
    queryFn: ({ signal }) => getJournals(signal),
  });
  return {
    journal: query.data ?? [],
    journalLoading: query.isPending,
    journalError: queryError(query.error),
  };
}

export function useScenesQuery() {
  const query = useQuery({
    queryKey: queryKeys.scenes,
    queryFn: ({ signal }) => getScenes(signal),
  });
  return {
    scenes: query.data ?? [],
    scenesLoading: query.isPending,
    scenesError: queryError(query.error),
  };
}

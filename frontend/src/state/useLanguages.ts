import { useQuery } from "@tanstack/react-query";
import { getLanguages } from "../lib/api";
import { queryKeys } from "../lib/queryKeys";

export function useLanguages() {
  return useQuery({
    queryKey: queryKeys.languages,
    queryFn: ({ signal }) => getLanguages(signal),
    staleTime: 24 * 60 * 60 * 1000,
  });
}

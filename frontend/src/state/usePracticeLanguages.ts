import { useQuery } from "@tanstack/react-query";
import { getPackPracticeLanguages } from "../lib/api";
import { profileLanguageChoices } from "../lib/languageChoices";
import { queryKeys } from "../lib/queryKeys";

export function usePracticeLanguages(activeCode: string) {
  const query = useQuery({ queryKey: queryKeys.practiceLanguages, queryFn: ({ signal }) => getPackPracticeLanguages(signal) });
  return { ...query, choices: profileLanguageChoices(query.data ?? [], activeCode) };
}

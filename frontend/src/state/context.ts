import { createContext } from "react";
import type { useAccount } from "./useAccount";
import type { usePractice } from "./usePractice";
import type { JournalDraft } from "../lib/api";
import type { JournalEntry, VocabStatus } from "../data/types";
import type { ProgressResponse } from "../lib/api";

export type Learner = ReturnType<typeof useAccount>["learner"];

export type AppState = ReturnType<typeof usePractice> & Pick<ReturnType<typeof useAccount>, "user" | "activeProfile" | "languageProfiles" | "activateLanguageProfile" | "profileSaving" | "profileError" | "setLanguage" | "saveUser" | "saveProfileSettings" | "startProfileSettingsSave" | "saveLanguageProfile" | "completeOnboarding"> & {
  progress: ProgressResponse | null;
  progressError: string | null;
  progressLoading: boolean;
  learner: Learner;
  xp: number;
  setVocabStatus: (id: string, status: VocabStatus) => void;
  journalSaving: boolean;
  journalSaveError: string | null;
  saveJournalEntry: (draft: JournalDraft, id?: string, date?: string) => Promise<JournalEntry | null>;
};

export const AppStateContext = createContext<AppState | null>(null);

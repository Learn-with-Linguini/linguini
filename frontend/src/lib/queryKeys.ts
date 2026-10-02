export const queryKeys = {
  account: ["account"] as const,
  scenes: ["scenes"] as const,
  vocabulary: (profileId: string) => ["vocabulary", profileId] as const,
  progress: (profileId: string) => ["progress", profileId] as const,
  journals: (profileId: string) => ["journals", profileId] as const,
  activeSession: (profileId: string) => ["session", "active", profileId] as const,
  journal: (id: string) => ["journal", id] as const,
  journalDayContext: (date: string) => ["journal", "day", date] as const,
  sessionScene: (sessionId: string) => ["session", sessionId, "scene"] as const,
  sceneSession: (sceneId: string) => ["scene", sceneId, "session"] as const,
  sessionSummary: (sessionId: string) => ["session", sessionId, "summary"] as const,
};

export function friendlyError(error: unknown): string {
  if (
    typeof error === "object"
    && error !== null
    && "status" in error
    && typeof error.status === "number"
  ) {
    const apiError = error as { status: number; code?: unknown };
    const codeMessages: Record<string, string> = {
      no_active_language: "Choose a learning language in Profile, then try again.",
      active_session_limit_reached: "You can keep up to three unfinished practices open. Finish or leave one before starting another.",
      practice_conflict: "This practice has changed. Refresh the page and try again.",
      task_conflict: "That activity has already been updated. Refresh to see where you are now.",
      journal_conflict: "This journal entry changed while you were editing. Refresh and try again.",
      practice_not_found: "We couldn't find that practice. Choose another photo to continue.",
      scene_not_found: "That ready scene is no longer available. Please choose another one.",
      media_url_error: "We couldn't load that photo just now. Please try again.",
      scene_analysis_failed: "We couldn't read that photo. Try another photo when you're ready.",
      learning_task_generation_failed: "We couldn't prepare the next activity. Please try again.",
    };
    if (typeof apiError.code === "string" && codeMessages[apiError.code]) return codeMessages[apiError.code];
    if (apiError.status === 401) return "Your sign-in has expired. Please sign in again.";
    if (apiError.status === 403) return "You don't have access to that yet.";
    if (apiError.status === 404) return "We couldn't find that. It may have been removed.";
    if (apiError.status === 429) return "Things are a little busy. Please wait a moment and try again.";
    if (apiError.status >= 500) return "Something went wrong on our side. Please try again in a moment.";
    return "We couldn't complete that just now. Please try again.";
  }
  return error instanceof Error
    ? "We couldn't connect just now. Check your connection and try again."
    : "We couldn't load this right now. Please try again.";
}

export function queryError(error: unknown): string | null {
  return error ? friendlyError(error) : null;
}

import { createClient, type Session } from "@supabase/supabase-js";

const env = (import.meta.env ?? {}) as Record<string, string | undefined>;
const url = env.VITE_SUPABASE_URL;
const anonKey = env.VITE_SUPABASE_ANON_KEY;

/** The publishable anon key is designed to be used by the browser. */
export const supabase = url && anonKey ? createClient(url, anonKey) : null;

export const isSupabaseConfigured = supabase !== null;

export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function waitForAccessToken(signal?: AbortSignal): Promise<string | null> {
  const abortError = () => signal?.reason ?? new DOMException("Aborted", "AbortError");
  let token: string | null;
  if (signal) {
    if (signal.aborted) throw abortError();
    const tokenPromise = getAccessToken();
    token = await new Promise((resolve, reject) => {
      let settled = false;
      const settle = (callback: () => void) => {
        if (settled) return;
        settled = true;
        signal.removeEventListener("abort", onAbort);
        callback();
      };
      const onAbort = () => settle(() => reject(abortError()));
      signal.addEventListener("abort", onAbort, { once: true });
      if (signal.aborted) {
        onAbort();
        return;
      }
      void tokenPromise.then(
        value => settle(() => resolve(value)),
        error => settle(() => reject(error)),
      );
    });
  } else {
    token = await getAccessToken();
  }
  if (token || !supabase) return token;

  return new Promise((resolve, reject) => {
    let settled = false;
    let unsubscribe: (() => void) | null = null;
    const settle = (callback: () => void) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener("abort", onAbort);
      if (unsubscribe) unsubscribe();
      callback();
    };
    const onAbort = () => settle(() => reject(abortError()));
    signal?.addEventListener("abort", onAbort, { once: true });
    if (signal?.aborted) {
      onAbort();
      return;
    }
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.access_token) settle(() => resolve(session.access_token));
    });
    unsubscribe = () => data.subscription.unsubscribe();
    if (settled) unsubscribe();
  });
}

export type { Session };

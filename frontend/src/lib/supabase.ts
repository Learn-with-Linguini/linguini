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

export type { Session };

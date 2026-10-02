import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "../components/ui";
import { isSupabaseConfigured, supabase } from "../lib/supabase.ts";
import { useAuth } from "../state/Auth";

function authenticationMessage(message: string) {
  const normalized = message.toLowerCase();
  if (normalized.includes("invalid login") || normalized.includes("invalid credentials")) {
    return "That email and password don't match. Try again or create an account.";
  }
  if (normalized.includes("email not confirmed")) {
    return "Confirm your email first, then come back here to sign in.";
  }
  if (normalized.includes("already registered")) {
    return "An account already uses that email. Try signing in instead.";
  }
  if (normalized.includes("rate limit") || normalized.includes("too many")) {
    return "Please wait a moment before trying again.";
  }
  return "We couldn't complete that sign-in request. Please try again.";
}

export function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { session, loading } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">(searchParams.get("mode") === "signup" ? "signup" : "signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const requestedPath = (location.state as { from?: string } | null)?.from;

  useEffect(() => {
    if (session && !loading) navigate("/onboarding", { replace: true, state: { from: requestedPath } });
  }, [loading, navigate, requestedPath, session]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) return;
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const response = mode === "signin"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: `${window.location.origin}/login` },
        });
      if (response.error) {
        setError(authenticationMessage(response.error.message));
        return;
      }
      if (mode === "signup") {
        if (response.data.session) {
          navigate("/onboarding", { replace: true, state: { from: requestedPath } });
          return;
        }
        setMessage("Check your email to confirm your account. When you sign in, we’ll take you straight to setup.");
      }
    } catch {
      setError("We couldn't connect right now. Please check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return <div className="stack">
    <div className="center-text stack-2" style={{ alignItems: "center" }}>
      <img className="mascot" src="/linguini-logo.png" width={120} height={120} alt="Linguini mascot" />
      <h1>{mode === "signin" ? "Welcome back" : "Create your account"}</h1>
      <p className="muted">{mode === "signin" ? "Sign in to continue learning." : "Start learning words from your world."}</p>
    </div>
    {!isSupabaseConfigured ? <p role="alert">Sign-in is being set up right now. Please try again shortly.</p> : null}
    {isSupabaseConfigured ? <form className="stack" onSubmit={event => void submit(event)}>
      <label className="field">
        <span className="field__label">Email</span>
        <input className="input" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required />
      </label>
      <label className="field">
        <span className="field__label">Password</span>
        <input className="input" type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} value={password} onChange={event => setPassword(event.target.value)} minLength={6} required />
      </label>
      {error ? <p role="alert">{error}</p> : null}
      {message ? <p role="status">{message}</p> : null}
      <Button type="submit" block disabled={submitting}>{submitting ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}</Button>
    </form> : null}
    <p className="small muted center-text">
      {mode === "signin" ? "New to Linguini? " : "Already have an account? "}
      <button type="button" className="btn btn--quiet" onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(null); setMessage(null); }}>
        {mode === "signin" ? "Create an account" : "Sign in"}
      </button>
    </p>
  </div>;
}

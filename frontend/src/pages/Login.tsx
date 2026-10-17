import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "../components/ui";
import { authenticationMessage } from "../lib/authMessages.ts";
import { isSupabaseConfigured, supabase } from "../lib/supabase.ts";
import { useAuth } from "../state/Auth";

export function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { session, loading } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup" | "forgot">(() => {
    const requested = searchParams.get("mode");
    if (requested === "signup") return "signup";
    if (requested === "forgot") return "forgot";
    return "signin";
  });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(() =>
    searchParams.get("reset") === "success"
      ? "Password updated successfully. Please sign in with your new password."
      : null
  );
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
      if (mode === "forgot") {
        const response = await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: `${window.location.origin}/reset-password`,
        });
        if (response.error) {
          setError(authenticationMessage(response.error.message));
          return;
        }
        setMessage("Check your email for a link to reset your password. It may take a minute to arrive.");
        return;
      }
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
      <h1>
        {mode === "signin" ? "Welcome back" : mode === "signup" ? "Create your account" : "Reset your password"}
      </h1>
      <p className="muted">
        {mode === "signin"
          ? "Sign in to continue learning."
          : mode === "signup"
            ? "Start learning words from your world."
            : "Enter your email and we’ll send you a link to reset your password."}
      </p>
    </div>
    {!isSupabaseConfigured ? <p role="alert">Sign-in is being set up right now. Please try again shortly.</p> : null}
    {isSupabaseConfigured ? <form className="stack" onSubmit={event => void submit(event)}>
      <label className="field">
        <span className="field__label">Email</span>
        <input className="input" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required />
      </label>
      {mode !== "forgot" ? (
        <label className="field">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "var(--space-2)" }}>
            <span className="field__label">Password</span>
            {mode === "signin" ? (
              <button
                type="button"
                className="btn btn--quiet"
                style={{ fontSize: "0.85rem", padding: 0, height: "auto", minHeight: "unset" }}
                onClick={() => { setMode("forgot"); setError(null); setMessage(null); }}
              >
                Forgot password?
              </button>
            ) : null}
          </div>
          <input className="input" type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} value={password} onChange={event => setPassword(event.target.value)} minLength={6} required />
        </label>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      {message ? <p role="status">{message}</p> : null}
      <Button type="submit" block disabled={submitting}>
        {submitting ? "Please wait…" : mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Send reset link"}
      </Button>
    </form> : null}
    <p className="small muted center-text">
      {mode === "forgot" ? (
        <>
          Remember your password?{" "}
          <button type="button" className="btn btn--quiet" onClick={() => { setMode("signin"); setError(null); setMessage(null); }}>
            Sign in
          </button>
        </>
      ) : mode === "signin" ? (
        <>
          New to Linguini?{" "}
          <button type="button" className="btn btn--quiet" onClick={() => { setMode("signup"); setError(null); setMessage(null); }}>
            Create an account
          </button>
        </>
      ) : (
        <>
          Already have an account?{" "}
          <button type="button" className="btn btn--quiet" onClick={() => { setMode("signin"); setError(null); setMessage(null); }}>
            Sign in
          </button>
        </>
      )}
    </p>
  </div>;
}

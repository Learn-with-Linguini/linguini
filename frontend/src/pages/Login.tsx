import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "../components/ui";
import { trackAction } from "../lib/analytics.ts";
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
    const requested = searchParams.get("mode");
    if (requested === "signup") setMode("signup");
    else if (requested === "forgot") setMode("forgot");
    else setMode("signin");
  }, [searchParams]);

  useEffect(() => {
    if (session && !loading) navigate("/onboarding", { replace: true, state: { from: requestedPath } });
  }, [loading, navigate, requestedPath, session]);

  const switchMode = (newMode: "signin" | "signup" | "forgot") => {
    setMode(newMode);
    setError(null);
    setMessage(null);
    navigate(`/login?mode=${newMode}`);
  };

  async function signInWithGoogle() {
    if (!supabase) return;
    setError(null);
    setMessage(null);
    setSubmitting(true);
    trackAction("google_signin_clicked");
    try {
      const { error: oauthError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/login`,
        },
      });
      if (oauthError) {
        setError(authenticationMessage(oauthError.message));
        setSubmitting(false);
      }
    } catch {
      setError("We couldn't connect right now. Please check your connection and try again.");
      setSubmitting(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) return;
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      if (mode === "forgot") {
        trackAction("forgot_password_requested");
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
      if (mode === "signin") {
        trackAction("login_submitted", { method: "email" });
      } else {
        trackAction("signup_submitted", { method: "email" });
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
    {isSupabaseConfigured && mode !== "forgot" ? (
      <>
        <button
          type="button"
          className="btn btn--google"
          disabled={submitting}
          onClick={() => void signInWithGoogle()}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
            <path fill="#4285F4" d="M17.64 9.2c0-.63-.06-1.25-.16-1.84H9v3.49h4.84a4.14 4.14 0 0 1-1.8 2.71v2.26h2.92c1.71-1.57 2.68-3.89 2.68-6.62z"/>
            <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.87-3.04.87-2.34 0-4.33-1.58-5.04-3.71H.95v2.33C2.43 15.68 5.48 18 9 18z"/>
            <path fill="#FBBC05" d="M3.96 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.28-1.72V4.95H.95A8.99 8.99 0 0 0 0 9c0 1.45.35 2.82.95 4.05l3.01-2.33z"/>
            <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0 5.48 0 2.43 2.32.95 5.95l3.01 2.33c.71-2.13 2.7-3.7 5.04-3.7z"/>
          </svg>
          <span>Continue with Google</span>
        </button>
        <div className="login-divider" role="separator" aria-label="or">
          <span>or</span>
        </div>
      </>
    ) : null}
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
                onClick={() => switchMode("forgot")}
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
          <button type="button" className="btn btn--quiet" onClick={() => switchMode("signin")}>
            Sign in
          </button>
        </>
      ) : mode === "signin" ? (
        <>
          New to Linguini?{" "}
          <button type="button" className="btn btn--quiet" onClick={() => switchMode("signup")}>
            Create an account
          </button>
        </>
      ) : (
        <>
          Already have an account?{" "}
          <button type="button" className="btn btn--quiet" onClick={() => switchMode("signin")}>
            Sign in
          </button>
        </>
      )}
    </p>
  </div>;
}

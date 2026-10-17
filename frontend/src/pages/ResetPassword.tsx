import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui";
import { parseRecoveryUrlError, validatePasswordReset } from "../lib/authMessages.ts";
import { isSupabaseConfigured, supabase } from "../lib/supabase.ts";

export function ResetPassword() {
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [checking, setChecking] = useState(true);
  const [canReset, setCanReset] = useState(false);

  // Check URL hash/search for Supabase error parameters (e.g. otp_expired, access_denied)
  const [urlError] = useState<string | null>(() =>
    parseRecoveryUrlError(window.location.hash, window.location.search)
  );

  useEffect(() => {
    if (!supabase) {
      setChecking(false);
      return;
    }

    // If Supabase already passed an error in the redirect URL, reject immediately
    if (urlError) {
      setChecking(false);
      return;
    }

    const hash = window.location.hash.replace(/^#/, "");
    const hashParams = new URLSearchParams(hash);
    const searchParams = new URLSearchParams(window.location.search);
    const isRecoveryUrl =
      hashParams.get("type") === "recovery" || Boolean(searchParams.get("code"));

    let mounted = true;
    const { data: listener } = supabase.auth.onAuthStateChange((event, newSession) => {
      if (!mounted) return;
      if (
        event === "PASSWORD_RECOVERY" ||
        (event === "SIGNED_IN" && isRecoveryUrl) ||
        (Boolean(newSession) && isRecoveryUrl)
      ) {
        setCanReset(true);
      }
      setChecking(false);
    });

    void supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      if (data.session && isRecoveryUrl) {
        setCanReset(true);
      }
      setChecking(false);
    });

    return () => {
      mounted = false;
      listener.subscription.unsubscribe();
    };
  }, [urlError]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) return;
    setError(null);

    const validationError = validatePasswordReset(password, confirmPassword);
    if (validationError) {
      setError(validationError);
      return;
    }

    setSubmitting(true);
    try {
      const { error: updateError } = await supabase.auth.updateUser({ password });
      if (updateError) {
        const msg = updateError.message.toLowerCase();
        if (msg.includes("same password") || msg.includes("different from old")) {
          setError("Please choose a new password that is different from your current one.");
        } else if (msg.includes("rate limit") || msg.includes("too many")) {
          setError("Please wait a moment before trying again.");
        } else {
          setError(updateError.message || "We couldn't update your password. Please try again.");
        }
        return;
      }
      setSuccess(true);

      // Sign out of the single-use recovery session so subsequent link clicks are rejected
      await supabase.auth.signOut({ scope: "local" }).catch(() => {});

      setTimeout(() => {
        navigate("/login?mode=signin&reset=success", { replace: true });
      }, 1500);
    } catch {
      setError("We couldn't connect right now. Please check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (checking) {
    return (
      <div className="stack center-text">
        <p className="muted">Checking your reset link…</p>
      </div>
    );
  }

  const isLinkInvalid = Boolean(urlError) || (!canReset && !success);
  const errorMessage =
    urlError || "This password reset link is invalid, expired, or has already been used.";

  return (
    <div className="stack">
      <div className="center-text stack-2" style={{ alignItems: "center" }}>
        <img className="mascot" src="/linguini-logo.png" width={120} height={120} alt="Linguini mascot" />
        <h1>Create new password</h1>
        <p className="muted">Choose a secure password with at least 6 characters.</p>
      </div>

      {!isSupabaseConfigured ? (
        <p role="alert">Sign-in is being set up right now. Please try again shortly.</p>
      ) : null}

      {isSupabaseConfigured && isLinkInvalid ? (
        <div className="stack center-text">
          <p role="alert">{errorMessage}</p>
          <Button type="button" block onClick={() => navigate("/login?mode=forgot", { replace: true })}>
            Request a new link
          </Button>
        </div>
      ) : null}

      {isSupabaseConfigured && !isLinkInvalid ? (
        <form className="stack" onSubmit={event => void submit(event)}>
          <label className="field">
            <span className="field__label">New password</span>
            <input
              className="input"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={event => setPassword(event.target.value)}
              minLength={6}
              disabled={submitting || success}
              required
            />
          </label>
          <label className="field">
            <span className="field__label">Confirm new password</span>
            <input
              className="input"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={event => setConfirmPassword(event.target.value)}
              minLength={6}
              disabled={submitting || success}
              required
            />
          </label>
          {error ? <p role="alert">{error}</p> : null}
          {success ? (
            <p role="status">
              Password updated successfully! Taking you into Linguini…
            </p>
          ) : null}
          <Button type="submit" block disabled={submitting || success}>
            {submitting ? "Updating password…" : success ? "Password updated" : "Update password"}
          </Button>
        </form>
      ) : null}

      <p className="small muted center-text">
        <button
          type="button"
          className="btn btn--quiet"
          onClick={() => navigate("/login", { replace: true })}
        >
          Back to sign in
        </button>
      </p>
    </div>
  );
}

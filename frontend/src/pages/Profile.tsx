import { InlineLoader } from "../components/LoadingScreen";
import { useEffect, useId, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, IconButton } from "../components/ui";
import { BasilIcon, ChevronRightIcon, CloseIcon, InstagramIcon, LinkedInIcon, TikTokIcon, XIcon } from "../components/icons";
import { HelpImproveModal } from "../components/HelpImproveModal";
import { languages } from "../config/languages";
import { deleteCurrentAccount } from "../lib/api";
import { accountTiers } from "../lib/accountTiers";
import { trackAction } from "../lib/analytics.ts";
import { validatePasswordReset } from "../lib/authMessages.ts";
import { SOCIAL_LINKS_LIST } from "../config/social";
import { supabase } from "../lib/supabase.ts";
import { useAppState } from "../state/useAppState";
import { useAuth } from "../state/Auth";
import { MissionBadges } from "../components/MissionBadges";
import { ChefOfTheDay } from "../components/ChefOfTheDay";
import { GameResources } from "../components/GameResources";

const socialIcons = {
  instagram: InstagramIcon,
  tiktok: TikTokIcon,
  x: XIcon,
  linkedin: LinkedInIcon,
};

export function Profile() {
  const navigate = useNavigate();
  const { clearDeletedAccountSession, signOut, session } = useAuth();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const deleteTitleId = useId();
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
  const [passwordUpdating, setPasswordUpdating] = useState(false);
  const [surveyOpen, setSurveyOpen] = useState(false);
  const { learner, user, activeProfile, progress, progressLoading, progressError, profileError, profileSaving, setLanguage, saveLanguageProfile, saveUser } = useAppState();
  const tier = accountTiers[user?.tier ?? "beta"];
  const weeklyBasil = progress?.leaderboard.find(row => row.isYou)?.xp ?? 0;

  useEffect(() => {
    if (!deleteOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !deleting) setDeleteOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [deleteOpen, deleting]);

  const closeDeleteDialog = () => {
    if (deleting) return;
    setDeleteOpen(false);
    setDeleteError("");
  };

  const logOut = async () => {
    trackAction("logout_clicked");
    await signOut();
    navigate("/", { replace: true });
  };

  const deleteAccount = async () => {
    if (deleting) return;
    setDeleting(true);
    setDeleteError("");
    try {
      trackAction("account_deleted");
      await deleteCurrentAccount();
      localStorage.removeItem("linguini-avatar");
      await clearDeletedAccountSession();
      navigate("/", { replace: true });
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "We couldn't delete your account. Please try again.");
      setDeleting(false);
    }
  };

  const handlePasswordUpdate = async (event: FormEvent) => {
    event.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(null);

    const validationError = validatePasswordReset(newPassword, confirmPassword);
    if (validationError) {
      setPasswordError(validationError);
      return;
    }

    if (!supabase) {
      setPasswordError("Authentication is not configured.");
      return;
    }

    setPasswordUpdating(true);
    try {
      const { error } = await supabase.auth.updateUser({ password: newPassword });
      if (error) {
        const msg = error.message.toLowerCase();
        if (msg.includes("same password") || msg.includes("different from old")) {
          setPasswordError("Please choose a new password that is different from your current one.");
        } else if (msg.includes("rate limit") || msg.includes("too many")) {
          setPasswordError("Please wait a moment before trying again.");
        } else {
          setPasswordError(error.message || "We couldn't update your password. Please try again.");
        }
        return;
      }
      trackAction("profile_password_changed");
      setPasswordSuccess("Password updated successfully!");
      setNewPassword("");
      setConfirmPassword("");
    } catch {
      setPasswordError("We couldn't connect right now. Please check your connection and try again.");
    } finally {
      setPasswordUpdating(false);
    }
  };

  return (
    <div className="stack profile-page">
      <div className="profile-page__heading">
        <h2>Profile</h2>
      </div>

      <section className="profile-identity-card" aria-label="Profile">
        <span className="profile-avatar">
          <img src={`/pasta-assets/${localStorage.getItem("linguini-avatar") ?? "farfalle"}.png`} alt="Profile avatar" />
        </span>
        <button type="button" className="profile-identity__details profile-name-link" onClick={() => navigate("/profile/edit")} aria-label="Change profile name and avatar">
          <h2>{learner.name}</h2>
          <span>{user ? `Joined ${new Date(user.createdAt).toLocaleDateString("en-GB", { month: "long", year: "numeric" })}` : ""}</span>
          <ChevronRightIcon size={20} />
        </button>
      </section>
      {progressLoading ? <InlineLoader label="Loading your profile…" /> : null}
      {progressError ? <p role="alert">{progressError} Reload to retry.</p> : null}
      {profileError ? <p role="alert">{profileError}</p> : null}

      {!progressLoading && !progressError ? <section className="profile-basil" aria-labelledby="profile-basil-heading">
        <h2 id="profile-basil-heading">Your Basil</h2>
        <div className="profile-basil__grid">
          <div><span className="profile-basil__icon"><BasilIcon size={24} /></span><span>This week</span><strong>{weeklyBasil}</strong></div>
          <div><span className="profile-basil__icon"><BasilIcon size={24} /></span><span>All time</span><strong>{progress?.xp ?? 0}</strong></div>
        </div>
      </section> : null}

      <section className="profile-section" aria-labelledby="account-tier-heading">
        <h2 id="account-tier-heading">Your plan</h2>
        <Card plain className="profile-tier-card">
          <div>
            <span className="profile-tier-badge">{tier.label}</span>
            <strong>{tier.description}</strong>
          </div>
          <p>{(user?.tier ?? "beta") === "beta"
            ? "Photo lessons and friend challenges are free to start during the beta."
            : tier.allowance}</p>
        </Card>
      </section>

      <MissionBadges />

      <section className="profile-section">
        <h2>Learning setup</h2>
        <Card plain className="profile-settings-card">
          <label className="profile-setting">
            <span>
              <strong>Target language</strong>
              <small>The language you are learning</small>
            </span>
            <select disabled={profileSaving} value={learner.languageCode} onChange={event => void setLanguage(event.target.value, learner.dailyMinutes ?? 10)}>
              {languages.map(language => (
                <option key={language.code} value={language.code}>
                  {language.flag} {language.name}
                </option>
              ))}
            </select>
          </label>

          <label className="profile-setting">
            <span>
              <strong>Daily goal</strong>
              <small>Time set aside each day</small>
            </span>
            <select disabled={profileSaving || !activeProfile} value={learner.dailyMinutes ?? 10} onChange={event => void saveLanguageProfile({ dailyGoalMinutes: Number(event.target.value) })}>
              {[5, 10, 15, 20].map(minutes => <option key={minutes} value={minutes}>{minutes} min</option>)}
            </select>
          </label>

          <label className="profile-setting">
            <span>
              <strong>Practice preference</strong>
              <small>How you prefer to respond</small>
            </span>
            <select disabled={profileSaving || !activeProfile} value={activeProfile?.preferredInputMode ?? "both"} onChange={event => void saveLanguageProfile({ preferredInputMode: event.target.value as "speech" | "text" | "both" })}>
              <option value="both">Both</option><option value="speech">Speaking</option><option value="text">Typing</option>
            </select>
          </label>
        </Card>
      </section>

      <section className="profile-section" aria-labelledby="account-heading">
        <h2 id="account-heading">Account</h2>
        <Card plain className="profile-settings-card">
          <div className="profile-setting">
            <span>
              <strong>Email</strong>
              <small>Your sign-in email address</small>
            </span>
            <b style={{ userSelect: "all", overflowWrap: "anywhere", wordBreak: "break-all" }}>
              {user?.email ?? session?.user?.email ?? "No email linked"}
            </b>
          </div>

          {!passwordOpen ? (
            <button
              type="button"
              className="profile-setting profile-support-link"
              onClick={() => {
                setPasswordOpen(true);
                setPasswordError(null);
                setPasswordSuccess(null);
              }}
            >
              <span>
                <strong>Reset password</strong>
                <small>Choose a new password for your account</small>
              </span>
              <ChevronRightIcon size={20} />
            </button>
          ) : (
            <form
              className="profile-password-form stack"
              onSubmit={event => void handlePasswordUpdate(event)}
            >
              <div className="profile-password-form__header">
                <strong>Change password</strong>
                <button
                  type="button"
                  className="btn btn--quiet"
                  style={{ padding: 0, height: "auto", minHeight: "unset", fontSize: "0.85rem" }}
                  onClick={() => {
                    setPasswordOpen(false);
                    setPasswordError(null);
                    setPasswordSuccess(null);
                    setNewPassword("");
                    setConfirmPassword("");
                  }}
                >
                  Cancel
                </button>
              </div>
              <label className="field">
                <span className="field__label" style={{ fontSize: "0.85rem" }}>New password</span>
                <input
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={event => setNewPassword(event.target.value)}
                  placeholder="At least 6 characters"
                  minLength={6}
                  disabled={passwordUpdating}
                  required
                />
              </label>
              <label className="field">
                <span className="field__label" style={{ fontSize: "0.85rem" }}>Confirm new password</span>
                <input
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={event => setConfirmPassword(event.target.value)}
                  placeholder="Re-enter new password"
                  minLength={6}
                  disabled={passwordUpdating}
                  required
                />
              </label>
              {passwordError ? (
                <p role="alert" style={{ color: "var(--danger)", margin: 0, fontSize: "0.85rem" }}>
                  {passwordError}
                </p>
              ) : null}
              {passwordSuccess ? (
                <p role="status" style={{ color: "var(--teal-dark)", margin: 0, fontSize: "0.85rem", fontWeight: 700 }}>
                  {passwordSuccess}
                </p>
              ) : null}
              <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-1)" }}>
                <Button type="submit" disabled={passwordUpdating}>
                  {passwordUpdating ? "Updating…" : "Save new password"}
                </Button>
              </div>
            </form>
          )}
        </Card>
      </section>

      <section className="profile-section">
        <h2>Permissions</h2>
        <Card plain className="profile-settings-card">
          
          <label className="profile-setting" >
            <span>
              <strong>Camera</strong>
              <small>Used to capture scenes for learning</small>
            </span>
            <input type="checkbox" disabled={profileSaving} checked={learner.cameraOn} onChange={event => void saveUser({ cameraEnabled: event.target.checked })} />
          </label>
        </Card>
      </section>

      <aside className="profile-ai-note">
        <strong>How AI helps</strong>
        <p>
          Linguini uses AI in a few specific places: it detects the objects in your scene
          photos, translates that vocabulary into your learning language, and writes the
          I-Spy clues and practice tasks from the words you keep. Every suggestion is yours
          to review: you decide what to keep, change, or remove before a lesson starts.
        </p>
      </aside>

      <aside className="profile-ai-note">
        <strong>Your privacy</strong>
        <p>
          Your photos are stored securely for learning. Photos you add to a private room are shared with the friend in that room. Your solo photos stay private and are never used to train AI models.
        </p>
      </aside>

      <section className="profile-section">
        <h2>Help and feedback</h2>
        <Card plain className="profile-settings-card">
          <button type="button" className="profile-setting profile-support-link" onClick={() => navigate("/contact")}>
            <span>
              <strong>Contact us</strong>
              <small>Report a problem or get support with your account</small>
            </span>
            <ChevronRightIcon size={20} />
          </button>
          <button type="button" className="profile-setting profile-support-link" onClick={() => setSurveyOpen(true)}>
            <span>
              <strong>Help us improve</strong>
              <small>Share feedback on your learning experience</small>
            </span>
            <ChevronRightIcon size={20} />
          </button>
        </Card>
      </section>

      <section className="profile-section" aria-labelledby="social-heading">
        <h2 id="social-heading">Follow Linguini</h2>
        <Card plain className="profile-settings-card">
          <div className="profile-social-grid">
            {SOCIAL_LINKS_LIST.map(({ platform, label, url, handle }) => {
              const Icon = socialIcons[platform];
              return (
                <a
                  key={platform}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="profile-social-item"
                  aria-label={`Follow Linguini on ${label}`}
                  onClick={() => trackAction("social_link_clicked", { platform })}
                >
                  <span className="profile-social-icon">
                    <Icon size={20} />
                  </span>
                  <div className="profile-social-info">
                    <strong>{label}</strong>
                    <small>{handle}</small>
                  </div>
                  <ChevronRightIcon size={18} />
                </a>
              );
            })}
          </div>
        </Card>
      </section>

      <Button block className="profile-logout" onClick={() => void logOut()}>
        Log Out
      </Button>

      <section className="profile-danger-zone" aria-labelledby="delete-account-heading">
        <h2 id="delete-account-heading">Delete account</h2>
        <p>Permanently remove your Linguini account and everything associated with it.</p>
        <Button variant="quiet" block className="profile-delete-trigger" onClick={() => setDeleteOpen(true)}>
          Delete my account
        </Button>
      </section>

      {deleteOpen ? (
        <div className="help-modal__backdrop" onMouseDown={closeDeleteDialog}>
          <section
            className="help-modal account-delete-modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby={deleteTitleId}
            aria-describedby={`${deleteTitleId}-description`}
            onMouseDown={event => event.stopPropagation()}
          >
            <div className="help-modal__header">
              <h2 id={deleteTitleId}>Delete your account?</h2>
              <IconButton label="Keep my account" disabled={deleting} onClick={closeDeleteDialog}>
                <CloseIcon />
              </IconButton>
            </div>
            <div id={`${deleteTitleId}-description`} className="account-delete-summary">
              <p>This will permanently delete:</p>
              <ul>
                <li>Your profile and sign-in account</li>
                <li>Your lessons, vocabulary progress, and Basil history</li>
                <li>Your journal entries and revisions</li>
                <li>Your uploaded photos and generated image copies</li>
              </ul>
              <strong>This action is irreversible.</strong>
            </div>
            {deleteError ? <p className="account-delete-error" role="alert">{deleteError}</p> : null}
            <div className="account-delete-actions">
              <Button variant="quiet" block disabled={deleting} onClick={closeDeleteDialog}>Keep my account</Button>
              <Button block disabled={deleting} onClick={() => void deleteAccount()}>
                {deleting ? "Deleting account…" : "Permanently delete account"}
              </Button>
            </div>
          </section>
        </div>
      ) : null}

      <HelpImproveModal
        open={surveyOpen}
        onClose={() => setSurveyOpen(false)}
        triggerSource="profile"
      />
    </div>
  );
}

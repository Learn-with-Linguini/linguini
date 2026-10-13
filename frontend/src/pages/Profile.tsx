import { useEffect, useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, IconButton } from "../components/ui";
import { ChevronRightIcon, CloseIcon } from "../components/icons";
import { deleteCurrentAccount } from "../lib/api";
import { accountTiers } from "../lib/accountTiers";
import { useAppState } from "../state/useAppState";
import { useAuth } from "../state/Auth";
import { GameResources } from "../components/GameResources";
import { gameResourcesEnabled } from "../lib/gameResources";
import { playTogetherEnabled } from "../lib/rooms";

export function Profile() {
  const navigate = useNavigate();
  const { clearDeletedAccountSession, signOut } = useAuth();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const deleteTitleId = useId();
  const { learner, user, activeProfile, progressLoading, progressError, profileError, profileSaving, setLanguage, saveLanguageProfile, saveUser } = useAppState();
  const tier = accountTiers[user?.tier ?? "beta"];

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
    await signOut();
    navigate("/", { replace: true });
  };

  const deleteAccount = async () => {
    if (deleting) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteCurrentAccount();
      localStorage.removeItem("linguini-avatar");
      await clearDeletedAccountSession();
      navigate("/", { replace: true });
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "We couldn't delete your account. Please try again.");
      setDeleting(false);
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
      {progressLoading ? <p role="status">Loading your profile...</p> : null}
      {progressError ? <p role="alert">{progressError} Reload to retry.</p> : null}
      {profileError ? <p role="alert">{profileError}</p> : null}

      <section className="profile-section" aria-labelledby="account-tier-heading">
        <h2 id="account-tier-heading">Your plan</h2>
        <Card plain className="profile-tier-card">
          <div>
            <span className="profile-tier-badge">{tier.label}</span>
            <strong>{tier.description}</strong>
          </div>
          <p>{gameResourcesEnabled && (user?.tier ?? "beta") === "beta"
            ? "Public beta includes a daily Sauce refill. New photo lessons and games each use 1 Sauce; resuming does not spend more."
            : tier.allowance}</p>
        </Card>
      </section>

      {gameResourcesEnabled ? <section className="profile-section" aria-labelledby="profile-sauce-heading">
        <h2 id="profile-sauce-heading">Your Sauce and Basil leaves</h2>
        <GameResources shop />
      </section> : null}

      <section className="profile-section">
        <h2>Learning setup</h2>
        <Card plain className="profile-settings-card">
          <label className="profile-setting">
            <span>
              <strong>Target language</strong>
              <small>The language you are learning</small>
            </span>
            <select disabled={profileSaving} value={learner.languageCode} onChange={event => void setLanguage(event.target.value, learner.dailyMinutes ?? 10)}>
              <option value="es">🇪🇸 Spanish</option><option value="fr">🇫🇷 French</option>
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
          {playTogetherEnabled
            ? "Your photos are stored securely for learning. Photos you add to a private room are shared with the friend in that room. Your solo photos stay private and are never used to train AI models."
            : "Your photos are stored securely and are only used to generate your own lessons. They are never shared with other learners and never used to train AI models."}
        </p>
      </aside>

      <section className="profile-section">
        <h2>Help and feedback</h2>
        <Card plain className="profile-settings-card">
          <button type="button" className="profile-setting profile-support-link" onClick={() => navigate("/contact")}>
            <span>
              <strong>Contact us</strong>
              <small>Report a problem or tell us what would make Linguini better</small>
            </span>
            <ChevronRightIcon size={20} />
          </button>
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
                <li>Your lessons, vocabulary progress, and XP history</li>
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
    </div>
  );
}

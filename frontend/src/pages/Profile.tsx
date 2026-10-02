import { useNavigate } from "react-router-dom";
import { Button, Card } from "../components/ui";
import { ChevronRightIcon } from "../components/icons";
import { useAppState } from "../state/useAppState";
import { useAuth } from "../state/Auth";

export function Profile() {
  const navigate = useNavigate();
  const { signOut } = useAuth();
  const { learner, user, activeProfile, progressLoading, progressError, profileError, profileSaving, setLanguage, saveLanguageProfile, saveUser } = useAppState();

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
          to review — you decide what to keep, change, or remove before a lesson starts.
        </p>
      </aside>

      <aside className="profile-ai-note">
        <strong>Your privacy</strong>
        <p>
          Your photos are stored securely and are only used to generate your own lessons.
          They are never shared with other learners and never used to train AI models.
        </p>
      </aside>

      <Button block className="profile-logout" onClick={() => void signOut()}>
        Log Out
      </Button>
    </div>
  );
}

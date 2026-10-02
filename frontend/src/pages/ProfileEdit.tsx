import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card } from "../components/ui";
import { useAppState } from "../state/useAppState";

const AVATARS = ["farfalle", "fusilli", "penne", "macaroni"] as const;

export function ProfileEdit() {
  const navigate = useNavigate();
  const { learner, activeProfile, startProfileSettingsSave, profileSaving, profileError } = useAppState();
  const [name, setName] = useState(learner.name);
  const [avatar, setAvatar] = useState(() => localStorage.getItem("linguini-avatar") ?? "farfalle");

  const saveProfile = () => {
    if (profileSaving || !name.trim()) return;
    const started = startProfileSettingsSave(learner.languageCode || "es", {
      displayName: name.trim(), microphoneEnabled: learner.micOn, cameraEnabled: learner.cameraOn,
    }, activeProfile ? { dailyGoalMinutes: activeProfile.dailyGoalMinutes, preferredInputMode: activeProfile.preferredInputMode } : {});
    if (started) { localStorage.setItem("linguini-avatar", avatar); navigate("/profile"); }
  };

  return (
    <div className="stack profile-page profile-edit-page">
      <div>
        <h1>Profile options</h1>
        <p className="small muted">Choose your avatar and update your name.</p>
      </div>

      <section className="profile-section">
        <h2>About you</h2>
        <Card plain className="profile-edit-card">
          <fieldset className="profile-avatar-picker"><legend>Profile avatar</legend><div className="profile-avatar-options">{AVATARS.map(option => <button key={option} type="button" className={avatar === option ? "is-selected" : ""} onClick={() => setAvatar(option)}><img src={`/pasta-assets/${option}.png`} alt={`${option} pasta`} /></button>)}</div></fieldset>
          <label className="profile-edit-field">
            <span>Name</span>
            <input maxLength={100} disabled={profileSaving} value={name} onChange={(event) => setName(event.target.value)} />
          </label>
        </Card>
      </section>

      {profileError ? <p role="alert">{profileError} Your changes are still here.</p> : null}
      {profileSaving ? <p role="status">Saving profile...</p> : null}
      <Button block disabled={profileSaving || !name.trim()} onClick={() => void saveProfile()}>Save changes</Button>
    </div>
  );
}

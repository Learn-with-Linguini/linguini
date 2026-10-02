import { useState } from "react";
import { Button, Card, ProgressTrail, TopBar } from "./ui";
import { CameraIcon, CheckIcon } from "./icons";
import { languages } from "../config/languages";
import { joinGoals, parseGoals, type OnboardingDraft } from "../lib/onboardingDraft";

const goals = ["Chat with neighbours", "Travel confidently", "Order food and drinks", "Understand my family"];
const minutesOptions = [5, 10, 20, 30];
const avatars = ["farfalle", "fusilli", "penne", "macaroni"] as const;

export function OnboardingSteps({ initial, saving = false, error, onComplete }: { initial: OnboardingDraft; saving?: boolean; error?: string | null; onComplete: (draft: OnboardingDraft) => void | Promise<void> }) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState(initial.name);
  const [language, setLanguage] = useState(languages.find(option => option.code === initial.languageCode) ?? languages[0]);
  const [selectedGoals, setSelectedGoals] = useState<string[]>(() => {
    const saved = parseGoals(initial.goal).filter(value => goals.includes(value));
    return saved.length ? saved : [];
  });
  const [minutes, setMinutes] = useState(initial.minutes || 10);
  const [microphoneEnabled] = useState(initial.microphoneEnabled);
  const [cameraEnabled, setCameraEnabled] = useState(initial.cameraEnabled);
  const [avatar, setAvatar] = useState(initial.avatar);
  const steps = ["Your profile", "Choose a language", "Set your goal", "Permissions"];
  const toggleGoal = (option: string) => setSelectedGoals(current => current.includes(option) ? current.filter(value => value !== option) : [...current, option]);
  const next = () => {
    if (step < steps.length - 1) { setStep(current => current + 1); return; }
    void onComplete({ name: name.trim(), languageCode: language.code, goal: joinGoals(selectedGoals), minutes, microphoneEnabled, cameraEnabled, avatar });
  };
  return <div className="stack">
    <TopBar title={steps[step]} help="Four short steps and you are ready to practise." />
    <ProgressTrail value={step + 1} total={steps.length} label={`Step ${step + 1} of ${steps.length}`} />
    {step === 0 ? <div className="stack"><h1>Nice to meet you</h1><p className="muted">Choose a pasta pal and a name to cheer you on.</p><fieldset className="profile-avatar-picker"><legend>Your pasta pal</legend><div className="profile-avatar-options">{avatars.map(option => <button key={option} type="button" className={avatar === option ? "is-selected" : ""} aria-pressed={avatar === option} onClick={() => setAvatar(option)}><img src={`/pasta-assets/${option}.png`} alt={`${option} pasta`} /></button>)}</div></fieldset><div className="field"><label className="field__label" htmlFor="ob-name">Your name</label><input id="ob-name" className="input" value={name} placeholder="Alex" onChange={event => setName(event.target.value)} /></div></div> : null}
    {step === 1 ? <div className="stack"><h1>Which language today?</h1><p className="muted">You can change this later in your profile.</p><div className="grid-2">{languages.map(option => <button key={option.code} type="button" className={`scene-pick${option.code === language.code ? " scene-pick--selected" : ""}`} onClick={() => setLanguage(option)} style={{ alignItems: "center", padding: "var(--space-4)" }}><span style={{ fontSize: 28 }}>{option.flag}</span><strong>{option.name}</strong></button>)}</div></div> : null}
    {step === 2 ? <div className="stack"><h1>What are you practising for?</h1><p className="muted">Pick as many as you like.</p><div className="stack-2">{goals.map(option => {
      const selected = selectedGoals.includes(option);
      return <button key={option} type="button" className={`task-row${selected ? " task-row--done" : ""}`} aria-pressed={selected} onClick={() => toggleGoal(option)}><span className="task-row__index">{selected ? <CheckIcon size={16} /> : ""}</span><span className="grow">{option}</span></button>;
    })}</div><h3>Minutes a day</h3><div className="row">{minutesOptions.map(option => <button key={option} type="button" className={`chip${option === minutes ? " chip--selected" : ""}`} onClick={() => setMinutes(option)}>{option} min</button>)}</div></div> : null}
    {step === 3 ? <div className="stack"><h1>Permissions</h1><p className="muted">Linguini uses your camera for scenes.</p><Card><div className="spread"><div className="row"><CameraIcon /><div><strong>Camera</strong><p className="small muted">Capture scenes to learn from</p></div></div><input type="checkbox" aria-label="Allow camera" checked={cameraEnabled} onChange={event => setCameraEnabled(event.target.checked)} /></div></Card></div> : null}
    {error ? <p role="alert">{error}</p> : null}{saving ? <p role="status">Saving profile…</p> : null}
    <Button block disabled={saving || (step === 2 && !selectedGoals.length)} onClick={next}>{step === steps.length - 1 ? "Start learning" : "Continue"}</Button>
  </div>;
}

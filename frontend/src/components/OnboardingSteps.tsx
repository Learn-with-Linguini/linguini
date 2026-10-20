import { LoadingScreen } from "./LoadingScreen";
import { useEffect, useState } from "react";
import { Button, Card, ProgressTrail, TopBar } from "./ui";
import { CameraIcon, CheckIcon } from "./icons";
import { profileLanguageChoices } from "../lib/languageChoices";
import { usePracticeLanguages } from "../state/usePracticeLanguages";
import { joinGoals, parseGoals, type OnboardingDraft } from "../lib/onboardingDraft";
import { checkPlacementAnswer, getPlacementTest, submitPlacement, type PlacementTest } from "../lib/api";
import { nextPlacementDifficulty } from "../lib/placementPath";

const goals = ["Chat with neighbours", "Travel confidently", "Order food and drinks", "Understand my family"];
const minutesOptions = [5, 10, 20, 30];
const avatars = ["farfalle", "fusilli", "penne", "macaroni"] as const;
type Stage = "profile" | "language" | "experience" | "placement" | "goals" | "permissions" | "success";

function OnboardingSuccess({ onFinish }: { onFinish: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onFinish, 1800);
    return () => window.clearTimeout(timer);
  }, [onFinish]);
  return <div className="stack onboarding-success"><img src="/linguini-logo.svg" alt="" className="onboarding-success__mascot" /><h1>You’re all set!</h1><p className="muted">Great work—your first learning path is ready for you.</p><Button block onClick={onFinish}>Go to home</Button></div>;
}

export function OnboardingSteps({ initial, saving = false, error, onComplete, onFinish }: {
  initial: OnboardingDraft;
  saving?: boolean;
  error?: string | null;
  onComplete: (draft: OnboardingDraft) => Promise<boolean>;
  onFinish: () => void;
}) {
  const [stage, setStage] = useState<Stage>("profile");
  const [name, setName] = useState(initial.name);
  const { choices: languages } = usePracticeLanguages(initial.languageCode);
  const [language, setLanguage] = useState(() => profileLanguageChoices([], initial.languageCode).find(option => option.code === initial.languageCode) ?? profileLanguageChoices([])[0]);
  const [selectedGoals, setSelectedGoals] = useState(() => parseGoals(initial.goal).filter(value => goals.includes(value)));
  const [minutes, setMinutes] = useState(initial.minutes || 10);
  const [microphoneEnabled] = useState(initial.microphoneEnabled);
  const [cameraEnabled, setCameraEnabled] = useState(initial.cameraEnabled);
  const [avatar, setAvatar] = useState(initial.avatar);
  const [level, setLevel] = useState<"A0" | "A1" | "A2">("A0");
  const [test, setTest] = useState<PlacementTest | null>(null);
  const [questionPath, setQuestionPath] = useState<string[]>([]);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<{ selected: string; correct: boolean; correctOption: string } | null>(null);
  const [showTranslation, setShowTranslation] = useState(false);
  const [working, setWorking] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const draft = (): OnboardingDraft => ({ name: name.trim(), languageCode: language.code, goal: joinGoals(selectedGoals), minutes, microphoneEnabled, cameraEnabled, avatar, proficiencyLevel: level });
  const chooseBeginner = async () => {
    setWorking(true); setLocalError(null);
    try {
      const result = await submitPlacement(language.code, "beginner");
      setLevel(result.proficiencyLevel); setStage("goals");
    } catch { setLocalError("We couldn't save your starting point. Please try again."); }
    finally { setWorking(false); }
  };
  const beginPlacement = async () => {
    setWorking(true); setLocalError(null);
    try {
      const loaded = await getPlacementTest(language.code);
      const startingQuestion = loaded.questions.find(question => question.difficulty === "A1");
      if (!startingQuestion) throw new Error("Placement questions are incomplete.");
      setTest(loaded); setQuestionPath([startingQuestion.id]); setQuestionIndex(0);
      setAnswers({}); setFeedback(null); setShowTranslation(false); setStage("placement");
    }
    catch { setLocalError("We couldn't load the quick activity. Please try again."); }
    finally { setWorking(false); }
  };
  const answer = async (value: string) => {
    if (!test || working || feedback) return;
    const question = test.questions.find(item => item.id === questionPath[questionIndex]);
    if (!question) return;
    const next = { ...answers, [question.id]: value };
    setAnswers(next);
    setWorking(true); setLocalError(null);
    try {
      const result = await checkPlacementAnswer(question.id, value);
      setFeedback({ selected: value, ...result });
    } catch { setLocalError("We couldn't check that answer. Please try again."); }
    finally { setWorking(false); }
  };
  const continuePlacement = async () => {
    if (!test || !feedback || working) return;
    if (questionIndex < 2) {
      const current = test.questions.find(question => question.id === questionPath[questionIndex]);
      if (!current) { setLocalError("We couldn't choose the next question. Please try again."); return; }
      const nextDifficulty = nextPlacementDifficulty(questionIndex, current.difficulty, feedback.correct);
      const nextQuestion = test.questions.find(question => question.difficulty === nextDifficulty && !questionPath.includes(question.id));
      if (!nextQuestion) { setLocalError("We couldn't choose the next question. Please try again."); return; }
      setQuestionPath(path => [...path, nextQuestion.id]);
      setQuestionIndex(index => index + 1); setFeedback(null); setShowTranslation(false); return;
    }
    setWorking(true); setLocalError(null);
    try {
      const result = await submitPlacement(language.code, "placement", answers);
      setLevel(result.proficiencyLevel); setStage("goals");
    } catch { setLocalError("We couldn't finish the activity. Your answers are still here—please try again."); }
    finally { setWorking(false); }
  };
  const finish = async () => { if (await onComplete(draft())) setStage("success"); };
  const toggleGoal = (option: string) => setSelectedGoals(current => current.includes(option) ? current.filter(value => value !== option) : [...current, option]);
  const progress = ({ profile: 1, language: 2, experience: 3, placement: 3, goals: 4, permissions: 5, success: 5 } as const)[stage];

  if (stage === "success") return <OnboardingSuccess onFinish={onFinish} />;
  const currentQuestion = test?.questions.find(question => question.id === questionPath[questionIndex]);
  return <div className="stack onboarding-flow">
    <TopBar title={stage === "placement" ? "A quick warm-up" : "Let’s get you ready"} help="A few short steps and you are ready to practise." />
    {stage !== "placement" ? <ProgressTrail value={progress} total={5} label={`Step ${progress} of 5`} /> : null}
    {stage === "profile" ? <div className="stack"><h1>Nice to meet you</h1><p className="muted">Choose a pasta pal and a name to cheer you on.</p><fieldset className="profile-avatar-picker"><legend>Your pasta pal</legend><div className="profile-avatar-options">{avatars.map(option => <button key={option} type="button" className={avatar === option ? "is-selected" : ""} aria-pressed={avatar === option} onClick={() => setAvatar(option)}><img src={`/pasta-assets/${option}.png`} alt={`${option} pasta`} /></button>)}</div></fieldset><div className="field"><label className="field__label" htmlFor="ob-name">Your name</label><input id="ob-name" className="input" value={name} placeholder="Alex" onChange={event => setName(event.target.value)} /></div><Button block onClick={() => setStage("language")}>Continue</Button></div> : null}
    {stage === "language" ? <div className="stack"><h1>Which language today?</h1><p className="muted">You can add another language later.</p><div className="grid-2">{languages.map(option => <button key={option.code} type="button" className={`scene-pick${option.code === language.code ? " scene-pick--selected" : ""}`} onClick={() => setLanguage(option)}><span className="language-choice__flag">{option.flag}</span><strong>{option.name}</strong></button>)}</div><Button block onClick={() => setStage("experience")}>Continue</Button></div> : null}
    {stage === "experience" ? <div className="stack"><h1>How much {language.name} do you know?</h1><p className="muted">We’ll use this to choose a comfortable place to begin.</p><button className="onboarding-path" disabled={working} onClick={() => void chooseBeginner()}><strong>I’m a complete beginner</strong><span>Start with the essentials</span></button><button className="onboarding-path" disabled={working} onClick={() => void beginPlacement()}><strong>I know some {language.name}</strong><span>Take a short picture activity</span></button></div> : null}
    {stage === "placement" && currentQuestion && test ? <div className="stack placement-test"><ProgressTrail value={questionIndex + 1} total={3} label={`${questionIndex + 1} of 3`} /><img src={test.imagePath} alt="A café with two customers, a server, cups, apples, chairs, a bag and a dog" className="placement-test__image" /><div className="stack-2 placement-question"><div><h2>{currentQuestion.prompt}</h2><button type="button" className="placement-translation-toggle" onClick={() => setShowTranslation(value => !value)}>{showTranslation ? "Hide translation" : "See translation"}</button>{showTranslation ? <p className="placement-question__translation">{currentQuestion.promptTranslation}</p> : null}</div><div className="choice-grid placement-choice-grid">{currentQuestion.options.map(option => { const state = feedback ? option.value === feedback.correctOption ? " choice--correct" : option.value === feedback.selected ? " choice--incorrect" : "" : ""; return <button className={`choice${state}`} type="button" aria-pressed={feedback?.selected === option.value} disabled={working || Boolean(feedback)} key={option.value} onClick={() => void answer(option.value)}>{option.label}{feedback && option.value === feedback.correctOption ? <span aria-hidden="true"> ✓</span> : null}</button>; })}</div><button className={`placement-unknown${feedback?.selected === "__unknown__" ? " placement-unknown--selected" : ""}`} type="button" disabled={working || Boolean(feedback)} onClick={() => void answer("__unknown__")}>I don’t know</button>{feedback ? <div className={`placement-feedback${feedback.correct ? " placement-feedback--correct" : " placement-feedback--incorrect"}`} role="status"><strong>{feedback.correct ? "Nice!" : "Not quite—but now you know."}</strong></div> : null}{feedback ? <Button block onClick={() => void continuePlacement()}>{questionIndex === 2 ? "Finish" : "Continue"}</Button> : null}</div></div> : null}
    {stage === "goals" ? <div className="stack"><h1>What are you practising for?</h1><p className="muted">Pick as many as you like.</p><div className="stack-2">{goals.map(option => { const selected = selectedGoals.includes(option); return <button key={option} type="button" className={`task-row${selected ? " task-row--done" : ""}`} aria-pressed={selected} onClick={() => toggleGoal(option)}><span className="task-row__index">{selected ? <CheckIcon size={16} /> : ""}</span><span className="grow">{option}</span></button>; })}</div><h3>Minutes a day</h3><div className="row">{minutesOptions.map(option => <button key={option} type="button" className={`chip${option === minutes ? " chip--selected" : ""}`} onClick={() => setMinutes(option)}>{option} min</button>)}</div><Button block disabled={!selectedGoals.length} onClick={() => setStage("permissions")}>Continue</Button></div> : null}
    {stage === "permissions" ? <div className="stack"><h1>One last thing</h1><p className="muted">Linguini can use your camera for scenes.</p><Card><div className="spread"><div className="row"><CameraIcon /><div><strong>Camera</strong><p className="small muted">Capture scenes to learn from</p></div></div><input type="checkbox" aria-label="Allow camera" checked={cameraEnabled} onChange={event => setCameraEnabled(event.target.checked)} /></div></Card><Button block disabled={saving || working} onClick={() => void finish()}>Finish setup</Button></div> : null}
    {working || saving ? <LoadingScreen label="Getting things ready…" /> : null}
    {localError || error ? <p role="alert">{localError ?? error}</p> : null}
  </div>;
}

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Card, ProgressTrail } from "../components/ui";
import { ArrowRightIcon, CameraIcon, CheckIcon, CloseIcon, SpeakerIcon, UploadIcon } from "../components/icons";
import { trackAction } from "../lib/analytics";
import { speak } from "../marketing/lib/speech";
import { getScene, scenes } from "../marketing/data/scenes";
import { languageNames, type Lang } from "../marketing/data/types";
import { analyzeGuestPhoto, staticGuestScene, type GuestScene, type GuestTerm, type GuestWord } from "../marketing/components/try/demoApi";
import styles from "./GuestDemo.module.css";

type Stage = "select" | "analyse" | "review" | "translate" | "task" | "done";
const languages: Lang[] = ["es", "fr", "de", "ko"];

export function GuestDemo() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fileInput = useRef<HTMLInputElement>(null);
  const [lang, setLang] = useState<Lang>(() => {
    const requested = searchParams.get("lang");
    return languages.includes(requested as Lang) ? requested as Lang : "es";
  });
  const [stage, setStage] = useState<Stage>("select");
  const [scene, setScene] = useState<GuestScene | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [wordIndex, setWordIndex] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const words = useMemo(() => scene?.words.filter(word => selected.includes(word.id)) ?? [], [scene, selected]);

  useEffect(() => {
    const previous = document.title;
    document.title = "Try a photo lesson | Linguini";
    return () => { document.title = previous; };
  }, []);

  useEffect(() => {
    const requested = searchParams.get("photo");
    if (!requested) return;
    const chosen = getScene(requested);
    if (chosen) chooseScene(staticGuestScene(chosen, lang), "sample");
    // The query is an entry hint, not persistent guest state.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (stage !== "analyse") return;
    const delay = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 1800;
    const timer = window.setTimeout(() => go("review"), delay);
    return () => window.clearTimeout(timer);
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  useEffect(() => {
    if (!scene?.photo.startsWith("blob:")) return;
    return () => URL.revokeObjectURL(scene.photo);
  }, [scene]);

  function go(next: Stage) {
    trackAction("guest_demo_stage_viewed", { stage: next, source: scene?.uploaded ? "upload" : "sample" });
    if (next === "done") trackAction("guest_demo_completed", { language: lang, source: scene?.uploaded ? "upload" : "sample" });
    setStage(next);
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  function chooseScene(next: GuestScene, source: "sample" | "upload") {
    setScene(next);
    setSelected(next.words.map(word => word.id));
    setWordIndex(0);
    setPicked(null);
    setError(null);
    setStage("analyse");
    trackAction("guest_demo_scene_selected", { sceneId: next.id, language: lang, source });
  }

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    trackAction("guest_demo_photo_selected", { language: lang });
    try {
      const result = await analyzeGuestPhoto(file, lang);
      trackAction("guest_demo_photo_analyzed", { language: lang, objectCount: result.words.length });
      chooseScene(result, "upload");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "We couldn't prepare that photo lesson.");
      trackAction("guest_demo_photo_failed", { language: lang });
    } finally {
      setUploading(false);
    }
  }

  function startOver() {
    setScene(null);
    setSelected([]);
    setPicked(null);
    setStage("select");
    navigate("/demo", { replace: true });
  }

  if (stage === "select" || !scene) return <DemoPicker lang={lang} setLang={setLang} uploading={uploading} error={error} fileInput={fileInput} onUpload={upload} onPick={item => chooseScene(staticGuestScene(item, lang), "sample")} />;
  if (stage === "analyse") return <div className="stack analysis-page"><h1>Scene analysis</h1><section className={`analysis-loading ${styles.analysis}`} aria-live="polite" aria-busy="true"><ScenePhoto scene={scene} scanning /><div className="analysis-loading__copy"><h2>Finding objects in your image...</h2><p className="muted">Linguini is looking for useful words to practise.</p></div></section></div>;
  if (stage === "review") return <Review scene={scene} selected={selected} setSelected={setSelected} onBack={startOver} onContinue={() => go("translate")} />;
  if (stage === "translate") return <Translation scene={scene} words={words} lang={lang} index={wordIndex} setIndex={setWordIndex} onBack={() => go("review")} onContinue={() => go("task")} />;
  if (stage === "task") return <Task scene={scene} words={words} lang={lang} picked={picked} setPicked={setPicked} onBack={() => go("translate")} onDone={() => go("done")} />;
  return <div className={`stack center-text ${styles.done}`}>
    <img className="mascot" src="/linguini-logo.png" width={124} height={124} alt="Linguini mascot" />
    <h1>You finished a photo lesson</h1>
    <Card lifted><div className="stack"><CheckIcon size={34} /><p>This guest lesson wasn’t saved and no Basil was awarded. Create an account to keep your photos, words and progress.</p></div></Card>
    <a className="btn btn--primary btn--block" href="/login?mode=signup" onClick={() => trackAction("guest_demo_signup_clicked", { language: lang })}>Create my free account <ArrowRightIcon /></a>
    <Button variant="quiet" block onClick={startOver}>Try another photo</Button>
  </div>;
}

function DemoPicker({ lang, setLang, uploading, error, fileInput, onUpload, onPick }: { lang: Lang; setLang: (lang: Lang) => void; uploading: boolean; error: string | null; fileInput: React.RefObject<HTMLInputElement | null>; onUpload: (file: File) => void; onPick: (scene: (typeof scenes)[number]) => void }) {
  return <div className="stack practice-select">
    <div className="stack-2"><p className={styles.eyebrow}>No account needed</p><h1>Try a photo lesson</h1><p className="muted">Upload a photo from your world or choose a ready-made scene. You’ll review the objects, learn their translations and try one task.</p></div>
    <label className="field"><span className="field__label">I want to learn</span><select className="input" value={lang} onChange={event => setLang(event.target.value as Lang)}>{languages.map(code => <option key={code} value={code}>{languageNames[code]}</option>)}</select></label>
    <div className="dashed-capture"><CameraIcon size={44} /><div className="stack-2 center-text"><h2>Use your own photo</h2><p className="muted small">JPEG, PNG or WebP · up to 10 MB</p></div><input ref={fileInput} className="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" disabled={uploading} onChange={event => { const file = event.target.files?.[0]; if (file) void onUpload(file); event.target.value = ""; }} /><Button variant="secondary" disabled={uploading} onClick={() => fileInput.current?.click()}><UploadIcon size={18} /> {uploading ? "Preparing lesson…" : "Upload photo"}</Button><p className="small muted">Guest photos are processed to build the demo and aren’t saved to an account.</p></div>
    {error ? <p role="alert">{error}</p> : null}
    <div className="stack-3"><h2>Or choose a ready-made scene</h2><div className="grid-2">{scenes.slice(0, 6).map(item => <button key={item.id} type="button" className="scene-pick" disabled={uploading} aria-label={`Choose ${item.title}`} onClick={() => onPick(item)}><img src={item.photo} alt="" /><span className={styles.sceneLabel}><b>{item.title}</b><span className="small muted">{item.place}</span></span></button>)}</div></div>
    <p className="small muted center-text">Nothing in the guest lesson is added to an account or counted toward progress.</p>
  </div>;
}

function ScenePhoto({ scene, scanning = false }: { scene: GuestScene; scanning?: boolean }) {
  return <figure className={styles.figure}><div className={styles.photo}><img src={scene.photo} alt={scene.alt} />{scene.words.slice(0, 5).map((word, index) => <span key={word.id} className={styles.marker} data-demo-marker style={{ left: `${word.x}%`, top: `${word.y}%` }}>{index + 1}</span>)}{scanning ? <span className={styles.scan} aria-hidden="true" /> : null}</div><figcaption><b>{scene.title}</b> · {scene.place}</figcaption></figure>;
}

function Review({ scene, selected, setSelected, onBack, onContinue }: { scene: GuestScene; selected: string[]; setSelected: React.Dispatch<React.SetStateAction<string[]>>; onBack: () => void; onContinue: () => void }) {
  return <div className="stack analysis-page"><div className={styles.titleRow}><h1>Review your scene</h1><Button variant="quiet" onClick={onBack}><CloseIcon size={18} /> Exit</Button></div><p className="muted">Linguini found five useful objects, plus words that describe where things are and what they look like.</p><ScenePhoto scene={scene} /><Card><div className="stack-3"><h2>Objects</h2><div className={styles.objectList}>{scene.words.map((word, index) => { const kept = selected.includes(word.id); return <button key={word.id} type="button" className={styles.objectRow} aria-pressed={kept} disabled={kept && selected.length <= 3} onClick={() => setSelected(current => kept ? current.filter(id => id !== word.id) : [...current, word.id])}><span className={styles.number}>{index + 1}</span><span>{word.source}</span><span className={styles.keep}>{kept ? <CheckIcon size={18} /> : "Add"}</span></button>; })}</div></div></Card><SupportingWords adjectives={scene.adjectives} prepositions={scene.prepositions} translated={false} /><Button block onClick={onContinue}>See translations <ArrowRightIcon /></Button></div>;
}

function Translation({ scene, words, lang, index, setIndex, onBack, onContinue }: { scene: GuestScene; words: GuestWord[]; lang: Lang; index: number; setIndex: (index: number) => void; onBack: () => void; onContinue: () => void }) {
  const safe = Math.min(index, words.length - 1), word = words[safe], last = safe === words.length - 1;
  return <div className="stack"><ProgressTrail value={safe + 1} total={words.length} label={`${safe + 1} of ${words.length} objects`} /><div className={styles.titleRow}><h1>Learn the words</h1><Button variant="quiet" onClick={onBack}>Back to review</Button></div><ScenePhoto scene={scene} /><Card lifted><div className={`stack center-text ${styles.wordCard}`}><p className="small muted">{word.source}</p><p className={styles.translation} lang={lang}>{word.translation}</p>{word.phoneticText ? <p className="muted">{word.phoneticText}</p> : null}<Button variant="secondary" onClick={() => speak(word.translation, lang)}><SpeakerIcon size={20} /> Hear it</Button></div></Card><SupportingWords adjectives={scene.adjectives} prepositions={scene.prepositions} translated lang={lang} /><div className={styles.actions}><Button variant="secondary" disabled={safe === 0} onClick={() => setIndex(safe - 1)}>Previous</Button><Button onClick={() => last ? onContinue() : setIndex(safe + 1)}>{last ? "Try a task" : "Next word"} <ArrowRightIcon /></Button></div></div>;
}

function SupportingWords({ adjectives, prepositions, translated, lang }: { adjectives: GuestTerm[]; prepositions: GuestTerm[]; translated: boolean; lang?: Lang }) {
  if (!adjectives.length && !prepositions.length) return null;
  return <Card><div className={styles.termSections}>{adjectives.length ? <TermGroup title="Describing words" terms={adjectives} translated={translated} lang={lang} /> : null}{prepositions.length ? <TermGroup title="Position words" terms={prepositions} translated={translated} lang={lang} /> : null}</div></Card>;
}

function TermGroup({ title, terms, translated, lang }: { title: string; terms: GuestTerm[]; translated: boolean; lang?: Lang }) {
  return <section className="stack-2"><h2>{title}</h2><div className={styles.termList}>{terms.map(term => <span className={styles.term} key={`${term.source}-${term.translation}`}><b lang={translated ? lang : undefined}>{translated ? term.translation : term.source}</b>{translated ? <small>{term.source}</small> : null}</span>)}</div></section>;
}

function Task({ scene, words, lang, picked, setPicked, onBack, onDone }: { scene: GuestScene; words: GuestWord[]; lang: Lang; picked: string | null; setPicked: (id: string) => void; onBack: () => void; onDone: () => void }) {
  const answer = words[0], correct = picked === answer.id;
  return <div className="stack"><ProgressTrail value={1} total={1} label="Demo task" /><div className={styles.titleRow}><h1>Choose the right word</h1><Button variant="quiet" onClick={onBack}>Back</Button></div><ScenePhoto scene={scene} /><Card><div className="stack"><p>Which {languageNames[lang]} word means <b>“{answer.source}”</b>?</p><div className={styles.choices}>{words.slice(0, 4).map(word => <button key={word.id} type="button" className={styles.choice} data-state={picked === word.id ? (word.id === answer.id ? "correct" : "wrong") : "idle"} onClick={() => !correct && setPicked(word.id)} lang={lang}>{word.translation}{picked === word.id && word.id === answer.id ? <CheckIcon size={19} /> : null}</button>)}</div>{picked ? <p className={correct ? "feedback feedback--good" : "feedback feedback--bad"}>{correct ? `Exactly — ${answer.translation} means ${answer.source}.` : "Almost. Look back at the words and try again."}</p> : null}</div></Card><Button block disabled={!correct} onClick={onDone}>Finish demo <ArrowRightIcon /></Button></div>;
}

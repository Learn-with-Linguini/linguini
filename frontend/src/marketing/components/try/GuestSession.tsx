import Image from "../Image";
import { useEffect, useMemo, useRef, useState } from "react";
import { languageNames, type Lang } from "../../data/types";
import { appLinks } from "../../lib/site";
import { speak } from "../../lib/speech";
import { trackAction } from "../../../lib/analytics";
import { ArrowLeft, ArrowRight, Check, Close, Refresh, Speaker } from "../icons";
import { LanguageToggle } from "./LanguageToggle";
import type { GuestScene, GuestWord } from "./demoApi";
import styles from "./session.module.css";

type Stage = "analyse" | "review" | "translate" | "task" | "done";
type HeadingRef = React.RefObject<HTMLHeadingElement | null>;

export function GuestSession({ scene, lang, onLangChange, onExit }: { scene: GuestScene; lang: Lang; onLangChange: (lang: Lang) => void; onExit: () => void }) {
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  const [stage, setStage] = useState<Stage>(() => reduceMotion ? "review" : "analyse"), [scanStep, setScanStep] = useState(0);
  const [selected, setSelected] = useState<string[]>(() => scene.words.map(word => word.id));
  const [wordIndex, setWordIndex] = useState(0);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const words = useMemo(() => scene.words.filter(word => selected.includes(word.id)), [scene.words, selected]);
  const scanLines = useMemo(() => ["Looking closely at your photo", `Spotted ${scene.words.map(word => word.source).join(", ")}`, `Translating the scene into ${languageNames[lang]}`, "Building one quick practice task"], [lang, scene.words]);

  useEffect(() => { headingRef.current?.focus({ preventScroll: true }); }, []);
  useEffect(() => { if (stage !== "analyse") return; if (scanStep >= scanLines.length) { const done = window.setTimeout(() => setStage("review"), 500); return () => window.clearTimeout(done); } const next = window.setTimeout(() => setScanStep(value => value + 1), 650); return () => window.clearTimeout(next); }, [scanLines.length, scanStep, stage]);
  function go(next: Stage) { trackAction("guest_demo_stage_viewed", { stage: next, source: scene.uploaded ? "upload" : "sample" }); if (next === "done") trackAction("guest_demo_completed", { language: lang, source: scene.uploaded ? "upload" : "sample" }); setStage(next); requestAnimationFrame(() => headingRef.current?.focus({ preventScroll: true })); }

  return <div className={styles.session}>
    <div className={styles.bar}><button type="button" className="btn-quiet" onClick={onExit}><Close size={18} /> Pick another photo</button>{scene.uploaded ? <span className="small">Learning {languageNames[lang]}</span> : <LanguageToggle value={lang} onChange={onLangChange} compact />}</div>
    <div className={styles.layout}>
      <div className={styles.visual} style={{ "--ar": scene.width / scene.height } as React.CSSProperties}>
        <div className={styles.guestPhoto}><Image src={scene.photo} alt={scene.alt} fill sizes="(max-width: 960px) 100vw, 680px" priority />{stage !== "analyse" || scanStep >= 2 ? scene.words.map((word, index) => <span key={word.id} className={styles.demoMarker} style={{ left: `${word.x}%`, top: `${word.y}%` }} aria-label={`${index + 1}. ${word.source}`}>{index + 1}</span>) : null}{stage === "analyse" ? <span className={styles.scan} aria-hidden="true" /> : null}</div>
        <p className={styles.caption}><span>{scene.title}</span><span aria-hidden="true">·</span><span>{scene.place}</span></p>
      </div>
      <div className={styles.panel}><div className={styles.stage} key={`${stage}-${lang}`}>
        {stage === "analyse" ? <><h2 ref={headingRef} tabIndex={-1} className={styles.title}>Reading your photo…</h2><ol className={styles.prompter} aria-live="polite">{scanLines.map((line, index) => <li key={line} className={styles.prompt} data-state={index < scanStep ? "done" : index === scanStep ? "active" : "waiting"}><span className={styles.promptIcon} aria-hidden="true">{index < scanStep ? <Check size={14} /> : <span className={styles.spinner} />}</span>{line}</li>)}</ol></> : null}
        {stage === "review" ? <><h2 ref={headingRef} tabIndex={-1} className={styles.title}>Found {scene.words.length} things to learn</h2><p className={styles.lede}>Choose the objects you want in this short lesson.</p><ul className={styles.found}>{scene.words.map((word, index) => { const on = selected.includes(word.id); return <li key={word.id}><button type="button" className={styles.foundChip} aria-pressed={on} disabled={on && selected.length <= 3} onClick={() => setSelected(current => on ? current.filter(id => id !== word.id) : [...current, word.id])}><span className={styles.foundNum}>{index + 1}</span><span className={styles.foundWord}>{word.source}</span><span className={styles.foundTick} aria-hidden="true">{on ? <Check size={16} /> : null}</span></button></li>; })}</ul><p className={styles.hint}>Keep at least three words.</p><button type="button" className="btn btn--block" onClick={() => go("translate")}>See the translations <ArrowRight size={20} /></button></> : null}
        {stage === "translate" ? <TranslationStage words={words} lang={lang} index={wordIndex} setIndex={setWordIndex} headingRef={headingRef} onDone={() => go("task")} /> : null}
        {stage === "task" ? <DemoTask words={words} lang={lang} headingRef={headingRef} onDone={() => go("done")} /> : null}
        {stage === "done" ? <><h2 ref={headingRef} tabIndex={-1} className={styles.title}>You finished a photo lesson</h2><p className={styles.lede}>This guest lesson wasn’t saved and no points were awarded. Create an account to keep your photos, words and progress.</p><a href={appLinks.signUp} className="btn btn--block" onClick={() => trackAction("guest_demo_signup_clicked", { language: lang })}>Create my free account <ArrowRight size={20} /></a><button type="button" className={`btn-quiet ${styles.skip}`} onClick={onExit}><Refresh size={18} /> Try another photo</button></> : null}
      </div></div>
    </div>
  </div>;
}

function TranslationStage({ words, lang, index, setIndex, headingRef, onDone }: { words: GuestWord[]; lang: Lang; index: number; setIndex: (value: number) => void; headingRef: HeadingRef; onDone: () => void }) {
  const safe = Math.min(index, words.length - 1), word = words[safe], last = safe === words.length - 1;
  return <><div className={styles.titleRow}><h2 ref={headingRef} tabIndex={-1} className={styles.title}>Words in {languageNames[lang]}</h2><span className={styles.count}>{safe + 1} of {words.length}</span></div><div className={styles.says}><p className={styles.clue} lang={lang}>{word.translation}</p><p className={styles.clueEn}>{word.source}{word.phoneticText ? ` · ${word.phoneticText}` : ""}</p><button type="button" className={styles.saysSpeak} onClick={() => speak(word.translation, lang)} aria-label={`Hear ${word.translation}`}><Speaker size={18} /></button></div><div className={styles.pair}><button type="button" className="btn btn--teal" disabled={safe === 0} onClick={() => setIndex(safe - 1)}><ArrowLeft size={18} /> Previous</button>{last ? <button type="button" className="btn" onClick={onDone}>Try a task <ArrowRight size={18} /></button> : <button type="button" className="btn btn--teal" onClick={() => setIndex(safe + 1)}>Next word <ArrowRight size={18} /></button>}</div></>;
}

function DemoTask({ words, lang, headingRef, onDone }: { words: GuestWord[]; lang: Lang; headingRef: HeadingRef; onDone: () => void }) {
  const answer = words[0], choices = useMemo(() => words.slice(0, 4), [words]);
  const [picked, setPicked] = useState<string | null>(null), correct = picked === answer.id;
  return <><h2 ref={headingRef} tabIndex={-1} className={styles.title}>Choose the right word</h2><p className={styles.lede}>Which {languageNames[lang]} word means <b>“{answer.source}”</b>?</p><fieldset className={styles.choices}><legend className="visually-hidden">Your answer</legend>{choices.map(choice => <button key={choice.id} type="button" className={styles.choice} data-state={picked === choice.id ? (choice.id === answer.id ? "correct" : "wrong") : correct ? "muted" : "idle"} onClick={() => !correct && setPicked(choice.id)} lang={lang}>{choice.id === picked && correct ? <Check size={18} /> : null}{choice.translation}</button>)}</fieldset><div className={styles.feedbackSlot} aria-live="polite">{picked ? <p className={`${styles.feedback} ${correct ? styles.good : styles.bad}`}>{correct ? `Exactly — ${answer.translation} means ${answer.source}.` : "Not quite. Look through the translated words and try again."}</p> : null}</div><button type="button" className="btn btn--block" disabled={!correct} onClick={onDone}>Finish demo <ArrowRight size={20} /></button></>;
}

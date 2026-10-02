"use client";

import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";
import { scenes } from "@/data/scenes";
import { languageNames, type Lang, type Scene } from "@/data/types";
import { appLinks } from "@/lib/site";
import { speak } from "@/lib/speech";
import { stripArticle } from "@/lib/words";
import { ShareBar } from "../ShareBar";
import { JournalCard } from "../product/JournalCard";
import { PhotoMarkers } from "../product/PhotoMarkers";
import { WordCard } from "../product/WordCard";
import { ArrowLeft, ArrowRight, Check, Close, Eye, Refresh, Speaker } from "../icons";
import { LanguageToggle } from "./LanguageToggle";
import styles from "./session.module.css";

type Stage = "analyse" | "review" | "words" | "ispy" | "blank" | "build" | "journal" | "done";

const taskStages: { stage: Stage; label: string }[] = [
  { stage: "words", label: "Learn the words" },
  { stage: "ispy", label: "I-Spy" },
  { stage: "blank", label: "Describe the scene" },
  { stage: "build", label: "Build a sentence" },
];

const XP = { task: 10, ispy: 15, journal: 20 } as const;

type SessionProps = {
  scene: Scene;
  lang: Lang;
  onLangChange: (lang: Lang) => void;
  onExit: () => void;
};

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function Session({ scene, lang, onLangChange, onExit }: SessionProps) {
  const [stage, setStage] = useState<Stage>(() => (prefersReducedMotion() ? "review" : "analyse"));
  const [scanStep, setScanStep] = useState(0);
  const [selected, setSelected] = useState<string[]>(() => scene.words.map(word => word.id));
  const [wordIndex, setWordIndex] = useState(0);
  const [xp, setXp] = useState(0);
  const [focusId, setFocusId] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const visualRef = useRef<HTMLDivElement>(null);

  const words = useMemo(() => scene.words.filter(word => selected.includes(word.id)), [scene.words, selected]);
  const scanLines = useMemo(
    () => [
      "Looking closely at your photo",
      `Spotted ${scene.words.map(word => word.en).join(", ")}`,
      `Choosing beginner ${languageNames[lang]} for each one`,
      "Adding articles, pronunciation and audio",
    ],
    [scene.words, lang],
  );

  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (stage !== "analyse") return;
    if (scanStep >= scanLines.length) {
      const done = window.setTimeout(() => setStage("review"), 650);
      return () => window.clearTimeout(done);
    }
    const next = window.setTimeout(() => setScanStep(step => step + 1), scanStep === 0 ? 700 : 850);
    return () => window.clearTimeout(next);
  }, [stage, scanStep, scanLines.length]);

  function go(next: Stage, gained = 0) {
    if (gained) setXp(value => value + gained);
    setStage(next);
    setFocusId(null);
    requestAnimationFrame(() => {
      headingRef.current?.focus({ preventScroll: true });
      const panel = panelRef.current;
      if (!panel) return;
      // On small screens the photo sticks under the header, so keep the panel start just below it.
      const stacked = window.matchMedia("(max-width: 960px)").matches;
      const offset = stacked ? 64 + (visualRef.current?.offsetHeight ?? 0) + 8 : 96;
      const top = panel.getBoundingClientRect().top;
      if (top < offset) {
        window.scrollTo({ top: top + window.scrollY - offset, behavior: prefersReducedMotion() ? "auto" : "smooth" });
      }
    });
  }

  const taskIndex = taskStages.findIndex(task => task.stage === stage);
  const markersVisible = stage !== "analyse" || scanStep >= 2;
  const activeId = stage === "words" ? words[wordIndex]?.id ?? null : focusId;
  const hiddenIds = scene.words.filter(word => !selected.includes(word.id)).map(word => word.id);
  const showLabels = stage === "review" || stage === "blank" || stage === "build";

  return (
    <div className={styles.session}>
      <div className={styles.bar}>
        <button type="button" className="btn-quiet" onClick={onExit}>
          <Close size={18} /> Pick another photo
        </button>
        <LanguageToggle value={lang} onChange={onLangChange} compact />
      </div>

      <div className={styles.layout}>
        <div
          ref={visualRef}
          className={styles.visual}
          data-compact={taskIndex >= 0}
          style={{ "--ar": scene.width / scene.height } as React.CSSProperties}
        >
          <PhotoMarkers
            scene={scene}
            lang={lang}
            labels={showLabels}
            activeId={activeId}
            hiddenIds={markersVisible ? hiddenIds : scene.words.map(word => word.id)}
            priority
            sizes="(max-width: 960px) 100vw, 680px"
            className={styles.photo}
            style={{ viewTransitionName: "picked-photo" }}
          >
            {stage === "analyse" ? <span className={styles.scan} aria-hidden="true" /> : null}
          </PhotoMarkers>
          <p className={styles.caption}>
            <span>{scene.title}</span>
            <span aria-hidden="true">·</span>
            <span>{scene.place}</span>
          </p>
        </div>

        <div className={styles.panel} ref={panelRef}>
          {taskIndex >= 0 ? (
            <div className={styles.progress}>
              <div className={styles.track} aria-hidden="true">
                <span style={{ width: `${((taskIndex + 1) / taskStages.length) * 100}%` }} />
              </div>
              <div className={styles.progressMeta}>
                <span>Task {taskIndex + 1} of {taskStages.length}</span>
                <span className={styles.xp}>{xp} XP</span>
              </div>
            </div>
          ) : null}

          <div className={styles.stage} key={`${stage}-${lang}`}>
            {stage === "analyse" ? (
              <>
                <h2 ref={headingRef} tabIndex={-1} className={styles.title}>Reading your photo…</h2>
                <ol className={styles.prompter} aria-live="polite">
                  {scanLines.map((line, index) => (
                    <li
                      key={line}
                      className={styles.prompt}
                      data-state={index < scanStep ? "done" : index === scanStep ? "active" : "waiting"}
                    >
                      <span className={styles.promptIcon} aria-hidden="true">
                        {index < scanStep ? <Check size={14} /> : <span className={styles.spinner} />}
                      </span>
                      {line}
                    </li>
                  ))}
                </ol>
                <button type="button" className={`btn-quiet ${styles.skip}`} onClick={() => go("review")}>
                  Skip the scan
                </button>
              </>
            ) : null}

            {stage === "review" ? (
              <>
                <h2 ref={headingRef} tabIndex={-1} className={styles.title}>
                  Found {scene.words.length} things to learn
                </h2>
                <p className={styles.lede}>
                  You’re in charge: untick anything you don’t want. Words appear in {languageNames[lang]} on the photo.
                </p>
                <ul className={styles.found}>
                  {scene.words.map((word, index) => {
                    const on = selected.includes(word.id);
                    return (
                      <li key={word.id}>
                        <button
                          type="button"
                          className={styles.foundChip}
                          aria-pressed={on}
                          disabled={on && selected.length <= 3}
                          onClick={() =>
                            setSelected(current => (on ? current.filter(id => id !== word.id) : [...current, word.id]))
                          }
                          onMouseEnter={() => setFocusId(word.id)}
                          onMouseLeave={() => setFocusId(null)}
                          onFocus={() => setFocusId(word.id)}
                          onBlur={() => setFocusId(null)}
                        >
                          <span className={styles.foundNum}>{index + 1}</span>
                          <span className={styles.foundWord}>
                            <span lang={lang}>{word[lang].word}</span>
                            <span className={styles.foundEn}>{word.en}</span>
                          </span>
                          <span className={styles.foundTick} aria-hidden="true">{on ? <Check size={16} /> : null}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
                <p className={styles.hint}>Keep at least three words.</p>
                <button type="button" className="btn btn--block" onClick={() => go("words")}>
                  Start learning {words.length} words <ArrowRight size={20} />
                </button>
              </>
            ) : null}

            {stage === "words" ? (
              <WordsStage
                words={words}
                lang={lang}
                index={wordIndex}
                setIndex={setWordIndex}
                headingRef={headingRef}
                onDone={() => go("ispy", XP.task)}
              />
            ) : null}

            {stage === "ispy" ? (
              <ISpyStage scene={scene} lang={lang} headingRef={headingRef} setFocusId={setFocusId} onDone={gained => go("blank", gained)} />
            ) : null}

            {stage === "blank" ? (
              <BlankStage scene={scene} lang={lang} headingRef={headingRef} onDone={gained => go("build", gained)} />
            ) : null}

            {stage === "build" ? (
              <BuildStage scene={scene} lang={lang} headingRef={headingRef} onDone={gained => go("journal", gained)} />
            ) : null}

            {stage === "journal" ? (
              <JournalStage scene={scene} lang={lang} words={words.map(word => word[lang].word)} headingRef={headingRef} onDone={() => go("done", XP.journal)} />
            ) : null}

            {stage === "done" ? (
              <DoneStage scene={scene} lang={lang} xp={xp} words={words.map(word => word[lang].word)} headingRef={headingRef} onRestart={onExit} />
            ) : null}
          </div>

          {taskIndex >= 0 ? (
            <button type="button" className={`btn-quiet ${styles.skip}`} onClick={() => go("journal")}>
              Skip to the journal
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

type HeadingRef = React.RefObject<HTMLHeadingElement | null>;

function WordsStage({
  words,
  lang,
  index,
  setIndex,
  headingRef,
  onDone,
}: {
  words: Scene["words"];
  lang: Lang;
  index: number;
  setIndex: (index: number) => void;
  headingRef: HeadingRef;
  onDone: () => void;
}) {
  const safeIndex = Math.min(index, words.length - 1);
  const word = words[safeIndex];
  const last = safeIndex === words.length - 1;
  return (
    <>
      <div className={styles.titleRow}>
        <h2 ref={headingRef} tabIndex={-1} className={styles.title}>Learn the words in this scene</h2>
        <span className={styles.count}>{safeIndex + 1} of {words.length}</span>
      </div>
      <div className={styles.deck}>
        <span className={styles.deckShadow} aria-hidden="true" />
        <WordCard key={word.id} word={word} lang={lang} className={styles.dealt} />
      </div>
      <div className={styles.pair}>
        <button
          type="button"
          className="btn btn--teal"
          style={safeIndex === 0 ? { visibility: "hidden" } : undefined}
          onClick={() => setIndex(safeIndex - 1)}
        >
          <ArrowLeft size={18} /> Previous
        </button>
        {last ? (
          <button type="button" className="btn" onClick={onDone}>
            Play I-Spy <ArrowRight size={18} />
          </button>
        ) : (
          <button type="button" className="btn btn--teal" onClick={() => setIndex(safeIndex + 1)}>
            Next word <ArrowRight size={18} />
          </button>
        )}
      </div>
    </>
  );
}

type Verdict = { correct: boolean; text: React.ReactNode } | null;

function Feedback({ verdict }: { verdict: Verdict }) {
  return (
    <div className={styles.feedbackSlot} aria-live="polite">
      {verdict ? (
        <p className={`${styles.feedback} ${verdict.correct ? styles.good : styles.bad}`}>
          <span className={styles.feedbackIcon} aria-hidden="true">{verdict.correct ? <Check size={16} /> : <Refresh size={16} />}</span>
          <span>{verdict.text}</span>
        </p>
      ) : null}
    </div>
  );
}

function ISpyStage({
  scene,
  lang,
  headingRef,
  setFocusId,
  onDone,
}: {
  scene: Scene;
  lang: Lang;
  headingRef: HeadingRef;
  setFocusId: (id: string | null) => void;
  onDone: (xp: number) => void;
}) {
  const round = scene.ispy[lang];
  const [picked, setPicked] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [showEnglish, setShowEnglish] = useState(false);
  const solved = picked === round.answer;
  const answerWord = scene.words.find(word => word[lang].word === round.answer);

  function choose(choice: string) {
    if (solved) return;
    setPicked(choice);
    setTries(value => value + 1);
    if (choice === round.answer && answerWord) setFocusId(answerWord.id);
  }

  const verdict: Verdict = picked
    ? solved
      ? { correct: true, text: <>Nice catch — <b lang={lang}>{round.answer}</b> means the {answerWord?.en}. +{XP.ispy} XP</> }
      : { correct: false, text: <>Not quite. Look at the photo again and have another go.</> }
    : null;

  return (
    <>
      <h2 ref={headingRef} tabIndex={-1} className={styles.title}>I-Spy with Linguini</h2>
      <div className={styles.says}>
        <div className={styles.saysTop}>
          <Image src="/brand/mascot-180.png" alt="" width={36} height={36} className={styles.saysMascot} />
          <span className={styles.saysLabel}>Linguini says</span>
          <button type="button" className={styles.saysSpeak} onClick={() => speak(round.clue, lang)} aria-label="Hear the clue">
            <Speaker size={18} />
          </button>
        </div>
        <p className={styles.clue} lang={lang}>{round.clue}</p>
        {showEnglish ? (
          <p className={styles.clueEn}>{round.clueEn}</p>
        ) : (
          <button type="button" className={`btn-quiet ${styles.translate}`} onClick={() => setShowEnglish(true)}>
            <Eye size={18} /> Show translation
          </button>
        )}
      </div>
      <fieldset className={styles.choices}>
        <legend className="visually-hidden">Your answer</legend>
        {round.choices.map(choice => {
          const state = picked === choice ? (choice === round.answer ? "correct" : "wrong") : solved ? "muted" : "idle";
          return (
            <button key={choice} type="button" className={styles.choice} data-state={state} onClick={() => choose(choice)} lang={lang} aria-pressed={picked === choice}>
              {state === "correct" ? <Check size={18} /> : null}
              {choice}
            </button>
          );
        })}
      </fieldset>
      <Feedback verdict={verdict} />
      <button type="button" className="btn btn--block" disabled={!solved} onClick={() => onDone(tries === 1 ? XP.ispy : XP.task)}>
        Next task <ArrowRight size={20} />
      </button>
    </>
  );
}

function BlankStage({ scene, lang, headingRef, onDone }: { scene: Scene; lang: Lang; headingRef: HeadingRef; onDone: (xp: number) => void }) {
  const round = scene.blank[lang];
  const [picked, setPicked] = useState<string | null>(null);
  const solved = picked === round.answer;
  const [before, after] = round.sentence.split("___");

  const verdict: Verdict = picked
    ? solved
      ? { correct: true, text: <>That’s it. +{XP.task} XP</> }
      : { correct: false, text: <>Close — check whether the noun should be singular or plural.</> }
    : null;

  return (
    <>
      <h2 ref={headingRef} tabIndex={-1} className={styles.title}>Describe the scene</h2>
      <p className={styles.lede}>Pick the word that completes the sentence.</p>
      <div className={styles.sentenceCard}>
        <p className={styles.sentence} lang={lang}>
          {before}
          <span className={`${styles.gap} ${picked ? (solved ? styles.gapGood : styles.gapBad) : ""}`}>
            {picked ?? " "}
          </span>
          {after}
        </p>
        <p className={styles.sentenceEn}>{round.en}</p>
      </div>
      <fieldset className={styles.choices}>
        <legend className="visually-hidden">Missing word</legend>
        {round.options.map(option => {
          const state = picked === option ? (option === round.answer ? "correct" : "wrong") : solved ? "muted" : "idle";
          return (
            <button key={option} type="button" className={styles.choice} data-state={state} lang={lang} onClick={() => !solved && setPicked(option)} aria-pressed={picked === option}>
              {state === "correct" ? <Check size={18} /> : null}
              {option}
            </button>
          );
        })}
      </fieldset>
      <Feedback verdict={verdict} />
      <button type="button" className="btn btn--block" disabled={!solved} onClick={() => onDone(XP.task)}>
        Next task <ArrowRight size={20} />
      </button>
    </>
  );
}

function shuffle<T>(items: T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function BuildStage({ scene, lang, headingRef, onDone }: { scene: Scene; lang: Lang; headingRef: HeadingRef; onDone: (xp: number) => void }) {
  const round = scene.build[lang];
  const tiles = useMemo(() => {
    const indexed = round.tokens.map((text, id) => ({ id, text }));
    let mixed = shuffle(indexed);
    for (let attempt = 0; attempt < 5 && mixed.every((tile, i) => tile.id === i); attempt++) mixed = shuffle(indexed);
    return mixed;
  }, [round.tokens]);
  const [placed, setPlaced] = useState<number[]>([]);
  const [checked, setChecked] = useState<boolean | null>(null);
  const answer = placed.map(id => round.tokens[id]).join(" ");
  const correct = answer === round.tokens.join(" ");
  const complete = placed.length === round.tokens.length;

  function toggle(id: number) {
    if (checked) return;
    setChecked(null);
    setPlaced(current => (current.includes(id) ? current.filter(item => item !== id) : [...current, id]));
  }

  const verdict: Verdict =
    checked === null ? null : checked ? { correct: true, text: <>Perfect sentence. +{XP.task} XP</> } : { correct: false, text: <>Almost — tap a tile to take it back and try another order.</> };

  return (
    <>
      <h2 ref={headingRef} tabIndex={-1} className={styles.title}>Build a sentence</h2>
      <p className={styles.lede}>Say it in {languageNames[lang]}: <b>“{round.en}”</b></p>
      <fieldset className={styles.answer} data-state={checked === null ? "idle" : checked ? "correct" : "wrong"}>
        <legend className="visually-hidden">Your sentence</legend>
        {placed.length === 0 ? <span className={styles.answerHint}>Tap the tiles in order</span> : null}
        {placed.map(id => (
          <button key={id} type="button" className={`${styles.tile} ${styles.tilePlaced}`} onClick={() => toggle(id)} lang={lang}>
            {round.tokens[id]}
          </button>
        ))}
      </fieldset>
      <fieldset className={styles.bank}>
        <legend className="visually-hidden">Word tiles</legend>
        {tiles.map(tile => (
          <button
            key={tile.id}
            type="button"
            className={styles.tile}
            data-used={placed.includes(tile.id)}
            disabled={placed.includes(tile.id)}
            onClick={() => toggle(tile.id)}
            lang={lang}
          >
            {tile.text}
          </button>
        ))}
      </fieldset>
      <Feedback verdict={verdict} />
      {checked ? (
        <button type="button" className="btn btn--block" onClick={() => onDone(XP.task)}>
          Write today’s journal <ArrowRight size={20} />
        </button>
      ) : (
        <button type="button" className="btn btn--block" disabled={!complete} onClick={() => setChecked(correct)}>
          Check sentence
        </button>
      )}
    </>
  );
}

function JournalStage({
  scene,
  lang,
  words,
  headingRef,
  onDone,
}: {
  scene: Scene;
  lang: Lang;
  words: string[];
  headingRef: HeadingRef;
  onDone: () => void;
}) {
  const draft = scene.journal[lang];
  const [title, setTitle] = useState(draft.title);
  const [body, setBody] = useState(draft.body);
  const used = words.filter(word => body.toLowerCase().includes(stripArticle(word).toLowerCase()));

  return (
    <>
      <h2 ref={headingRef} tabIndex={-1} className={styles.title}>Keep today in your journal</h2>
      <p className={styles.lede}>Linguini drafted a few lines with your new words. Make them yours.</p>
      <label className={styles.field}>
        <span>Title</span>
        <input value={title} onChange={event => setTitle(event.target.value)} maxLength={60} />
      </label>
      <label className={styles.field}>
        <span>Entry</span>
        <textarea value={body} onChange={event => setBody(event.target.value)} rows={5} lang={lang} maxLength={420} />
      </label>
      <p className={styles.usedWords}>
        <b>{used.length} of {words.length} new words used</b>
        {words.map(word => (
          <span key={word} className={styles.usedChip} data-used={used.includes(word)} lang={lang}>{word}</span>
        ))}
      </p>
      <button
        type="button"
        className="btn btn--block"
        disabled={!title.trim() || !body.trim()}
        onClick={() => {
          sessionStorageSafeSet(`journal-${scene.id}-${lang}`, JSON.stringify({ title, body }));
          onDone();
        }}
      >
        Save to journal <Check size={20} />
      </button>
    </>
  );
}

function sessionStorageSafeSet(key: string, value: string) {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    /* storage can be unavailable in private windows */
  }
}

function sessionStorageSafeGet(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

const days = ["M", "T", "W", "T", "F", "S", "S"];

function DoneStage({
  scene,
  lang,
  xp,
  words,
  headingRef,
  onRestart,
}: {
  scene: Scene;
  lang: Lang;
  xp: number;
  words: string[];
  headingRef: HeadingRef;
  onRestart: () => void;
}) {
  const [entry] = useState(() => {
    const saved = sessionStorageSafeGet(`journal-${scene.id}-${lang}`);
    return saved ? (JSON.parse(saved) as { title: string; body: string }) : scene.journal[lang];
  });
  const [today] = useState(() => new Date());
  // This stage only ever renders in the browser, after the visitor has played the session.
  const origin = window.location.origin;

  const todayIndex = (today.getDay() + 6) % 7;
  const date = today.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "short" });
  const shareUrl = `${origin}/share?photo=${encodeURIComponent(scene.id)}&lang=${lang}&words=${encodeURIComponent(words.slice(0, 5).join(","))}`;

  return (
    <>
      <div className={styles.doneHead}>
        <h2 ref={headingRef} tabIndex={-1} className={styles.title}>Saved. That’s a day well spent.</h2>
        <p className={styles.xpBig}>+{xp} XP</p>
      </div>
      <div className={styles.streak} aria-label={`Streak: today checked in`}>
        {days.map((day, index) => (
          <span key={index} className={styles.streakDay} data-state={index === todayIndex ? "today" : index < todayIndex ? "past" : "future"}>
            {index === todayIndex ? <Image src="/pasta/farfalle.webp" alt="" width={36} height={28} /> : <span className={styles.streakDot} />}
            <span>{day}</span>
          </span>
        ))}
      </div>
      <JournalCard
        photos={[scene, ...scenes.filter(other => other.id !== scene.id).slice(0, 3)].map(item => ({ src: item.photo, alt: item.alt }))}
        title={entry.title}
        body={entry.body}
        date={date}
        lang={lang}
        highlight={words}
        className={styles.savedCard}
        headingLevel="p"
      />
      <a href={appLinks.signUp} className="btn btn--block">
        Do this with your own photos <ArrowRight size={20} />
      </a>
      <div className={styles.shareRow}>
        <p>Share your journal page</p>
        <ShareBar url={shareUrl} text={`I just learned ${words.length} ${languageNames[lang]} words from one photo on Linguini.`} />
      </div>
      <button type="button" className={`btn-quiet ${styles.skip}`} onClick={onRestart}>
        <Refresh size={18} /> Try another photo
      </button>
    </>
  );
}

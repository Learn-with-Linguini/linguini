import Image from "./Image";
import { useEffect, useRef, useState } from "react";
import { getScene } from "../data/scenes";
import { speak } from "../lib/speech";
import { Basil, Check, Close, Mic, Plus, Speaker, Users } from "./icons";
import { Reveal } from "./Reveal";
import styles from "./Features.module.css";

const pastas = [
  { id: "farfalle", name: "Farfalle", line: "Bow-tie ready. Here for the streaks.", w: 360, h: 281 },
  { id: "fusilli", name: "Fusilli", line: "Twisty, tenacious, never skips a day.", w: 276, h: 360 },
  { id: "penne", name: "Penne", line: "Straight to the point. Loves grammar.", w: 360, h: 341 },
  { id: "macaroni", name: "Macaroni", line: "Small, cheerful, collects every word.", w: 360, h: 333 },
];

const week = [
  { d: "M", on: true },
  { d: "T", on: true },
  { d: "W", on: true },
  { d: "T", on: false },
  { d: "F", on: true },
  { d: "S", on: true },
  { d: "S", on: true },
];

const desk = getScene("desk-flatlay")!;
const roomObjects = ["notebook", "pencil", "phone", "plant"].map(id => desk.words.find(word => word.id === id)!);
const roomClues = [
  { id: "plant", text: "Veo algo verde encima del móvil." },
  { id: "pencil", text: "Veo algo amarillo a la derecha de la libreta." },
  { id: "phone", text: "Veo algo negro debajo de la planta." },
];

function SpyTogether() {
  const [clue, setClue] = useState<string | null>(null);
  const [tried, setTried] = useState<string[]>([]);
  const found = clue !== null && tried.includes(clue);
  const missed = !found && tried.length > 0;

  const chooseClue = (id: string) => {
    setClue(id);
    setTried([]);
  };

  return (
    <div className={styles.room}>
      <div className={styles.roomBar}>
        <strong>Photo 1 of 3</strong>
        <span>{found ? 1 : 0} found together</span>
      </div>
      <div className={styles.spyPhoto}>
        <Image src={desk.photo} alt={desk.alt} fill sizes="(max-width: 720px) 90vw, 380px" className={styles.spyImg} />
        {roomObjects.map((object, index) => {
          const isTarget = found && object.id === clue;
          return (
            <button
              key={object.id}
              type="button"
              className={`${styles.spyMarker} ${isTarget ? styles.spyFound : ""}`}
              style={{ left: `${object.x}%`, top: `${Math.max(10, object.y)}%` }}
              aria-label={`Object ${index + 1}`}
              aria-pressed={tried.includes(object.id)}
              disabled={!clue || found || tried.includes(object.id)}
              onClick={() => setTried(current => [...current, object.id])}
            >
              {isTarget ? <Check size={14} /> : index + 1}
            </button>
          );
        })}
      </div>
      <p className={styles.roomStep}>{clue ? "Now spot it, the way your friend would" : "Give your friend a clue"}</p>
      <div className={styles.clues} role="group" aria-label="Choose your clue">
        {roomClues.map(option => (
          <button
            key={option.id}
            type="button"
            className={styles.clueChip}
            aria-pressed={clue === option.id}
            onClick={() => chooseClue(option.id)}
            lang="es"
          >
            {option.text}
          </button>
        ))}
      </div>
      <p className={styles.roomFeedback} data-tone={found ? "good" : missed ? "warn" : undefined} role="status">
        {found ? (
          <>
            <Check size={16} /> You found it together! <span className={styles.basilTotal}><Basil size={14} /> +20 Basil each</span>
          </>
        ) : missed ? (
          "Not quite. Try one more object."
        ) : clue ? (
          "Tap the numbered marker that matches the clue."
        ) : (
          "Your friend sees only the clue, never your marker."
        )}
      </p>
    </div>
  );
}

const readyScenes = ["cafe-interior", "paris-rooftops", "hillside-street"].map(id => getScene(id)!);

function ReadyScenes() {
  const [picked, setPicked] = useState(readyScenes[0].id);
  const scene = readyScenes.find(item => item.id === picked)!;

  return (
    <div className={styles.scenes}>
      <div className={styles.scenePicks} role="group" aria-label="Choose a ready-made scene">
        {readyScenes.map(item => (
          <button key={item.id} type="button" className={styles.scenePick} aria-pressed={picked === item.id} onClick={() => setPicked(item.id)}>
            <span className={styles.sceneThumb}>
              <Image src={item.photo} alt="" fill sizes="120px" className={styles.spyImg} />
            </span>
            <span>{item.title}</span>
          </button>
        ))}
      </div>
      <div className={styles.sceneReady} aria-live="polite">
        <p>
          <b>{scene.words.length} words</b> ready in {scene.title}
        </p>
        <ul className={styles.sceneWords}>
          {scene.words.slice(0, 4).map(word => (
            <li key={word.id} lang="es">{word.es.word}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

type MicState = "idle" | "listening" | "ready" | "typing";

function MicCheck() {
  const [state, setState] = useState<MicState>("idle");
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const listen = () => {
    window.clearTimeout(timer.current);
    setState("listening");
    timer.current = window.setTimeout(() => setState("ready"), 1600);
  };

  const typeInstead = () => {
    window.clearTimeout(timer.current);
    setState("typing");
  };

  return (
    <div className={styles.voice}>
      <div className={styles.voiceTop}>
        <button type="button" className={styles.voiceSpeak} onClick={() => speak("el puente rojo", "es")} aria-label="Hear “el puente rojo”">
          <Speaker size={22} />
        </button>
        <div className={styles.voiceLine}>
          <p className={styles.voicePhrase} lang="es">el puente rojo</p>
          <p className={styles.voiceIpa}>/el ˈpwente ˈroxo/ · the red bridge</p>
        </div>
      </div>
      <div className={styles.voiceMic} data-state={state}>
        <button
          type="button"
          className={styles.micIcon}
          onClick={listen}
          disabled={state === "listening"}
          aria-label={state === "listening" ? "Listening" : "Test my microphone"}
        >
          <Mic size={20} />
        </button>
        <span className={styles.wave} aria-hidden="true">
          {Array.from({ length: 14 }, (_, i) => (
            <span key={i} style={{ "--i": i, "--s": [0.35, 0.6, 0.9, 0.55, 1, 0.7, 0.4, 0.8, 0.95, 0.5, 0.65, 0.3, 0.75, 0.45][i] } as React.CSSProperties} />
          ))}
        </span>
        <span className={styles.heard} role="status">
          {state === "idle" ? "Tap to test" : state === "listening" ? "Listening…" : state === "ready" ? <><Check size={16} /> Mic ready</> : "Typing is ready instead"}
        </span>
      </div>
      <button type="button" className={styles.typeInstead} onClick={typeInstead} aria-pressed={state === "typing"}>
        Use typing instead
      </button>
    </div>
  );
}

type Status = "new" | "learning" | "mastered";
const statusTabs: { id: Status | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "new", label: "New" },
  { id: "learning", label: "Learning" },
  { id: "mastered", label: "Mastered" },
];
const wordBank: { place: string; words: { word: string; en: string; status: Status }[] }[] = [
  {
    place: "Across the bay",
    words: [
      { word: "el puente", en: "the bridge", status: "mastered" },
      { word: "la torre", en: "the tower", status: "learning" },
      { word: "el mar", en: "the sea", status: "new" },
    ],
  },
  {
    place: "Study day",
    words: [
      { word: "la libreta", en: "the notebook", status: "mastered" },
      { word: "el lápiz", en: "the pencil", status: "mastered" },
      { word: "la planta", en: "the plant", status: "learning" },
    ],
  },
];

function WordBank() {
  const [filter, setFilter] = useState<Status | "all">("all");

  return (
    <div className={styles.bank}>
      <div className={styles.tabs} role="group" aria-label="Filter words by status">
        {statusTabs.map(tab => (
          <button key={tab.id} type="button" className={styles.tab} aria-pressed={filter === tab.id} onClick={() => setFilter(tab.id)}>
            {tab.label}
          </button>
        ))}
      </div>
      {wordBank.map(group => {
        const words = group.words.filter(word => filter === "all" || word.status === filter);
        return (
          <div key={group.place} className={styles.bankGroup}>
            <p className={styles.bankPlace}>
              {group.place} <span>{group.words.length} words</span>
            </p>
            <ul className={styles.bankWords}>
              {words.length ? (
                words.map(word => (
                  <li key={word.word} data-status={word.status}>
                    <b lang="es">{word.word}</b>
                    <span>{word.status}</span>
                  </li>
                ))
              ) : (
                <li className={styles.bankEmpty}>No {filter} words here yet</li>
              )}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

const chefs = [
  { rank: 1, name: "Marta", basil: 610 },
  { rank: 2, name: "You", basil: 420, you: true },
  { rank: 3, name: "Kai", basil: 385 },
  { rank: 4, name: "Noor", basil: 240 },
];
const sceneProgress = [
  { title: "Across the bay", done: 5, total: 5 },
  { title: "Study day", done: 4, total: 5 },
  { title: "Café morning", done: 2, total: 5 },
];

function ProgressBoard() {
  const [view, setView] = useState<"progress" | "chefs">("progress");

  return (
    <div className={styles.board}>
      <div className={styles.streak}>
        <div className={styles.week}>
          {week.map((day, index) => (
            <span key={index} className={styles.day} data-on={day.on}>
              {day.on ? <Image src="/pasta/farfalle.webp" alt="" width={40} height={31} /> : <span className={styles.missed} />}
              <span>{day.d}</span>
            </span>
          ))}
        </div>
        <p className={styles.stats}>
          <span className={styles.basilTotal}><Basil size={16} /> <b>420</b> Basil this week</span> <span className={styles.nowrap}><b>6</b> of 7 days this week</span>
        </p>
      </div>

      <div className={styles.boardPanel}>
        <div className={styles.tabs} role="group" aria-label="Choose a progress view">
          <button type="button" className={styles.tab} aria-pressed={view === "progress"} onClick={() => setView("progress")}>All-time progress</button>
          <button type="button" className={styles.tab} aria-pressed={view === "chefs"} onClick={() => setView("chefs")}>Chefs of the Day</button>
        </div>
        {view === "progress" ? (
          <>
            <div className={styles.metrics}>
              <span><b>86</b>Words learned</span>
              <span><b>34</b>Mastered</span>
              <span><b>9</b>Scenes</span>
            </div>
            <ul className={styles.sceneBars}>
              {sceneProgress.map(item => (
                <li key={item.title}>
                  <span>{item.title}</span>
                  <span className={styles.bar} aria-hidden="true"><span style={{ width: `${(item.done / item.total) * 100}%` }} /></span>
                  <span className={styles.barCount}>{item.done}/{item.total}</span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <ol className={styles.chefs}>
            {chefs.map(chef => (
              <li key={chef.rank} data-you={chef.you ?? false}>
                <span className={styles.rank}>{chef.rank}</span>
                <b>{chef.name}</b>
                <span className={styles.basilTotal}><Basil size={14} /> {chef.basil} Basil</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

export function Features() {
  const [pasta, setPasta] = useState(pastas[1]);
  const [kept, setKept] = useState<Record<string, boolean>>({ "la taza": true, "el portátil": true, "la planta": false });

  return (
    <section id="features" className={`section ${styles.section}`} aria-labelledby="features-title">
      <div className="container">
        <div className="section-head">
          <h2 id="features-title" className="section-title">Small sessions, serious habits</h2>
          <p className="section-lede">
            Everything in Linguini is built around five spare minutes and a photo: play solo or with a friend, start from a
            ready-made scene, and watch your words and Basil add up.
          </p>
        </div>

        <div className={styles.grid}>
          <Reveal className={`${styles.tile} ${styles.wide} ${styles.cream}`}>
            <div className={styles.text}>
              <h3>I Spy together</h3>
              <p>
                Open a private room and send a friend the invite code or link. You each add 2–4 photos, then take turns giving
                a clue and spotting the object. Every round you find together earns XP and Basil leaves for you both.
              </p>
              <div className={styles.invite}>
                <p className={styles.inviteHead}><Users size={18} /> Invite one friend</p>
                <p className={styles.inviteCode}>
                  <span>Room code</span>
                  <b>PASTA-4821</b>
                </p>
                <ul className={styles.members}>
                  <li><b>You</b><span>Ready</span></li>
                  <li><b>Sam</b><span>Ready</span></li>
                </ul>
              </div>
            </div>
            <SpyTogether />
          </Reveal>

          <Reveal className={styles.tile} delay={80}>
            <div className={styles.text}>
              <h3>No photo? No problem</h3>
              <p>Pick a ready-made scene, from a café to Paris at dusk. The words are already waiting, so you can start in seconds.</p>
            </div>
            <ReadyScenes />
          </Reveal>

          <Reveal className={styles.tile}>
            <div className={styles.text}>
              <h3>Articles come attached</h3>
              <p>Nouns arrive with their article and gender, so you learn <i lang="es">la mesa</i>, not just <i lang="es">mesa</i>.</p>
            </div>
            <ul className={styles.nouns}>
              <li><b lang="es">la mesa</b><span>feminine</span></li>
              <li><b lang="fr">le pont</b><span>masculine</span></li>
              <li><b lang="es">las sillas</b><span>feminine · plural</span></li>
            </ul>
          </Reveal>

          <Reveal className={`${styles.tile} ${styles.wide} ${styles.yellow}`} delay={80}>
            <div className={styles.text}>
              <h3>Hear it, then say it</h3>
              <p>
                Every word and clue has audio. A quick mic check gets you ready to answer out loud, so the words leave your head
                through your mouth, not just your thumbs. Rather type? That works too.
              </p>
            </div>
            <MicCheck />
          </Reveal>

          <Reveal className={`${styles.tile} ${styles.wide}`}>
            <div className={styles.text}>
              <h3>I-Spy, both ways</h3>
              <p>Playing solo? First Linguini gives you a clue about your photo. Then it’s your turn to describe something and let Linguini guess.</p>
            </div>
            <div className={styles.chat}>
              <div className={styles.spyPhoto}>
                <Image
                  src="/photos/desk-flatlay.jpg"
                  alt="A white desk with a notebook, pencil, phone, laptop and a potted plant"
                  fill
                  sizes="(max-width: 720px) 90vw, 380px"
                  className={styles.spyImg}
                />
                <span className={`${styles.spyMarker} ${styles.spyFound}`} style={{ left: "17%", top: "12%" }} aria-hidden="true">
                  <Check size={14} />
                </span>
                <span className={styles.spyMarker} style={{ left: "11%", top: "65%" }} aria-hidden="true">?</span>
              </div>
              <p className={styles.bubbleThem} lang="es">Veo, veo… algo que es verde y está en la mesa.</p>
              <p className={styles.bubbleYou} lang="es">¡La planta! Ahora yo: veo algo negro y pequeño.</p>
            </div>
          </Reveal>

          <Reveal className={styles.tile} delay={80}>
            <div className={styles.text}>
              <h3>You have the final say</h3>
              <p>AI suggests the words. You keep the useful ones, drop the rest, and tap the photo to add anything it missed.</p>
            </div>
            <ul className={styles.keep}>
              {Object.entries(kept).map(([word, on]) => (
                <li key={word}>
                  <button type="button" aria-pressed={on} onClick={() => setKept(current => ({ ...current, [word]: !on }))} className={styles.keepChip}>
                    <span lang="es">{word}</span>
                    <span className={styles.keepIcon} aria-hidden="true">{on ? <Check size={14} /> : <Close size={14} />}</span>
                  </button>
                </li>
              ))}
              <li>
                <span className={styles.addChip}><Plus size={16} /> Add a word</span>
              </li>
            </ul>
          </Reveal>

          <Reveal className={styles.tile}>
            <div className={styles.text}>
              <h3>Every word, filed by place</h3>
              <p>Your vocabulary bank keeps words with the scene you learned them in, marked new, learning or mastered.</p>
            </div>
            <WordBank />
          </Reveal>

          <Reveal className={`${styles.tile} ${styles.wide} ${styles.cream}`} delay={80}>
            <div className={styles.text}>
              <h3>Pick your pasta</h3>
              <p>Your avatar is a pasta shape. It shows up on your profile, your streak and the leaderboard.</p>
              <fieldset className={styles.pastaPicker}>
                <legend className="visually-hidden">Choose a pasta avatar</legend>
                {pastas.map(item => (
                  <label key={item.id} className={styles.pastaOption}>
                    <input
                      type="radio"
                      name="pasta-avatar"
                      value={item.id}
                      checked={pasta.id === item.id}
                      onChange={() => setPasta(item)}
                      className="visually-hidden"
                    />
                    <Image src={`/pasta/${item.id}.webp`} alt={item.name} width={item.w} height={item.h} />
                  </label>
                ))}
              </fieldset>
            </div>
            <div className={styles.avatar} aria-live="polite">
              <div className={styles.avatarDisc}>
                <Image key={pasta.id} src={`/pasta/${pasta.id}.webp`} alt="" width={pasta.w} height={pasta.h} className={styles.avatarImg} />
              </div>
              <p className={styles.avatarName}>{pasta.name}</p>
              <p className={styles.avatarLine}>{pasta.line}</p>
            </div>
          </Reveal>

          <Reveal className={`${styles.tile} ${styles.full} ${styles.sage}`}>
            <div className={styles.text}>
              <h3>Watch it add up</h3>
              <p>
                Earn Basil for every task, I-Spy round and journal entry. Your progress page tracks your streak, the words you’ve
                mastered, each scene you’ve played and where you stand among this week’s Chefs of the Day.
              </p>
            </div>
            <ProgressBoard />
          </Reveal>
        </div>
      </div>
    </section>
  );
}

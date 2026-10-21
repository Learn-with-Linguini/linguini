import Image from "./Image";
import { useEffect, useRef, useState } from "react";
import { speak } from "../lib/speech";
import { Check, Close, Mic, Plus, Speaker } from "./icons";
import { Reveal } from "./Reveal";
import styles from "./Features.module.css";

const pastas = [
  { id: "farfalle", name: "Farfalle", line: "Bow-tie ready. Here for the streaks.", w: 360, h: 281 },
  { id: "fusilli", name: "Fusilli", line: "Twisty, tenacious, never skips a day.", w: 276, h: 360 },
  { id: "penne", name: "Penne", line: "Straight to the point. Loves grammar.", w: 360, h: 341 },
  { id: "macaroni", name: "Macaroni", line: "Small, cheerful, collects every word.", w: 360, h: 333 },
];

function AppShot({ src, alt, width, height, className = "" }: { src: string; alt: string; width: number; height: number; className?: string }) {
  return (
    <figure className={`${styles.shot} ${className}`}>
      <Image src={src} alt={alt} width={width} height={height} sizes="(max-width: 720px) 90vw, 360px" />
    </figure>
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
            </div>
            <AppShot
              src="/app-shots/room-found.webp"
              alt="Linguini private room: a shared café photo with two numbered markers, the friend’s clue “Tiene una superficie plana.” and the message “You found it together!”"
              width={686}
              height={1112}
              className={styles.shotPad}
            />
          </Reveal>

          <Reveal className={styles.tile} delay={80}>
            <div className={styles.text}>
              <h3>No photo? No problem</h3>
              <p>Pick a ready-made scene, from a café to Paris at dusk. The words are already waiting, so you can start in seconds.</p>
            </div>
            <AppShot
              src="/app-shots/scenes.webp"
              alt="Linguini Practice page: ready-made scenes A walk downtown, At the café, At the market and My bedroom"
              width={686}
              height={576}
            />
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
              <p>Your vocabulary bank keeps every word with the scene you learned it in, with audio, and filters by new, learning or mastered.</p>
            </div>
            <div className={styles.shotStack}>
              <AppShot src="/app-shots/vocabulary-filters.webp" alt="Vocabulary filters: All, New, Learning, Mastered" width={686} height={98} />
              <AppShot
                src="/app-shots/vocabulary.webp"
                alt="Linguini vocabulary bank: the At the market scene with 7 words, including el queso, la bolsa and el tomate"
                width={686}
                height={798}
              />
            </div>
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
                Earn Basil for every task, I-Spy round and journal entry. Your progress page counts the words you’ve learned and mastered and the scenes you’ve played, and the weekly Chefs of the Day board shows where you stand.
              </p>
              <AppShot
                src="/app-shots/progress.webp"
                alt="Linguini progress page: 28 words learned, 10 mastered, 4 scenes"
                width={716}
                height={266}
                className={styles.statsShot}
              />
            </div>
            <AppShot
              src="/app-shots/leaderboard.webp"
              alt="Chefs of the Day weekly Basil leaderboard, with Sofia in third place on 405 Basil"
              width={686}
              height={1284}
              className={styles.boardShot}
            />
          </Reveal>
        </div>
      </div>
    </section>
  );
}

"use client";

import Image from "next/image";
import { useState } from "react";
import { speak } from "@/lib/speech";
import { Check, Close, Mic, Plus, Speaker } from "./icons";
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

export function Features() {
  const [pasta, setPasta] = useState(pastas[1]);
  const [kept, setKept] = useState<Record<string, boolean>>({ "la taza": true, "el portátil": true, "la planta": false });

  return (
    <section id="features" className={`section ${styles.section}`} aria-labelledby="features-title">
      <div className="container">
        <div className="section-head">
          <h2 id="features-title" className="section-title">Small sessions, serious habits</h2>
          <p className="section-lede">
            Everything in Linguini is built around five spare minutes and a photo, and around making you want to come back tomorrow.
          </p>
        </div>

        <div className={styles.grid}>
          <Reveal className={`${styles.tile} ${styles.wide} ${styles.cream}`}>
            <div className={styles.text}>
              <h3>Hear it, then say it</h3>
              <p>Every word and clue has audio. Answer out loud and Linguini listens, so the words leave your head through your mouth, not just your thumbs.</p>
            </div>
            <div className={styles.voice}>
              <button type="button" className={styles.voiceSpeak} onClick={() => speak("el puente rojo", "es")} aria-label="Hear “el puente rojo”">
                <Speaker size={22} />
              </button>
              <div className={styles.voiceLine}>
                <p className={styles.voicePhrase} lang="es">el puente rojo</p>
                <p className={styles.voiceIpa}>/el ˈpwente ˈroxo/ · the red bridge</p>
              </div>
              <div className={styles.voiceMic}>
                <span className={styles.micIcon}><Mic size={20} /></span>
                <span className={styles.wave} aria-hidden="true">
                  {Array.from({ length: 14 }, (_, i) => (
                    <span key={i} style={{ "--i": i, "--s": [0.35, 0.6, 0.9, 0.55, 1, 0.7, 0.4, 0.8, 0.95, 0.5, 0.65, 0.3, 0.75, 0.45][i] } as React.CSSProperties} />
                  ))}
                </span>
                <span className={styles.heard}><Check size={16} /> Sounds right</span>
              </div>
            </div>
          </Reveal>

          <Reveal className={styles.tile} delay={80}>
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

          <Reveal className={styles.tile}>
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

          <Reveal className={`${styles.tile} ${styles.wide} ${styles.yellow}`} delay={80}>
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

          <Reveal className={`${styles.tile} ${styles.wide}`}>
            <div className={styles.text}>
              <h3>I-Spy, both ways</h3>
              <p>First Linguini gives you a clue about your photo. Then it’s your turn to describe something and let Linguini guess.</p>
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

          <Reveal className={`${styles.tile} ${styles.sage} ${styles.lone}`} delay={80}>
            <div className={styles.text}>
              <h3>A streak worth keeping</h3>
              <p>Earn XP for every task, I-Spy win and journal entry. Each day you practise, a farfalle lands on your week.</p>
            </div>
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
                <b>420</b> XP this week · <b>86</b> words · <b>19</b> pages
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

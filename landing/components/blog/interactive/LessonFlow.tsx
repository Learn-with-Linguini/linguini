"use client";

import Image from "next/image";
import { useEffect, useState, useSyncExternalStore } from "react";
import { scenes } from "@/data/scenes";
import type { Lang } from "@/data/types";
import s from "./flow.module.css";

export type StageId = "snap" | "check" | "find" | "choose" | "build" | "ispy" | "journal";

const copy: Record<StageId, { label: string; title: string; text: string }> = {
  snap: { label: "Photo", title: "Snap a moment", text: "Start from a photo of your day, or pick one of our curated scenes." },
  check: { label: "Check", title: "A quick safety check", text: "The photo is screened before it can become a lesson." },
  find: { label: "Words", title: "Find the words", text: "Useful words are pinned to the things they name." },
  choose: { label: "Choose", title: "Keep the ones you want", text: "You decide which words to learn. Nothing is saved until you confirm." },
  build: { label: "Practise", title: "Build a sentence", text: "Word cards, fill-in-the-blank and a sentence builder use the words you chose." },
  ispy: { label: "I-Spy", title: "Play I-Spy", text: "Solve a clue about the scene, then describe an object for the app to guess." },
  journal: { label: "Journal", title: "Keep the day", text: "The lesson ends as a journal page you can come back to tomorrow." },
};

const STAGE_MS = 3200;
const REDUCED = "(prefers-reduced-motion: reduce)";

function subscribeReduced(onChange: () => void) {
  const query = window.matchMedia(REDUCED);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** Auto-playing walkthrough of one lesson on a real demo scene. */
export function LessonFlow({ sceneId, lang = "es", stages, costs }: {
  sceneId: string;
  lang?: Lang;
  stages: StageId[];
  /** Optional per-stage cost labels, e.g. { find: "$0.0139" }. */
  costs?: Partial<Record<StageId, string>>;
}) {
  const scene = scenes.find(item => item.id === sceneId) ?? scenes[0];
  const [index, setIndex] = useState(0);
  // null follows the reduced-motion setting until the reader presses play or pause.
  const [choice, setChoice] = useState<boolean | null>(null);
  const [hovered, setHovered] = useState(false);
  const reduced = useSyncExternalStore(subscribeReduced, () => window.matchMedia(REDUCED).matches, () => false);
  const playing = choice ?? !reduced;
  const stage = stages[index];
  const at = (id: StageId) => stages.indexOf(id) <= index && stages.includes(id);
  const running = playing && !hovered;

  useEffect(() => {
    if (!running) return;
    const next = (index + 1) % stages.length;
    const timer = window.setTimeout(() => setIndex(next), STAGE_MS);
    return () => window.clearTimeout(timer);
  }, [running, index, stages.length]);

  const words = scene.words.slice(0, 4);
  const answer = scene.ispy[lang].answer;
  const skipped = words[words.length - 1]?.id;
  const tokens = scene.build[lang].tokens;
  const journal = scene.journal[lang];
  const showWords = at("find") || (!stages.includes("find") && index > 0);

  return (
    <figure
      className={s.flow}
      data-stage={stage}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
    >
      <div className={s.stage} style={{ aspectRatio: `${scene.width} / ${scene.height}` }}>
        <Image src={scene.photo} alt={scene.alt} fill sizes="(min-width: 900px) 720px, 100vw" className={s.photo} data-snap={stage === "snap" || undefined} />
        <span className={s.flash} data-on={stage === "snap" || undefined} aria-hidden="true" />
        <span className={s.corners} data-on={stage === "snap" || undefined} aria-hidden="true" />

        <span className={s.badge} data-on={stage === "check" || undefined}>✓ Photo checked</span>

        {words.map((word, i) => (
          <span
            key={word.id}
            className={s.chip}
            data-on={showWords || undefined}
            data-picked={at("choose") && word.id !== skipped ? true : undefined}
            data-skipped={at("choose") && word.id === skipped ? true : undefined}
            data-answer={stage === "ispy" && word[lang].word === answer ? true : undefined}
            style={{ left: `${word.x}%`, top: `${word.y}%`, transitionDelay: showWords ? `${i * 120}ms` : "0ms" }}
          >
            {word[lang].word}
          </span>
        ))}

        <div className={s.sheet} data-on={stage === "build" || undefined} aria-hidden={stage !== "build"}>
          <span className={s.sheetLabel}>{scene.build[lang].en}</span>
          <span className={s.tiles}>
            {tokens.map((token, i) => (
              <span key={`${token}-${i}`} className={s.tile} style={{ transitionDelay: stage === "build" ? `${200 + i * 140}ms` : "0ms" }}>
                {token}
              </span>
            ))}
          </span>
        </div>

        <div className={s.bubble} data-on={stage === "ispy" || undefined} aria-hidden={stage !== "ispy"}>
          <b>{scene.ispy[lang].clue}</b>
          <small>{scene.ispy[lang].clueEn}</small>
        </div>

        <div className={s.journal} data-on={stage === "journal" || undefined} aria-hidden={stage !== "journal"}>
          <small>Today</small>
          <b>{journal.title}</b>
          <p>{journal.body}</p>
        </div>
      </div>

      <figcaption className={s.caption} aria-live="polite">
        <span className={s.captionText}>
          <b>{copy[stage].title}</b>
          <span>{copy[stage].text}</span>
        </span>
        {costs?.[stage] ? <span className={s.cost}>{costs[stage]}</span> : null}
      </figcaption>

      <div className={s.rail}>
        <button
          type="button"
          className={s.play}
          onClick={() => setChoice(!playing)}
          aria-label={playing ? "Pause walkthrough" : "Play walkthrough"}
        >
          {playing ? (
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M7 5h3v14H7zM14 5h3v14h-3z" fill="currentColor" /></svg>
          ) : (
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor" /></svg>
          )}
        </button>
        <ol className={s.steps}>
          {stages.map((id, i) => (
            <li key={id}>
              <button
                type="button"
                className={s.step}
                aria-current={i === index ? "step" : undefined}
                data-done={i < index || undefined}
                onClick={() => setIndex(i)}
              >
                <span className={s.stepBar}>
                  <span
                    key={`${index}-${i}`}
                    className={s.stepFill}
                    style={{
                      animationDuration: `${STAGE_MS}ms`,
                      animationPlayState: running && i === index ? "running" : "paused",
                    }}
                  />
                </span>
                {copy[id].label}
              </button>
            </li>
          ))}
        </ol>
      </div>
    </figure>
  );
}

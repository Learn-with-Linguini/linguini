"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { getScene } from "@/data/scenes";
import { steps } from "@/data/steps";
import type { Scene } from "@/data/types";
import { JournalCard } from "./product/JournalCard";
import { PhotoMarkers } from "./product/PhotoMarkers";
import { WordCard } from "./product/WordCard";
import { Camera, Check } from "./icons";
import styles from "./HowItWorks.module.css";

function StepVisual({ index, scene, desk }: { index: number; scene: Scene; desk: Scene }) {
  if (index === 0) {
    return (
      <div className={styles.snap}>
        <div className={styles.snapBack}>
          <Image src="/photos/summer-meadow.jpg" alt="" fill sizes="280px" className={styles.cover} />
        </div>
        <div className={styles.snapFront}>
          <Image src={scene.photo} alt={scene.alt} fill sizes="420px" className={styles.cover} />
          <span className={styles.shutter} aria-hidden="true">
            <Camera size={26} />
          </span>
        </div>
      </div>
    );
  }
  if (index === 1) {
    return <PhotoMarkers scene={scene} labels className={styles.markers} sizes="(max-width: 960px) 90vw, 520px" />;
  }
  if (index === 2) {
    const clue = desk.ispy.es;
    return (
      <div className={styles.play}>
        <WordCard word={desk.words[0]} lang="es" className={styles.playCard} />
        <div className={styles.playSpy}>
          <p className={styles.playLabel}>Linguini says</p>
          <p className={styles.playClue} lang="es">{clue.clue}</p>
          <div className={styles.playChoices}>
            {clue.choices.slice(0, 4).map(choice => (
              <span key={choice} className={styles.playChoice} data-correct={choice === clue.answer} lang="es">
                {choice === clue.answer ? <Check size={16} /> : null}
                {choice}
              </span>
            ))}
          </div>
        </div>
      </div>
    );
  }
  return (
    <JournalCard
      photos={[
        { src: scene.photo, alt: scene.alt },
        { src: "/photos/hillside-street.jpg", alt: "Flower-lined hillside street with a red car" },
        { src: "/photos/sunlit-promenade.jpg", alt: "Sunlit city square with street lamps" },
        { src: "/photos/lake-shore.jpg", alt: "Lake shore" },
      ]}
      title={scene.journal.es.title}
      body={scene.journal.es.body}
      date="Saturday, 19 Sep"
      lang="es"
      highlight={scene.words.map(word => word.es.word)}
      className={styles.journal}
      headingLevel="p"
    />
  );
}

export function HowItWorks() {
  const [active, setActive] = useState(0);
  const stepRefs = useRef<(HTMLLIElement | null)[]>([]);
  const scene = getScene("golden-gate-bridge")!;
  const desk = getScene("desk-flatlay")!;

  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(Number((entry.target as HTMLElement).dataset.index));
        }
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    stepRefs.current.forEach(node => node && observer.observe(node));
    return () => observer.disconnect();
  }, []);

  return (
    <section id="how" className={styles.section} aria-labelledby="how-title">
      <div className="container">
        <div className={`section-head ${styles.head}`}>
          <h2 id="how-title" className="section-title">From snapshot to sentence</h2>
          <p className={`section-lede ${styles.lede}`}>
            Every Linguini session follows the same small loop. It fits in a coffee break and leaves you with a page to keep.
          </p>
        </div>

        <div className={styles.layout}>
          <ol className={styles.steps}>
            {steps.map((step, index) => (
              <li
                key={step.title}
                ref={node => {
                  stepRefs.current[index] = node;
                }}
                data-index={index}
                className={styles.step}
                data-active={active === index}
              >
                <span className={styles.num} aria-hidden="true">{index + 1}</span>
                <div className={styles.stepText}>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
                <div className={styles.inlineVisual}>
                  <StepVisual index={index} scene={scene} desk={desk} />
                </div>
              </li>
            ))}
          </ol>

          <div className={styles.pin} aria-hidden="true" inert>
            <div className={styles.pinInner}>
              {steps.map((step, index) => (
                <div key={step.title} className={styles.frame} data-active={active === index}>
                  <StepVisual index={index} scene={scene} desk={desk} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

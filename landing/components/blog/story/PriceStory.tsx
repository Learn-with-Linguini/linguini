"use client";

import { Scrolly } from "./Scrolly";
import s from "./story.module.css";

const MAX = 180;
const pct = (v: number) => `${(v / MAX) * 100}%`;

type Mark = { name: string; short?: string; lo: number; hi: number; pos: "above" | "below"; align?: "start" | "end" };

const competitors: Mark[] = [
  { name: "CapWords", lo: 19.99, hi: 29.99, pos: "above" },
  { name: "Duolingo, Speak", lo: 83.99, hi: 95.99, pos: "above" },
  { name: "Babbel", lo: 107.64, hi: 107.64, pos: "below" },
  { name: "Duolingo Max", short: "Max", lo: 168, hi: 168, pos: "above", align: "end" },
];

// Which rows each step shows: active, dimmed or not yet drawn.
const layers = ["cost", "competition", "value"] as const;
function stateFor(layer: (typeof layers)[number], step: number) {
  const index = layers.indexOf(layer);
  if (step === 3) return "active";
  if (index > step) return "hidden";
  return index === step ? "active" : "dim";
}

function Ruler({ step }: { step: number }) {
  return (
    <div className={s.rulerBox}>
      <div className={s.rulerHead}>
        <span className={s.chartTitle}>What a year of Linguini should cost</span>
        <span className={s.chartSub}>Annual prices, US dollars</span>
      </div>
      <div className={s.ruler}>
        {[0, 50, 100, 150].map(v => <span key={v} className={s.grid} style={{ left: `calc(var(--lw) + (100% - var(--lw)) * ${v / MAX})` }} />)}

        <div className={s.row} data-state={stateFor("cost", step)}>
          <span className={s.rowLabel}>Cost</span>
          <span className={s.rowTrack} />
          <span className={s.range} data-soft style={{ left: 0, width: pct(14.5) }} />
          <span className={s.markLabel} data-pos="below" data-align="start" style={{ left: 0 }}>≈ $15 AI + fees</span>
        </div>

        <div className={s.row} data-state={stateFor("competition", step)}>
          <span className={s.rowLabel}>Competition</span>
          <span className={s.rowTrack} />
          {competitors.map((mark, i) => (
            <span key={mark.name}>
              {mark.hi > mark.lo ? (
                <span className={s.range} style={{ left: pct(mark.lo), width: pct(mark.hi - mark.lo), transitionDelay: `${i * 120}ms` }} />
              ) : (
                <span className={s.dot} style={{ left: pct(mark.lo), transitionDelay: `${i * 120}ms` }} />
              )}
              <span className={s.markLabel} data-pos={mark.pos} data-align={mark.align} style={{ left: pct((mark.lo + mark.hi) / 2) }}>
                {mark.short ? (
                  <><span className={s.long}>{mark.name}</span><span className={s.short} aria-hidden="true">{mark.short}</span></>
                ) : mark.name}
              </span>
            </span>
          ))}
        </div>

        <div className={s.row} data-state={stateFor("value", step)}>
          <span className={s.rowLabel}>Value</span>
          <span className={s.rowTrack} />
          <span className={s.range} data-soft style={{ left: pct(20), width: pct(60) }} />
          <span className={s.markLabel} data-pos="below" style={{ left: pct(50) }}>1–2 hours with a tutor</span>
        </div>

        <span className={s.priceLine} data-off={step < 3 || undefined} style={{ left: `calc(var(--lw) + (100% - var(--lw)) * ${49.99 / MAX})` }}>
          <span className={s.priceTag}>Plus $49.99</span>
        </span>
        <span className={s.priceLine} data-kind="founding" data-off={step < 3 || undefined} style={{ left: `calc(var(--lw) + (100% - var(--lw)) * ${34.99 / MAX})`, transitionDelay: "250ms" }}>
          <span className={s.priceTag}>Founding $34.99</span>
        </span>
      </div>
      <div className={s.axis}>
        {[0, 50, 100, 150].map(v => <span key={v} style={{ left: pct(v) }}>${v}</span>)}
      </div>
    </div>
  );
}

export function PriceStory() {
  return (
    <Scrolly
      label="How we set the Plus price"
      graphic={Ruler}
      steps={[
        <><strong>Cost sets the floor.</strong> A typical Plus learner costs us about $15 a year in AI, storage and card fees. Anything above that can also carry some free learners.</>,
        <><strong>Competitors set the range.</strong> Photo-flashcard apps charge $20–30 a year. Duolingo, Speak and Babbel charge $84–168. We do more than a flashcard app and less than a full course.</>,
        <><strong>Value sets the ceiling.</strong> An online tutor costs $15–60 an hour. A year of daily practice should cost less than one or two lessons.</>,
        <><strong>So Plus is $49.99 a year.</strong> That is close to the $44.99 education-app median and below every course app. Our first 300 members lock in $34.99.</>,
      ]}
    />
  );
}

"use client";

import { type ComponentType, type ReactNode, useEffect, useRef, useState } from "react";
import s from "./story.module.css";

/**
 * Scrollytelling block: the graphic stays pinned while short text steps scroll past,
 * and each step sets the graphic's state. Printing shows the final step.
 */
export function Scrolly({ steps, graphic: Graphic, label }: {
  steps: ReactNode[];
  graphic: ComponentType<{ step: number }>;
  label: string;
}) {
  const [step, setStep] = useState(0);
  const refs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) setStep(Number((entry.target as HTMLElement).dataset.index));
        }
      },
      // Wide screens: steps sit beside the chart. Narrow screens: switch once the card is below the pinned chart.
      { rootMargin: window.matchMedia("(min-width: 980px)").matches ? "-49% 0px -50% 0px" : "-72% 0px -20% 0px" },
    );
    refs.current.forEach(node => node && observer.observe(node));
    const toEnd = () => setStep(steps.length - 1);
    window.addEventListener("beforeprint", toEnd);
    return () => {
      observer.disconnect();
      window.removeEventListener("beforeprint", toEnd);
    };
  }, [steps.length]);

  return (
    <section className={s.scrolly} aria-label={label}>
      <div className={s.graphic}>
        <div className={s.graphicInner}><Graphic step={step} /></div>
        <ol className={s.dots} aria-hidden="true">
          {steps.map((_, i) => <li key={i} data-on={i === step || undefined} />)}
        </ol>
      </div>
      <div className={s.steps}>
        {steps.map((content, i) => (
          <div
            key={i}
            ref={node => { refs.current[i] = node; }}
            data-index={i}
            data-active={i === step || undefined}
            data-past={i < step || undefined}
            className={s.step}
          >
            <div className={s.card}>{content}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

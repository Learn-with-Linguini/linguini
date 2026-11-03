import { useEffect, useState, type CSSProperties } from "react";
import { PASTA_SHOWER_EVENT, type PastaShowerVariant } from "../lib/answerCelebration";
import "./PastaShower.css";

const SHAPES = ["farfalle", "fusilli", "macaroni", "penne"] as const;
const SAUCE = ["var(--tomato)", "var(--pasta)", "var(--teal)"] as const;

/** A correct answer gets a quick sprinkle; a perfect finish gets a long, dense, sparkling shower. */
const SHOWERS: Record<PastaShowerVariant, { pieces: number; sparkles: number; size: [number, number]; duration: [number, number]; spread: number }> = {
  answer: { pieces: 12, sparkles: 0, size: [26, 40], duration: [1100, 1600], spread: 250 },
  partial: { pieces: 20, sparkles: 0, size: [32, 48], duration: [2200, 3000], spread: 900 },
  perfect: { pieces: 46, sparkles: 28, size: [34, 56], duration: [2400, 3400], spread: 1600 },
};

interface Drop { id: number; shape?: string; color?: string; style: CSSProperties }

const between = ([low, high]: [number, number]) => low + Math.random() * (high - low);

function drops(variant: PastaShowerVariant): Drop[] {
  const shower = SHOWERS[variant];
  const fall = (size: number) => ({
    "--x": `${Math.random() * 100}%`,
    "--size": `${size}px`,
    "--delay": `${Math.round(Math.random() * shower.spread)}ms`,
    "--duration": `${Math.round(between(shower.duration))}ms`,
    "--drift": `${Math.round((Math.random() - 0.5) * 160)}px`,
    "--spin": `${Math.round((Math.random() - 0.5) * 900)}deg`,
  }) as CSSProperties;
  return [
    ...Array.from({ length: shower.pieces }, (_, id) => ({ id, shape: SHAPES[id % SHAPES.length], style: fall(between(shower.size)) })),
    ...Array.from({ length: shower.sparkles }, (_, id) => ({ id: shower.pieces + id, color: SAUCE[id % SAUCE.length], style: fall(between([8, 14])) })),
  ];
}

function longest(variant: PastaShowerVariant) {
  const shower = SHOWERS[variant];
  return shower.spread + shower.duration[1] + 100;
}

export function PastaShower({ variant }: { variant: PastaShowerVariant }) {
  const [pieces] = useState(() => drops(variant));
  return <div className={`pasta-shower pasta-shower--${variant}`} aria-hidden="true">
    {pieces.map(piece => piece.shape
      ? <img key={piece.id} className="pasta-shower__piece" src={`/pasta/${piece.shape}.webp`} alt="" style={piece.style} />
      : <span key={piece.id} className="pasta-shower__piece pasta-shower__sauce" style={{ ...piece.style, background: piece.color }} />)}
  </div>;
}

const reducedMotion = () => typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Listens for `showPastaShower` so any screen can celebrate without owning the overlay. */
export function PastaShowerHost() {
  const [showers, setShowers] = useState<{ id: number; variant: PastaShowerVariant }[]>([]);
  useEffect(() => {
    // Warm the cache so the first shower does not fall as empty boxes.
    for (const shape of SHAPES) new Image().src = `/pasta/${shape}.webp`;
    let next = 0;
    const timers = new Set<number>();
    const show = (event: Event) => {
      if (reducedMotion()) return;
      const variant = (event as CustomEvent<PastaShowerVariant>).detail;
      const id = ++next;
      // Quick answers replace an older shower instead of piling up on the page.
      setShowers(value => [...value.slice(-1), { id, variant }]);
      const timer = window.setTimeout(() => {
        timers.delete(timer);
        setShowers(value => value.filter(item => item.id !== id));
      }, longest(variant));
      timers.add(timer);
    };
    window.addEventListener(PASTA_SHOWER_EVENT, show);
    return () => {
      window.removeEventListener(PASTA_SHOWER_EVENT, show);
      for (const timer of timers) window.clearTimeout(timer);
    };
  }, []);
  return <>{showers.map(shower => <PastaShower key={shower.id} variant={shower.variant} />)}</>;
}

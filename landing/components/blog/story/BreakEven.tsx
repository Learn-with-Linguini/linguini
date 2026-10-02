"use client";

import { useId, useRef, useState } from "react";
import { breakEvenConversion, monthlyResult, type Pipeline, usd } from "../interactive/data";
import { useInView, useTween, useWidth } from "./hooks";
import s from "./story.module.css";

const USER_STOPS = [300, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000, 100_000];
const MAX_C = 0.08;
const H = 280, T = 20, B = 30, L = 56, R = 110;

const PRIMARY: Pipeline = "chosen";
const lines: { id: Pipeline; label: string; color: string; ink: string }[] = [
  { id: "budget", label: "Cheapest models", color: "#00968F", ink: "var(--teal-dark)" },
  { id: "chosen", label: "Chosen models", color: "#EF5B32", ink: "var(--tomato-ink)" },
];

function niceStep(span: number) {
  const raw = span / 4;
  const pow = 10 ** Math.floor(Math.log10(raw));
  return ([1, 2, 2.5, 5, 10].find(n => n * pow >= raw) ?? 10) * pow;
}

function signed(value: number) {
  if (Math.abs(value) < 0.5) return "$0";
  return `${value > 0 ? "+" : "−"}${usd(Math.abs(value))}`;
}

/** Monthly result as the share of paying learners grows, for the chosen models and the cheapest alternatives. */
export function BreakEven() {
  const [userIndex, setUserIndex] = useState(3);
  const [conversion, setConversion] = useState(0.045);
  const [hover, setHover] = useState<number | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  const inView = useInView(chartRef);
  const width = useWidth(chartRef);
  const ids = { users: useId(), conversion: useId() };

  const users = USER_STOPS[userIndex];
  const planShown = useTween(monthlyResult(users, conversion, "chosen").result);
  const budgetShown = useTween(monthlyResult(users, conversion, "budget").result);

  // Straight lines, so two ends per line are enough; tweening them animates the chart.
  const chosenStart = useTween(monthlyResult(users, 0, "chosen").result);
  const chosenEnd = useTween(monthlyResult(users, MAX_C, "chosen").result);
  const budgetStart = useTween(monthlyResult(users, 0, "budget").result);
  const budgetEnd = useTween(monthlyResult(users, MAX_C, "budget").result);
  const ends: Record<string, [number, number]> = {
    chosen: [chosenStart, chosenEnd],
    budget: [budgetStart, budgetEnd],
  };
  const all = [chosenStart, chosenEnd, budgetStart, budgetEnd, 0];
  const step = niceStep(Math.max(...all) - Math.min(...all) || 1);
  const yMin = Math.floor(Math.min(...all) / step) * step;
  const yMax = Math.ceil(Math.max(...all) / step) * step;
  const ticks: number[] = [];
  for (let v = yMin; v <= yMax + step / 2; v += step) ticks.push(v);

  const x = (c: number) => L + (c / MAX_C) * (width - L - R);
  const y = (v: number) => T + (1 - (v - yMin) / (yMax - yMin || 1)) * (H - T - B);
  const at = (id: Pipeline, c: number) => ends[id][0] + (ends[id][1] - ends[id][0]) * (c / MAX_C);

  function onMove(event: React.PointerEvent<SVGSVGElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * width;
    setHover(Math.min(MAX_C, Math.max(0, ((px - L) / (width - L - R)) * MAX_C)));
  }

  return (
    <figure className={s.breakEven}>
      <p className={s.verdict} aria-live="polite">
        With <b>{users.toLocaleString("en-US")}</b> learners and <b>{(conversion * 100).toFixed(1)}%</b> paying, Linguini makes{" "}
        <span className={s.bigResult} data-sign={planShown >= 0 ? "pos" : "neg"}>{signed(planShown)}</span> a month on the
        chosen models.
        <small>On the cheapest alternatives, once they pass our evaluation, it would be {signed(budgetShown)}.</small>
      </p>

      <div ref={chartRef} className={s.lineChart} data-inview={inView || undefined}>
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
          <title>{`Monthly result against the share of learners who pay, for ${users.toLocaleString("en-US")} learners`}</title>
          <rect x={L} y={y(0)} width={Math.max(0, width - L - R)} height={Math.max(0, y(yMin) - y(0))} fill="#fdf1ec" />
          {ticks.map(v => (
            <g key={v}>
              <line x1={L} x2={width - R} y1={y(v)} y2={y(v)} stroke={v === 0 ? "#a99d86" : "#efe8da"} />
              <text x={L - 8} y={y(v) + 4} textAnchor="end">{signed(v)}</text>
            </g>
          ))}
          {[0, 0.02, 0.04, 0.06, 0.08].map(c => (
            <text key={c} x={x(c)} y={H - 8} textAnchor="middle">{Math.round(c * 100)}%</text>
          ))}
          {lines.map(line => (
            <g key={line.id}>
              <path
                className={s.draw}
                pathLength={1}
                d={`M${x(0)},${y(at(line.id, 0))} L${x(MAX_C)},${y(at(line.id, MAX_C))}`}
                fill="none"
                stroke={line.color}
                strokeWidth={line.id === PRIMARY ? 3.5 : 2.5}
                strokeLinecap="round"
                style={{ transitionDelay: line.id === PRIMARY ? "0.4s" : "0s" }}
              />
              <text
                x={x(MAX_C) + 10}
                y={y(at(line.id, MAX_C)) + 4}
                className={s.strong}
                style={{ fill: line.ink }}
              >
                {line.label}
              </text>
            </g>
          ))}
          {lines.map(line => {
            const be = breakEvenConversion(users, line.id);
            return be <= MAX_C ? (
              <g key={line.id} className={s.mover} style={{ transform: `translate(${x(be)}px, ${y(0)}px)` }}>
                <circle r={5} fill="var(--paper)" stroke={line.color} strokeWidth={3} />
                <text y={18} textAnchor="middle" style={{ fontSize: 11 }}>{(be * 100).toFixed(1)}%</text>
              </g>
            ) : null;
          })}
          <line x1={x(conversion)} x2={x(conversion)} y1={T} y2={H - B} stroke="#263238" strokeDasharray="3 4" />
          <g className={s.mover} style={{ transform: `translate(${x(conversion)}px, ${y(at(PRIMARY, conversion))}px)` }}>
            <circle r={8} fill="#263238" stroke="var(--paper)" strokeWidth={3} />
          </g>
          {hover != null ? (
            <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="#263238" strokeOpacity={0.25} pointerEvents="none" />
          ) : null}
          <rect x={L} y={T} width={Math.max(0, width - L - R)} height={H - T - B} fill="transparent" />
        </svg>
        {hover != null ? (
          <div className={s.tip} style={{ left: x(hover), top: y(at(PRIMARY, hover)) }}>
            {(hover * 100).toFixed(1)}% pay · {signed(at(PRIMARY, hover))}
          </div>
        ) : null}
      </div>

      <div className={s.controls}>
        <label className={s.control} htmlFor={ids.users}>
          <span className={s.controlHead}>Learners a month <output htmlFor={ids.users}>{users.toLocaleString("en-US")}</output></span>
          <input
            id={ids.users}
            className={s.slider}
            type="range"
            min={0}
            max={USER_STOPS.length - 1}
            step={1}
            value={userIndex}
            style={{ "--fill": `${(userIndex / (USER_STOPS.length - 1)) * 100}%` } as React.CSSProperties}
            onChange={event => setUserIndex(Number(event.target.value))}
            aria-valuetext={`${users.toLocaleString("en-US")} learners a month`}
          />
        </label>
        <label className={s.control} htmlFor={ids.conversion}>
          <span className={s.controlHead}>Share who pay <output htmlFor={ids.conversion}>{(conversion * 100).toFixed(1)}%</output></span>
          <input
            id={ids.conversion}
            className={s.slider}
            type="range"
            min={0.005}
            max={MAX_C}
            step={0.001}
            value={conversion}
            style={{ "--fill": `${((conversion - 0.005) / (MAX_C - 0.005)) * 100}%` } as React.CSSProperties}
            onChange={event => setConversion(Number(event.target.value))}
            aria-valuetext={`${(conversion * 100).toFixed(1)} percent pay`}
          />
        </label>
      </div>
    </figure>
  );
}

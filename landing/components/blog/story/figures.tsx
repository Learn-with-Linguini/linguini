import type { CSSProperties, ReactNode } from "react";
import { competitors } from "@/data/competitors";
import { Check } from "../../icons";
import { InView } from "./InView";
import s from "./story.module.css";

const yes = <span className={s.yes}><Check size={16} /><span className="visually-hidden">Yes</span></span>;
const no = <span className={s.no}><span className="visually-hidden">No</span></span>;
const n = (value: string, unit?: string) => <span className={s.big}>{value}{unit ? <small> {unit}</small> : null}</span>;

type Plan = "free" | "plus" | "founding";
const plans: { id: Plan; name: string; price: string; per: string }[] = [
  { id: "free", name: "Free", price: "$0", per: "forever" },
  { id: "plus", name: "Plus", price: "$49.99", per: "a year · or $7.99/mo" },
  { id: "founding", name: "Founding", price: "$34.99", per: "a year · first 300" },
];

const rows: { label: string; cells: Record<Plan, ReactNode> }[] = [
  { label: "Photo lessons", cells: { free: n("1", "/day"), plus: n("10", "/day"), founding: n("10", "/day") } },
  { label: "Photos per journal page", cells: { free: n("1"), plus: n("10"), founding: n("10") } },
  { label: "Curated scenes", cells: { free: n("∞"), plus: n("∞"), founding: n("∞") } },
  { label: "Pronunciation feedback", cells: { free: no, plus: yes, founding: yes } },
  { label: "Review mode", cells: { free: no, plus: yes, founding: yes } },
  { label: "Competitive I-Spy beta", cells: { free: no, plus: no, founding: yes } },
  { label: "Vote on the roadmap", cells: { free: no, plus: no, founding: yes } },
];

/** Plans side by side: numbers where there is a limit, ticks where there is a feature. */
export function PlanMatrix() {
  return (
    <figure className={s.figure}>
      <div className={s.plansWrap}>
        <table className={s.plans}>
          <thead>
            <tr>
              <th scope="col" className={s.feature}><span className="visually-hidden">Feature</span></th>
              {plans.map(plan => (
                <th key={plan.id} scope="col" className={s.planHead} data-col={plan.id}>
                  <b>{plan.name}</b>
                  <strong>{plan.price}</strong>
                  <small>{plan.per}</small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.label}>
                <th scope="row" className={s.feature}>{row.label}</th>
                {plans.map(plan => (
                  <td key={plan.id} data-col={plan.id}>{row.cells[plan.id]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

const apps = competitors;

/** Annual price bars with the two things only Linguini combines. */
export function CompareApps() {
  const max = 110;
  return (
    <figure className={s.figure}>
      <InView as="ul" className={s.apps} aria-label="Annual price and features by app">
        <li className={s.appHead} aria-hidden="true">
          <span>App</span><span>Price a year</span><span>Own photos</span><span>Journal</span>
        </li>
        {apps.map((app, i) => (
          <li key={app.name} className={s.app} data-ours={app.ours || undefined}>
            <span className={s.appName}>
              <b>{app.name} <small>{app.plan}</small></b>
              <small>Free: {app.free}</small>
            </span>
            <span className={s.appPrice}>
              <span className={s.appBar}><i style={{ "--w": `${(app.price / max) * 100}%`, "--i": i } as CSSProperties} /></span>
              {app.label}
            </span>
            <span className={s.check}><span className="visually-hidden">Lessons from your photos:</span>{app.photos ? yes : no}</span>
            <span className={s.check}><span className="visually-hidden">Games and a journal:</span>{app.journal ? yes : no}</span>
          </li>
        ))}
      </InView>
      <figcaption>US list prices checked September 2026; they vary by country and with discounts. CapWords turns photos into flashcards, without games or a journal.</figcaption>
    </figure>
  );
}

const options = [
  { name: "Freemium with daily limits", why: "Free learners get one photo lesson a day, which caps what they cost. Everyone can try it first.", x: 76, y: 24, chosen: true, flip: true },
  { name: "Usage credits", why: "Matches our costs exactly, but counting credits breaks a daily habit.", x: 18, y: 16 },
  { name: "Flat subscription", why: "No way to try before paying.", x: 40, y: 62 },
  { name: "Lifetime deal", why: "Popular, but AI costs keep coming after the one payment.", x: 80, y: 82, flip: true },
  { name: "Ads", why: "Earns little at our size, and ads would sit next to personal photos.", x: 16, y: 82 },
];

/** Each pricing model placed by how it handles AI cost and how learners feel about it. */
export function ModelMap() {
  const chosen = options.find(option => option.chosen)!;
  return (
    <figure className={s.figure}>
      <InView className={s.map}>
        <span className={s.mapWin} aria-hidden="true"><span>Sweet spot</span></span>
        <span className={s.axisX} aria-hidden="true">Learners like it →</span>
        <span className={s.axisY} aria-hidden="true">Covers AI cost →</span>
        {options.map((option, i) => (
          <span
            key={option.name}
            className={s.point}
            data-chosen={option.chosen || undefined}
            data-flip={option.flip || undefined}
            style={{ "--x": option.x, "--y": option.y, "--i": i } as CSSProperties}
            tabIndex={option.chosen ? undefined : 0}
          >
            <b>{option.name}</b>
            {option.chosen ? null : <span className={s.why} role="tooltip">{option.why}</span>}
          </span>
        ))}
        <p className={s.callout} style={{ "--x": chosen.x, "--y": chosen.y } as CSSProperties}>
          {chosen.why}
        </p>
      </InView>
      <ul className={s.reasons}>
        {options.map(option => (
          <li key={option.name}><b>{option.name}{option.chosen ? " (chosen)" : ""}.</b> {option.why}</li>
        ))}
      </ul>
      <figcaption className="no-print">Hover or tap a model to see why we passed on it.</figcaption>
    </figure>
  );
}

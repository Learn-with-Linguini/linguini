"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
import { ArrowRight } from "@/components/icons";
import { useInView } from "../story/hooks";
import { Img } from "./Img";
import { type Brand, Logo } from "./Logos";
import { InstagramPost, LinkedInPost, RedditPost, StoryPhone, TelegramChat, XThread } from "./Social";
import p from "./plan.module.css";

function useInViewRef<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  return [ref, useInView(ref)] as const;
}

/* ---------- The whole plan on one line ---------- */

const steps = [
  { href: "#soft-launch", when: "Now to 16 Oct", title: "Beta testers" },
  { href: "#who", when: "The week before", title: "Tell people" },
  { href: "#day", when: "Sat 17 Oct, 3:01pm", title: "Launch", live: true },
  { href: "#after", when: "The 2 weeks after", title: "Bring people back" },
  { href: "#next", when: "Already planned", title: "Launch again" },
];

export function PlanStrip() {
  const [ref, inView] = useInViewRef<HTMLOListElement>();
  return (
    <nav aria-label="The plan">
      <ol ref={ref} className={p.strip} data-inview={inView || undefined}>
        {steps.map((step, i) => (
          <li key={step.title} style={{ ["--i" as string]: i }} data-live={step.live || undefined}>
            <a href={step.href}>
              <small>{step.when}</small>
              <b>{step.title}</b>
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

/* ---------- Soft launch, then open doors ---------- */

export function Phases() {
  return (
    <figure className={p.fig}>
      <div className={p.phases}>
        <section className={p.phase} data-tone="soft">
          <small>Now to 16 October</small>
          <h4>Soft launch</h4>
          <p><b>10 to 20 beta testers</b>, by invitation. People learning Spanish or French who will tell us what breaks.</p>
        </section>
        <span className={p.phaseArrow} aria-hidden="true"><ArrowRight size={22} /></span>
        <section className={p.phase} data-tone="open">
          <small>From 17 October, 3:01pm</small>
          <h4>Open to everyone</h4>
          <p><b>No waitlist.</b> The browser demo needs no account, and anyone can sign up for the app’s free daily lesson.</p>
        </section>
      </div>
      <figcaption>An invite list for three weeks to find the bugs, then open doors for launch day.</figcaption>
    </figure>
  );
}

/* ---------- What Product Hunt asks for ---------- */

const asks = [
  { need: "A product site", ours: "linguini-landing.vercel.app, with the demo on the first screen" },
  { need: "A logo", ours: "Our pasta mascot, 240 × 240" },
  { need: "A pitch", ours: "A one-line tagline and a short description" },
  { need: "A demo video", ours: "The 50-second explainer, below" },
  { need: "A first comment", ours: "Why we built it, and two questions for readers" },
];

export function ProductHuntAsks() {
  return (
    <ul className={p.asks}>
      {asks.map(item => (
        <li key={item.need}>
          <b>{item.need}</b>
          <span>{item.ours}</span>
        </li>
      ))}
    </ul>
  );
}

/* ---------- Every draft, side by side, drifting on its own ---------- */

type Draft = { brand: Brand; label: string; note: string; body: ReactNode };

const slides: { wide?: boolean; drafts: Draft[] }[] = [
  { wide: true, drafts: [{ brand: "x", label: "X thread", note: "The first post carries the link card. The replies carry the why.", body: <XThread /> }] },
  { drafts: [{ brand: "instagram", label: "Instagram carousel", note: "4:5 takes the most room in the feed. Double-click the photo.", body: <InstagramPost /> }] },
  { drafts: [{ brand: "instagram", label: "Instagram story", note: "A countdown at T−3, then “we’re live” with a link sticker.", body: <div className={p.storyWrap}><StoryPhone /></div> }] },
  {
    wide: true,
    drafts: [
      { brand: "linkedin", label: "LinkedIn", note: "From one of us, not the brand. People reply to people.", body: <LinkedInPost /> },
      { brand: "reddit", label: "Reddit", note: "A question in the weekly thread, not an announcement.", body: <RedditPost /> },
    ],
  },
  { drafts: [{ brand: "telegram", label: "Telegram", note: "Lowercase, because that’s how we text each other.", body: <TelegramChat /> }] },
];

const DRIFT_PX_PER_S = 28;
const RESUME_AFTER_MS = 2500;

export function DraftRail() {
  const railRef = useRef<HTMLDivElement>(null);
  const [edge, setEdge] = useState({ start: true, end: false });

  useEffect(() => {
    const rail = railRef.current;
    if (!rail) return;
    const update = () => setEdge({
      start: rail.scrollLeft < 8,
      end: rail.scrollLeft + rail.clientWidth > rail.scrollWidth - 8,
    });
    update();
    rail.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      rail.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  // Drift back and forth while on screen, hover included. Only a swipe, wheel or drag pauses it briefly.
  useEffect(() => {
    const rail = railRef.current;
    if (!rail || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let visible = false;
    let pausedUntil = 0;
    let dir = 1;
    let pos = rail.scrollLeft;
    let last = 0;
    let frame = 0;

    const tick = (now: number) => {
      const dt = last ? Math.min(64, now - last) : 16;
      last = now;
      if (visible && now > pausedUntil) {
        const max = rail.scrollWidth - rail.clientWidth;
        if (Math.abs(rail.scrollLeft - pos) > 2) pos = rail.scrollLeft;
        pos += dir * DRIFT_PX_PER_S * (dt / 1000);
        if (pos >= max) { pos = max; dir = -1; }
        if (pos <= 0) { pos = 0; dir = 1; }
        rail.scrollLeft = pos;
      }
      frame = requestAnimationFrame(tick);
    };

    const hold = () => { pausedUntil = performance.now() + RESUME_AFTER_MS; };
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }, { threshold: 0.3 });
    observer.observe(rail);
    rail.addEventListener("wheel", hold, { passive: true });
    rail.addEventListener("touchstart", hold, { passive: true });
    rail.addEventListener("pointerdown", hold);
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      rail.removeEventListener("wheel", hold);
      rail.removeEventListener("touchstart", hold);
      rail.removeEventListener("pointerdown", hold);
    };
  }, []);

  const all = slides.flatMap(s => s.drafts);

  return (
    <div className={p.railWrap}>
      <div className={p.railBar}>
        <p className={p.railHint}>
          <span className={p.railLogos} aria-hidden="true">{all.map(d => <Logo key={d.label} brand={d.brand} size={16} />)}</span>
          {all.length} drafts, drifting sideways. Swipe or scroll to look closer.
        </p>
      </div>
      <div ref={railRef} className={p.rail} data-start={edge.start || undefined} data-end={edge.end || undefined}>
        {slides.map((slide, i) => (
          <div key={i} className={p.slide} data-wide={slide.wide || undefined} data-stack={slide.drafts.length > 1 || undefined}>
            {slide.drafts.map(d => (
              <section key={d.label} className={p.draft} aria-label={d.label}>
                <p className={p.slideLabel}><Logo brand={d.brand} size={16} /> {d.label}</p>
                <div className={p.slideBody}>{d.body}</div>
                <p className={p.slideNote}>{d.note}</p>
              </section>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- Who hears first: three circles ---------- */

const circles: { name: string; when: string; how: string; brands: Brand[]; extra?: string[] }[] = [
  { name: "People we know", when: "Beta from now, a message on the day", how: "Friends, classmates and our beta testers. They’ll use it properly and tell us the truth.", brands: ["telegram", "instagram", "linkedin"] },
  { name: "Communities", when: "Launch afternoon", how: "Language learners, makers and AI readers, in the threads each place allows.", brands: ["reddit", "discord", "ycombinator", "indiehackers", "producthunt"], extra: ["HelloTalk", "NUS Hackers"] },
  { name: "Creators", when: "A note the week before", how: "Language YouTubers, with no ask to post.", brands: ["youtube"] },
];

export function Circles() {
  const [ref, inView] = useInViewRef<HTMLDivElement>();
  return (
    <div ref={ref} className={p.circles} data-inview={inView || undefined}>
      <div className={p.rings} aria-hidden="true">
        <span className={p.ring} data-n="3" />
        <span className={p.ring} data-n="2" />
        <span className={p.ring} data-n="1" />
        <Img src="/brand/mascot-180.png" alt="" className={p.ringCore} />
        <b className={p.ringTag} data-n="1">1</b>
        <b className={p.ringTag} data-n="2">2</b>
        <b className={p.ringTag} data-n="3">3</b>
      </div>
      <ol className={p.ringList}>
        {circles.map((c, i) => (
          <li key={c.name} style={{ ["--i" as string]: i }} data-n={i + 1}>
            <p className={p.ringHead}><b>{c.name}</b> <small>{c.when}</small></p>
            <p className={p.ringLogos}>
              {c.brands.map(b => <Logo key={b} brand={b} size={22} title={b} />)}
              {c.extra?.map(name => <span key={name} className={p.textMark}>{name}</span>)}
            </p>
            <p className={p.ringHow}>{c.how}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}

/* ---------- Communities: one line each ---------- */

const communities: { brand: Brand | null; mark?: string; name: string; size?: string; rule: string }[] = [
  { brand: "reddit", name: "r/languagelearning", size: "3.4M", rule: "Resources thread. Exactly our learners." },
  { brand: "reddit", name: "r/Spanish", rule: "Weekly promo thread. We ask the mods first." },
  { brand: "reddit", name: "r/French", rule: "No ads, so we ask the mods for one feedback post." },
  { brand: "reddit", name: "r/SideProject", rule: "Promotion welcome. We lead with how we built it." },
  { brand: "discord", name: "Refold, Language Learning Community, Language Cafe", size: "28k to 37k each", rule: "Promo channels. Daily learners." },
  { brand: null, mark: "HT", name: "HelloTalk", rule: "No promotion, so we share our own journal pages as learners and let people ask." },
  { brand: "ycombinator", name: "Show HN", rule: "Live demo, no sign-up needed, which is what HN asks for." },
  { brand: null, mark: "AI", name: "The Rundown, TLDR AI, Ben’s Bites", rule: "One short pitch each: AI that turns your photo into a lesson." },
  { brand: "indiehackers", name: "Indie Hackers", rule: "One Show IH post, asking for notes on the listing." },
  { brand: null, mark: "NUS", name: "NUS Hackers Friday Hacks", rule: "Ten minutes of live demo. Speakers wanted until 13 Nov." },
];

export function Communities() {
  return (
    <ul className={p.rows}>
      {communities.map(c => (
        <li key={c.name}>
          {c.brand ? <Logo brand={c.brand} size={22} /> : <span className={p.textMark} aria-hidden="true">{c.mark}</span>}
          <b>{c.name}{c.size ? <small> {c.size}</small> : null}</b>
          <span>{c.rule}</span>
        </li>
      ))}
    </ul>
  );
}

/* ---------- Creators: reach against the odds of a reply ---------- */

// x: audience on a log scale (10k to 10M), y: how likely they are to try it and reply (0 to 1).
const creators = [
  { name: "Xiaomanyc", size: "7.1M", reach: 7_100_000, reply: 0.12, note: "Speak-first, and a long shot" },
  { name: "Lindie Botes", size: "357k", reach: 357_000, reply: 0.62, note: "Reviews language apps. Our first email" },
  { name: "Matt vs Japan", size: "Refold", reach: 900_000, reply: 0.4, note: "Comprehensible input" },
  { name: "Ten smaller tutors", size: "under 50k", reach: 30_000, reply: 0.85, note: "Most likely to try it and reply" },
];

const logX = (n: number) => ((Math.log10(n) - 4) / 3) * 100;

export function CreatorMap() {
  const [ref, inView] = useInViewRef<HTMLDivElement>();
  return (
    <figure className={p.fig}>
      <div ref={ref} className={p.map} data-inview={inView || undefined}>
        <span className={p.axisY}>More likely to reply</span>
        <span className={p.axisX}>Bigger audience <Logo brand="youtube" size={14} /></span>
        <div className={p.plot}>
          {creators.map((c, i) => (
            <div key={c.name} className={p.dot} data-side={logX(c.reach) > 60 ? "left" : undefined}
              style={{ left: `${logX(c.reach)}%`, bottom: `${c.reply * 100}%`, ["--i" as string]: i }}>
              <i aria-hidden="true" />
              <p><b>{c.name}</b> <small>{c.size}</small><span>{c.note}</span></p>
            </div>
          ))}
        </div>
      </div>
      <figcaption>
        Followers aren’t the point. A creator with 30,000 viewers who actually tries it beats one with seven million who
        never opens the email.
      </figcaption>
    </figure>
  );
}

/* ---------- Launch day in three shifts ---------- */

const shifts = [
  {
    name: "Afternoon", hours: "14:00 to 01:00", crew: "All four of us", tone: "tomato",
    beats: [
      ["14:00", "Sign up fresh on a phone. Dashboards open."],
      ["15:01", "Live. First comment up within a minute.", true],
      ["15:10", "Every post goes out at once. Friends get a message each."],
      ["16:00", "Every comment answered within the hour."],
      ["21:00", "US east coast wakes up. Second story."],
    ],
  },
  {
    name: "Night", hours: "01:00 to 08:00", crew: "Two on call", tone: "teal",
    beats: [
      ["01:00", "Handover to one replier and one engineer."],
      ["All night", "Watch errors and sign-ups. Answer the US."],
    ],
  },
  {
    name: "Morning", hours: "08:00 to 14:59", crew: "All four of us", tone: "pasta",
    beats: [
      ["08:00", "Read the overnight numbers."],
      ["10:00", "Second nudge in our NUS class chats."],
      ["14:59", "Day ends. Write down what broke."],
    ],
  },
] as const;

export function DayShifts() {
  const [ref, inView] = useInViewRef<HTMLDivElement>();
  return (
    <div ref={ref} className={p.shifts} data-inview={inView || undefined}>
      {shifts.map((shift, i) => (
        <section key={shift.name} className={p.shift} data-tone={shift.tone} style={{ ["--i" as string]: i }}>
          <header>
            <h4>{shift.name}</h4>
            <p>{shift.hours}</p>
            <p className={p.crew}>{shift.crew}</p>
          </header>
          <ol>
            {shift.beats.map(([time, text, live]) => (
              <li key={time} data-live={live || undefined}>
                <time>{time}</time>
                <span>{text}</span>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}

const roles = [
  { role: "Replier", job: "Answers every comment and support email. Our customer support for the day." },
  { role: "Engineer on call", job: "Watches analytics and the error dashboard. Fixes bugs, restarts servers, rolls back." },
  { role: "Poster", job: "Sends the posts and messages on time, and tracks what’s gone out." },
];

export function Roles() {
  return (
    <dl className={p.roles}>
      {roles.map(r => (
        <div key={r.role}>
          <dt>{r.role}</dt>
          <dd>{r.job}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ---------- The one number after launch ---------- */

export function ReturnDots() {
  const [ref, inView] = useInViewRef<HTMLDivElement>();
  return (
    <figure className={p.fig}>
      <div ref={ref} className={p.returns} data-inview={inView || undefined}>
        <div className={p.dots} aria-hidden="true">
          {Array.from({ length: 30 }, (_, i) => <i key={i} data-back={i < 3 || undefined} style={{ ["--i" as string]: i }} />)}
        </div>
        <p className={p.returnsText}>
          <b>3 of 30</b>
          <span>people who sign up during launch week do a second lesson within 7 days. That’s 10%.</span>
        </p>
      </div>
      <figcaption>Our target, not a forecast. We’ll publish the real number either way.</figcaption>
    </figure>
  );
}

/* ---------- Launches are spikes ---------- */

const W = 640;
const H = 250;
const X0 = 44;
const Y0 = 208;
const weekX = (w: number) => X0 + (w / 12) * (W - X0 - 118);

// Weekly active users, as a share of the launch-day peak. A sketch, not data.
const oneLaunch = [0.06, 1, 0.55, 0.38, 0.3, 0.26, 0.24, 0.23, 0.22, 0.215, 0.21, 0.205, 0.2];
const twoLaunches = [...oneLaunch.slice(0, 6), 0.95, 0.62, 0.5, 0.45, 0.42, 0.41, 0.4];

function smooth(values: number[]) {
  const pts = values.map((v, w) => [weekX(w), Y0 - v * (Y0 - 30)] as const);
  return pts.reduce((d, [x, y], i) => {
    if (i === 0) return `M${x},${y}`;
    const [px, py] = pts[i - 1];
    const cx = (px + x) / 2;
    return `${d} C${cx},${py} ${cx},${y} ${x},${y}`;
  }, "");
}

export function GrowthCurve() {
  const [ref, inView] = useInViewRef<HTMLDivElement>();
  const end = (values: number[]) => Y0 - values[12] * (Y0 - 30);
  return (
    <figure className={p.fig}>
      <div ref={ref} className={p.curve} data-inview={inView || undefined}>
        <svg viewBox={`0 0 ${W} ${H}`} aria-labelledby="growth-title">
          <title id="growth-title">Active users over twelve weeks: one launch spikes then settles low; a second launch in week six lifts the level again.</title>
          <rect x={weekX(3)} y={24} width={weekX(5) - weekX(3)} height={Y0 - 24} className={p.planBand} />
          <text x={(weekX(3) + weekX(5)) / 2} y={18} className={p.planText} textAnchor="middle">Plan launch 2 here</text>
          <line x1={X0} y1={Y0} x2={weekX(12)} y2={Y0} className={p.axis} />
          {[0, 2, 4, 6, 8, 10, 12].map(w => (
            <text key={w} x={weekX(w)} y={Y0 + 20} className={p.tick} textAnchor="middle">{w === 0 ? "Week 0" : w}</text>
          ))}
          <text x={X0} y={14} className={p.tick}>Active users</text>
          <path d={smooth(oneLaunch)} className={p.lineOne} />
          <path d={smooth(twoLaunches)} className={p.lineTwo} />
          <text x={weekX(1)} y={Y0 + 38} className={p.launchTick} textAnchor="middle">Launch 1</text>
          <text x={weekX(6)} y={Y0 + 38} className={p.launchTick} textAnchor="middle">Launch 2</text>
          <text x={weekX(12) + 10} y={end(twoLaunches) + 4} className={p.endTwo}>With launch 2</text>
          <text x={weekX(12) + 10} y={end(oneLaunch) + 4} className={p.endOne}>One launch</text>
        </svg>
      </div>
      <figcaption>A sketch of what launches do to active users, not our data.</figcaption>
    </figure>
  );
}

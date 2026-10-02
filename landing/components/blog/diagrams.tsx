import Image from "next/image";
import type { CSSProperties, ReactNode } from "react";
import {
  Book, Camera, Card, Cloud, Database, Flame, Gauge, Layers, Megaphone, Mic, Share, Sparkle, Users,
} from "../icons";
import { InView } from "./story/InView";
import s from "./article.module.css";

type Chip = { icon: ReactNode; label: string };
type Tone = "make" | "value" | "learner" | "money";

function Block({ area, tone, title, index, children }: {
  area: string; tone: Tone; title: string; index: number; children: ReactNode;
}) {
  return (
    <section
      className={`${s.block} ${s[tone]}`}
      style={{ gridArea: area, "--i": index } as CSSProperties}
      aria-label={title}
    >
      <h3 className={s.blockTitle}>{title}</h3>
      {children}
    </section>
  );
}

function Chips({ items }: { items: Chip[] }) {
  return (
    <ul className={s.chips}>
      {items.map(item => (
        <li key={item.label}><span aria-hidden="true">{item.icon}</span>{item.label}</li>
      ))}
    </ul>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <p className={s.stat}>
      <b>{value}</b>
      <span>{label}</span>
    </p>
  );
}

const i = 15;

const personas = [
  { avatar: "/pasta/farfalle.png", name: "Returning learners" },
  { avatar: "/pasta/penne.png", name: "Everyday beginners" },
  { avatar: "/pasta/fusilli.png", name: "Students and travellers" },
];

const zones: { tone: Tone; label: string }[] = [
  { tone: "make", label: "How we deliver" },
  { tone: "value", label: "What learners get" },
  { tone: "learner", label: "Who we serve" },
  { tone: "money", label: "Money" },
];

export function BusinessModelCanvas() {
  return (
    <figure className={`${s.fig} ${s.breakout}`}>
      <ul className={s.zones} aria-label="Colour key">
        {zones.map(zone => <li key={zone.tone} className={s[zone.tone]}>{zone.label}</li>)}
      </ul>
      <InView className={s.canvas}>
        <Block area="partners" tone="make" title="Key partners" index={0}>
          <Chips items={[
            { icon: <Sparkle size={i} />, label: "OpenRouter" },
            { icon: <Sparkle size={i} />, label: "Anthropic · OpenAI · Google" },
            { icon: <Database size={i} />, label: "Supabase" },
            { icon: <Cloud size={i} />, label: "Vercel · Render" },
            { icon: <Card size={i} />, label: "Stripe" },
            { icon: <Users size={i} />, label: "Tutors and creators" },
          ]} />
        </Block>
        <Block area="activities" tone="make" title="Key activities" index={1}>
          <Chips items={[
            { icon: <Camera size={i} />, label: "Photo → lesson" },
            { icon: <Layers size={i} />, label: "Curate scenes" },
            { icon: <Gauge size={i} />, label: "Keep AI cost low" },
          ]} />
        </Block>
        <Block area="resources" tone="make" title="Key resources" index={2}>
          <Chips items={[
            { icon: <Sparkle size={i} />, label: "Lesson pipeline" },
            { icon: <Book size={i} />, label: "Scene library" },
            { icon: <Database size={i} />, label: "Vocabulary data" },
          ]} />
        </Block>
        <Block area="value" tone="value" title="Value proposition" index={3}>
          <p className={s.promise}>Learn the language of your own day.</p>
          <ul className={s.valueList}>
            <li><Camera size={18} /> Your photo is the lesson</li>
            <li><Mic size={18} /> Hear it, say it, play it</li>
            <li><Book size={18} /> Keep the day as a journal page</li>
          </ul>
        </Block>
        <Block area="relationships" tone="learner" title="Relationships" index={4}>
          <Chips items={[
            { icon: <Flame size={i} />, label: "Daily streak" },
            { icon: <Book size={i} />, label: "Journal habit" },
            { icon: <Users size={i} />, label: "Founding Plus club" },
          ]} />
        </Block>
        <Block area="channels" tone="learner" title="Channels" index={5}>
          <Chips items={[
            { icon: <Sparkle size={i} />, label: "Landing demo" },
            { icon: <Megaphone size={i} />, label: "Product Hunt" },
            { icon: <Users size={i} />, label: "Reddit · Discord" },
            { icon: <Share size={i} />, label: "Share cards" },
          ]} />
        </Block>
        <Block area="segments" tone="learner" title="Customer segments" index={6}>
          <ul className={s.people}>
            {personas.map(p => (
              <li key={p.name}>
                <Image src={p.avatar} alt="" width={44} height={44} />
                {p.name}
              </li>
            ))}
          </ul>
        </Block>
        <Block area="costs" tone="money" title="Cost structure" index={7}>
          <div className={s.stats}>
            <Stat value="2¢" label="AI per photo lesson" />
            <Stat value="$52–70" label="hosting a month" />
            <Stat value="3.4% + 50¢" label="per card payment" />
          </div>
        </Block>
        <Block area="revenue" tone="money" title="Revenue streams" index={8}>
          <div className={s.stats}>
            <Stat value="$49.99" label="Plus a year, or $7.99/mo" />
            <Stat value="$34.99" label="Founding Plus, first 300" />
            <Stat value="Later" label="family, classroom, print" />
          </div>
        </Block>
      </InView>
      <figcaption>Linguini’s business model canvas. The customer segments are example learner types, not real users.</figcaption>
    </figure>
  );
}

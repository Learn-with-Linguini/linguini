"use client";

import { useEffect, useRef, useState } from "react";
import { Download } from "@/components/icons";
import { useInView } from "../story/hooks";
import { banners, productHunt } from "./content";
import l from "./launch.module.css";
import { Img, ratio } from "./Img";

function useInViewRef<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  return [ref, useInView(ref)] as const;
}

/* ---------- Product Hunt listing ---------- */

export function ProductHuntListing() {
  const [ref, inView] = useInViewRef<HTMLDivElement>();
  const [shot, setShot] = useState(0);
  const [paused, setPaused] = useState(false);
  const count = productHunt.gallery.length;

  useEffect(() => {
    if (!inView || paused || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => setShot(s => (s + 1) % count), 3200);
    return () => window.clearInterval(id);
  }, [inView, paused, count]);

  return (
    <div ref={ref} className={l.ph} data-inview={inView || undefined} aria-label="Draft Product Hunt listing"
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <header className={l.phHead}>
        <Img src="/blog/launch/product-hunt-icon-240.png" alt="Linguini icon" className={l.phIcon} />
        <div className={l.phName}>
          <h4>{productHunt.name}</h4>
          <p>{productHunt.tagline}</p>
          <ul className={l.phTopics}>
            {productHunt.topics.map(topic => <li key={topic}>{topic}</li>)}
          </ul>
        </div>
        <div className={l.phButtons}>
          <span className={l.phVisit}>Visit</span>
          <span className={l.phUpvote}>▲ Upvote</span>
        </div>
      </header>

      <p className={l.phDesc}>{productHunt.description}</p>

      <div className={l.phGallery}>
        <div className={l.phStage}>
          {productHunt.gallery.map((item, i) => (
            <Img key={item.src} src={item.src} alt={item.alt} data-on={i === shot || undefined} aria-hidden={i !== shot} loading="lazy" />
          ))}
        </div>
        <div className={l.phThumbs}>
          {productHunt.gallery.map((item, i) => (
            <button key={item.src} type="button" data-on={i === shot || undefined} aria-label={`Show gallery image ${i + 1}`}
              onClick={() => setShot(i)}>
              <Img src={item.src} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      </div>

      <div className={l.phComment}>
        <p className={l.phMaker}>
          <span className={l.phFaces} aria-hidden="true">
            <Img src="/pasta/farfalle.png" alt="" /><Img src="/pasta/fusilli.png" alt="" /><Img src="/pasta/penne.png" alt="" />
          </span>
          <b>Linguini team</b> <span className={l.phBadge}>Maker</span> <span className={l.muted}>First comment</span>
        </p>
        {productHunt.firstComment.map((para, i) => (
          <p key={i} className={l.phPara} style={{ ["--i" as string]: i }}>{para}</p>
        ))}
      </div>
    </div>
  );
}

/* ---------- The Product Hunt day on two clocks ---------- */

const ticks = [0, 3, 6, 9, 12, 15, 18, 21, 24];
const pad = (n: number) => String(n % 24).padStart(2, "0");

export function LaunchClock() {
  const [ref, inView] = useInViewRef<HTMLDivElement>();
  return (
    <figure className={`${l.clockFig}`}>
      <div ref={ref} className={l.clock} data-inview={inView || undefined}>
        <div className={l.clockRow}>
          <span className={l.clockLabel}>Pacific</span>
          <div className={l.ticks}>
            {ticks.map(h => <span key={h} style={{ left: `${(h / 24) * 100}%` }}>{pad(h)}:00</span>)}
          </div>
        </div>

        <div className={l.band}>
          <div className={l.dayBar}>
            <b>One Product Hunt day</b>
          </div>
          <div className={l.usBand} style={{ left: `${(5 / 24) * 100}%`, width: `${(12 / 24) * 100}%` }}>
            <span>US daytime, our night</span>
          </div>
          <span className={l.sweep} aria-hidden="true" />
        </div>

        <div className={l.clockRow}>
          <span className={l.clockLabel}>Singapore</span>
          <div className={l.ticks}>
            {ticks.map(h => <span key={h} style={{ left: `${(h / 24) * 100}%` }}>{pad(h + 15)}:00</span>)}
          </div>
        </div>
      </div>
      <figcaption>
        Midnight to midnight in San Francisco is 3:01pm Saturday to 2:59pm Sunday in Singapore.
      </figcaption>
    </figure>
  );
}

/* ---------- Banners ---------- */

export function BannerWall() {
  const [ref, inView] = useInViewRef<HTMLUListElement>();
  return (
    <ul ref={ref} className={l.wall} data-inview={inView || undefined}>
      {banners.map((b, i) => (
        <li key={b.src} style={{ ["--i" as string]: i, ["--r" as string]: ratio(b.src) }}>
          <a href={b.src} download className={l.wallLink}>
            <Img src={b.src} alt={`${b.name} banner`} loading="lazy" />
            <span className={l.wallSave}><Download size={16} /> Save</span>
          </a>
          <p><b>{b.name}</b> <span>{b.size}</span></p>
          <p className={l.muted}>{b.use}</p>
        </li>
      ))}
    </ul>
  );
}

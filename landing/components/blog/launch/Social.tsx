"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
import { useInView, usePrinting } from "../story/hooks";
import { instagram, linkedin, reddit, telegram, xThread } from "./content";
import l from "./launch.module.css";
import { Img } from "./Img";

const AVATAR = "/brand/mascot-180.png";

function reducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Cycles 0..count-1 every `ms` while `running`. */
function useTicker(count: number, ms: number, running: boolean) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (!running || count < 2 || reducedMotion()) return;
    const id = window.setInterval(() => setIndex(i => (i + 1) % count), ms);
    return () => window.clearInterval(id);
  }, [count, ms, running]);
  return [index, setIndex] as const;
}

/* ---------- Small icons drawn to match each app's action row ---------- */

type P = { size?: number };
const svg = (size: number, children: ReactNode, fill = "none") => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor" strokeWidth={1.8}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
);
const Heart = ({ size = 20, filled = false }: P & { filled?: boolean }) =>
  svg(size, <path d="M12 20.5s-7.5-4.6-9.2-9.3C1.6 7.8 3.9 4.5 7.3 4.5c2 0 3.4 1.1 4.7 2.8 1.3-1.7 2.7-2.8 4.7-2.8 3.4 0 5.7 3.3 4.5 6.7-1.7 4.7-9.2 9.3-9.2 9.3Z" />, filled ? "currentColor" : "none");
const Bubble = ({ size = 20 }: P) => svg(size, <path d="M20.5 11.5a8.5 8.5 0 0 1-12.6 7.4L3.5 20l1.2-4.1A8.5 8.5 0 1 1 20.5 11.5Z" />);
const Repost = ({ size = 20 }: P) => svg(size, <><path d="m4 8 3-3 3 3" /><path d="M7 5v10a3 3 0 0 0 3 3h5" /><path d="m20 16-3 3-3-3" /><path d="M17 19V9a3 3 0 0 0-3-3H9" /></>);
const Send = ({ size = 20 }: P) => svg(size, <><path d="M21 3 10.5 13.5" /><path d="M21 3 14.5 21l-4-7.5L3 9.5 21 3Z" /></>);
const Bookmark = ({ size = 20 }: P) => svg(size, <path d="M6 3.5h12v17l-6-4.2-6 4.2v-17Z" />);
const Bars = ({ size = 20 }: P) => svg(size, <><path d="M5 20V12" /><path d="M12 20V5" /><path d="M19 20v-9" /></>);
const Dots = () => <span className={l.more} aria-hidden="true">···</span>;

function LikeButton() {
  const [on, setOn] = useState(false);
  return (
    <button type="button" className={l.action} data-on={on || undefined}
      aria-pressed={on} aria-label={on ? "Unlike" : "Like"} onClick={() => setOn(v => !v)}>
      <Heart filled={on} />
    </button>
  );
}

/** Text with line breaks, #tags and [placeholders] styled like the app would. */
function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\[[A-Z_]+\]|#\w+)/).map((part, i) =>
        /^\[|^#/.test(part) ? <span key={i} className={l.link}>{part}</span> : part,
      )}
    </>
  );
}

/* ---------- X thread ---------- */

export function XThread() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref);
  return (
    <div ref={ref} className={`${l.phoneCard} ${l.x}`} data-inview={inView || undefined} aria-label="Draft X thread">
      {xThread.map((post, i) => (
        <article key={i} className={l.xPost} style={{ ["--i" as string]: i }}>
          <div className={l.xRail}>
            <Img src={AVATAR} alt="" className={l.avatar} />
            {i < xThread.length - 1 ? <span className={l.thread} /> : null}
          </div>
          <div className={l.xMain}>
            <p className={l.xHead}>
              <b>Linguini</b> <span>Draft · 17 Oct</span> <Dots />
            </p>
            <p className={l.xText}><Rich text={post.text} /></p>
            {post.image ? <Img src={post.image.src} alt={post.image.alt} className={l.xImage} loading="lazy" /> : null}
            <div className={l.xActions}>
              <span className={l.action}><Bubble size={18} /></span>
              <span className={l.action}><Repost size={18} /></span>
              <LikeButton />
              <span className={l.action}><Bars size={18} /></span>
              <span className={l.action}><Bookmark size={18} /></span>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

/* ---------- Instagram feed post ---------- */

export function InstagramPost() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref);
  const [paused, setPaused] = useState(false);
  const [slide, setSlide] = useTicker(instagram.slides.length, 3600, inView && !paused);
  const [burst, setBurst] = useState(0);
  const [liked, setLiked] = useState(false);
  const [opened, setOpen] = useState(false);
  const printing = usePrinting();
  const open = opened || printing;

  const like = () => {
    setLiked(true);
    setBurst(n => n + 1);
  };

  return (
    <div ref={ref} className={`${l.phoneCard} ${l.ig}`} data-inview={inView || undefined} aria-label="Draft Instagram post"
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <header className={l.igHead}>
        <span className={l.ring}><Img src={AVATAR} alt="" /></span>
        <b>linguini</b>
        <span className={l.igSub}>Original audio</span>
        <Dots />
      </header>

      <div className={l.igMedia} onDoubleClick={like}>
        <div className={l.igTrack} style={{ transform: `translateX(${-slide * 100}%)` }}>
          {instagram.slides.map((item, i) => (
            <Img key={item.src} src={item.src} alt={item.alt} aria-hidden={i !== slide} loading="lazy" />
          ))}
        </div>
        <span className={l.igCount}>{slide + 1}/{instagram.slides.length}</span>
        {burst ? <span key={burst} className={l.burst} aria-hidden="true"><Heart size={96} filled /></span> : null}
        <button type="button" className={`${l.igNav} ${l.igPrev}`} aria-label="Previous slide"
          onClick={() => setSlide(i => (i - 1 + instagram.slides.length) % instagram.slides.length)}>‹</button>
        <button type="button" className={`${l.igNav} ${l.igNext}`} aria-label="Next slide"
          onClick={() => setSlide(i => (i + 1) % instagram.slides.length)}>›</button>
      </div>

      <div className={l.igActions}>
        <button type="button" className={l.action} data-on={liked || undefined} aria-pressed={liked}
          aria-label={liked ? "Unlike" : "Like"} onClick={() => (liked ? setLiked(false) : like())}>
          <Heart size={24} filled={liked} />
        </button>
        <span className={l.action}><Bubble size={24} /></span>
        <span className={l.action}><Send size={24} /></span>
        <span className={l.igDots} aria-hidden="true">
          {instagram.slides.map((_, i) => <i key={i} data-on={i === slide || undefined} />)}
        </span>
        <span className={l.action}><Bookmark size={24} /></span>
      </div>

      <p className={l.igCaption} data-open={open || undefined}>
        <b>linguini</b> <Rich text={instagram.caption} />
        {open ? <><br /><br /><span className={l.link}>{instagram.tags}</span></> : null}
      </p>
      {!open ? <button type="button" className={l.igMore} onClick={() => setOpen(true)}>more</button> : null}
      <p className={l.igHint}>Double-click the photo. It works.</p>
    </div>
  );
}

/* ---------- Instagram story in a phone ---------- */

export function StoryPhone() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref);
  const [frame] = useTicker(instagram.story.length, 5000, inView);
  return (
    <div ref={ref} className={l.phone} data-inview={inView || undefined} aria-label="Draft Instagram story sequence">
      <div className={l.screen}>
        <div className={l.progress}>
          {instagram.story.map((_, i) => (
            <span key={i} data-state={i < frame ? "done" : i === frame ? "now" : undefined}>
              <i key={i === frame ? `on-${frame}` : "off"} />
            </span>
          ))}
        </div>
        <p className={l.storyHead}>
          <Img src={AVATAR} alt="" /> <b>linguini</b> <span>{frame === 0 ? "3d" : "now"}</span>
        </p>
        {instagram.story.map((item, i) => (
          <Img key={item.src} src={item.src} alt={item.alt} className={l.storyImg} data-on={i === frame || undefined}
            loading="lazy" />
        ))}
        {frame === 1 ? <span className={l.sticker}>🔗 PRODUCT HUNT</span> : null}
      </div>
    </div>
  );
}

/* ---------- The other channels ---------- */

export function LinkedInPost() {
  const [opened, setOpen] = useState(false);
  const printing = usePrinting();
  const open = opened || printing;
  const [first, ...rest] = linkedin.text.split("\n\n");
  return (
    <article className={`${l.phoneCard} ${l.li}`} aria-label="Draft LinkedIn post">
      <header className={l.liHead}>
        <Img src="/pasta/farfalle.png" alt="" />
        <div>
          <b>{linkedin.author}</b>
          <span>{linkedin.role}</span>
          <span>Draft · 🌐</span>
        </div>
      </header>
      <p className={l.liText}>
        {first}
        {open ? rest.map(p => <span key={p}><br /><br />{p}</span>) : null}
        {!open ? <button type="button" className={l.liMore} onClick={() => setOpen(true)}>…more</button> : null}
      </p>
      <Img src={linkedin.image.src} alt={linkedin.image.alt} className={l.liImage} loading="lazy" />
      <div className={l.liActions}>
        <LikeButton /><span>Like</span>
        <span className={l.action}><Bubble size={18} /></span><span>Comment</span>
        <span className={l.action}><Repost size={18} /></span><span>Repost</span>
      </div>
    </article>
  );
}

export function RedditPost() {
  const [vote, setVote] = useState(0);
  return (
    <article className={`${l.phoneCard} ${l.rd}`} aria-label="Draft Reddit comment">
      <p className={l.rdSub}>
        <span className={l.rdIcon}>r/</span><b>{reddit.sub}</b> · <span className={l.rdFlair}>{reddit.flair}</span>
      </p>
      <h4 className={l.rdTitle}>{reddit.title}</h4>
      <p className={l.rdText}>{reddit.text}</p>
      <div className={l.rdActions}>
        <span className={l.rdVote} data-vote={vote || undefined}>
          <button type="button" aria-label="Upvote" onClick={() => setVote(v => (v === 1 ? 0 : 1))}>▲</button>
          <b>{vote === 1 ? "Nice" : vote === -1 ? "Fair" : "Vote"}</b>
          <button type="button" aria-label="Downvote" onClick={() => setVote(v => (v === -1 ? 0 : -1))}>▼</button>
        </span>
        <span className={l.rdPill}><Bubble size={16} /> Reply</span>
        <span className={l.rdPill}><Send size={16} /> Share</span>
      </div>
    </article>
  );
}

export function TelegramChat() {
  return (
    <div className={`${l.phoneCard} ${l.tg}`} aria-label="Draft Telegram message">
      <p className={l.tgHead}><b>{telegram.group}</b><span>group</span></p>
      <div className={l.tgBody}>
        <div className={l.tgTyping} aria-hidden="true"><i /><i /><i /></div>
        <div className={l.tgBubble}>
          <Img src={telegram.image.src} alt={telegram.image.alt} className={l.tgPhoto} />
          <b className={l.tgName}>Madrid</b>
          <p>{telegram.text} <span className={l.link}>[PH_POST_URL]</span></p>
          <span className={l.tgTime}>15:12 ✓✓</span>
        </div>
      </div>
    </div>
  );
}

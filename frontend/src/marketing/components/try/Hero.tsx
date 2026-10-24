
import Image from "../Image";
import { useEffect, useRef } from "react";
import { scenes } from "../../data/scenes";
import { appLinks } from "../../lib/site";
import { ArrowRight } from "../icons";
import { ProductHuntBadge } from "../ProductHuntBadge";
import styles from "./hero.module.css";

/** Where each print sits around the headline on wide screens. */
const slots = [
  { left: "0%", top: "4%", w: 250, r: -7, d: 1.2 },
  { left: "8%", top: "38%", w: 196, r: 5, d: 0.6 },
  { left: "1%", top: "68%", w: 236, r: -3, d: 1 },
  { left: "23%", top: "81%", w: 172, r: 6, d: 0.5 },
  { right: "1%", top: "3%", w: 236, r: 6, d: 1.1 },
  { right: "8%", top: "37%", w: 200, r: -5, d: 0.7 },
  { right: "0%", top: "64%", w: 236, r: 3, d: 1.2 },
  { right: "24%", top: "82%", w: 168, r: -6, d: 0.5 },
] as const;

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function Hero() {
  const sectionRef = useRef<HTMLElement>(null);

  // Gentle pointer parallax on the photo ring.
  useEffect(() => {
    const node = sectionRef.current;
    if (!node || reducedMotion() || !window.matchMedia("(pointer: fine)").matches) return;
    let frame = 0;
    const onMove = (event: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const rect = node.getBoundingClientRect();
        node.style.setProperty("--px", ((event.clientX - rect.left) / rect.width - 0.5).toFixed(3));
        node.style.setProperty("--py", ((event.clientY - rect.top) / rect.height - 0.5).toFixed(3));
      });
    };
    node.addEventListener("pointermove", onMove);
    return () => {
      node.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <section
      id="try"
      ref={sectionRef}
      className={styles.hero}
      aria-labelledby="hero-title"
    >
        <div className={`container ${styles.stage}`}>
          <div className={styles.copy}>
            <p className={styles.betaNote}>Free public beta</p>
            <h1 id="hero-title" className={styles.title}>
              Learn the language of <span className={styles.underline}>your day.</span>
            </h1>
            <p className={styles.lede}>
              Snap the café, the street, the view.
            </p>
            <p>Linguini finds the words in your photo and turns them into a
              five-minute game in <span className={styles.lang}>Spanish</span>, <span className={styles.lang}>French</span>,{" "}
              <span className={styles.lang}>German</span> or <span className={styles.lang}>beginner Korean</span>.</p>
            <div className={styles.ctas}>
              <a href={appLinks.signUp} className="btn">
                Join the public beta
              </a>
              <a className={`btn btn--teal ${styles.uploadCta}`} href="/demo">Try a photo lesson</a>
            </div>
            <ProductHuntBadge />
          </div>

          <ul className={styles.ring} aria-label="Photos you can learn from">
            {scenes.slice(0, slots.length).map((item, index) => {
              const slot = slots[index];
              return (
                <li
                  key={item.id}
                  className={styles.slot}
                  style={
                    {
                      left: "left" in slot ? slot.left : undefined,
                      right: "right" in slot ? slot.right : undefined,
                      top: slot.top,
                      "--w": `${slot.w}px`,
                      "--r": `${slot.r}deg`,
                      "--d": slot.d,
                      "--i": index,
                    } as React.CSSProperties
                  }
                >
                  <button
                    type="button"
                    className={styles.print}
                    onClick={() => window.location.assign(`/demo?photo=${encodeURIComponent(item.id)}`)}
                    aria-label={`Learn from “${item.title}”, ${item.place}`}
                  >
                    <span
                      className={styles.printImage}
                      data-print={item.id}
                      style={{
                        aspectRatio: `${item.width} / ${item.height}`,
                      }}
                    >
                      <Image src={item.photo} alt="" fill sizes="260px" priority={index < 4} className={styles.printImg} />
                    </span>
                    <span className={styles.printCaption}>
                      {item.title}
                      <span className={styles.printCta}>Learn this <ArrowRight size={14} /></span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
    </section>
  );
}

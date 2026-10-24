
import Image from "../Image";
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { scenes, getScene } from "../../data/scenes";
import type { Lang } from "../../data/types";
import { appLinks } from "../../lib/site";
import { ArrowRight } from "../icons";
import { ProductHuntBadge } from "../ProductHuntBadge";
import { LanguageToggle } from "./LanguageToggle";
import { GuestSession } from "./GuestSession";
import { analyzeGuestPhoto, staticGuestScene, type GuestScene } from "./demoApi";
import { trackAction } from "../../../lib/analytics";
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

type ViewTransitionDocument = Document & {
  startViewTransition?: (callback: () => void) => { finished: Promise<void> };
};

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function Hero() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [returnId, setReturnId] = useState<string | null>(null);
  const [lang, setLang] = useState<Lang>("es");
  const [uploadedScene, setUploadedScene] = useState<GuestScene | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const sampleScene = activeId ? getScene(activeId) : undefined;
  const scene = uploadedScene ?? (sampleScene ? staticGuestScene(sampleScene, lang) : undefined);

  const transition = useCallback((update: () => void) => {
    const doc = document as ViewTransitionDocument;
    const scrollToStage = () => {
      const top = sectionRef.current ? sectionRef.current.getBoundingClientRect().top + window.scrollY - 72 : 0;
      if (window.scrollY > top + 40) window.scrollTo({ top: Math.max(0, top) });
    };
    if (!doc.startViewTransition || reducedMotion()) {
      update();
      scrollToStage();
      return null;
    }
    return doc.startViewTransition(() => {
      flushSync(update);
      scrollToStage();
    });
  }, []);

  const pick = useCallback(
    (id: string, element?: HTMLElement | null) => {
      if (element) element.style.viewTransitionName = "picked-photo";
      setReturnId(null);
      setUploadedScene(null);
      const vt = transition(() => setActiveId(id));
      vt?.finished.finally(() => {
        if (element) element.style.viewTransitionName = "";
      });
    },
    [transition],
  );

  const exit = useCallback(() => {
    const id = activeId;
    const vt = transition(() => {
      setReturnId(id);
      setActiveId(null);
      setUploadedScene(null);
    });
    if (vt) vt.finished.finally(() => setReturnId(null));
    else setReturnId(null);
  }, [activeId, transition]);

  const upload = useCallback(async (file: File) => {
    setUploadError(null);
    setUploading(true);
    trackAction("guest_demo_photo_selected", { language: lang });
    try {
      const result = await analyzeGuestPhoto(file, lang);
      setActiveId(null);
      setUploadedScene(result);
      trackAction("guest_demo_photo_analyzed", { language: lang, objectCount: result.words.length });
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "We couldn't prepare that photo lesson.");
      trackAction("guest_demo_photo_failed", { language: lang });
    } finally {
      setUploading(false);
    }
  }, [lang]);

  // Deep link: /?photo=<id>#try opens a session straight away.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("photo");
    // oxlint-disable-next-line react/set-state-in-effect -- the URL is only readable after hydration
    if (id && getScene(id)) setActiveId(id);
  }, []);

  useEffect(() => {
    if (!uploadedScene?.photo.startsWith("blob:")) return;
    return () => URL.revokeObjectURL(uploadedScene.photo);
  }, [uploadedScene]);

  // Gentle pointer parallax on the photo ring.
  useEffect(() => {
    const node = sectionRef.current;
    if (!node || activeId || reducedMotion() || !window.matchMedia("(pointer: fine)").matches) return;
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
  }, [activeId]);

  return (
    <section
      id="try"
      ref={sectionRef}
      className={`${styles.hero} ${scene ? styles.inSession : ""}`}
      aria-labelledby={scene ? undefined : "hero-title"}
      aria-label={scene ? `Mini session: ${scene.title}` : undefined}
    >
      {scene ? (
        <div className={`container ${styles.sessionWrap}`}>
          <GuestSession scene={scene} lang={lang} onLangChange={setLang} onExit={exit} />
        </div>
      ) : (
        <div className={`container ${styles.stage}`}>
          <div className={styles.copy}>
            <h1 id="hero-title" className={styles.title}>
              Learn the language of <span className={styles.underline}>your day.</span>
            </h1>
            <p className={styles.lede}>
              Photograph the café you’re sitting in, the street you walked, the view from the bridge. Linguini finds the
              words inside the picture, turns them into a short language game, and keeps the day in your journal. The app
              supports Spanish, French, German and beginner Korean.
            </p>
            <p className={styles.betaNote}>Public beta · Free access · Unlimited photo lessons</p>
            <div className={styles.ctas}>
              <a href={appLinks.signUp} className="btn">
                Join the public beta
              </a>
              <label className={`btn btn--teal ${styles.uploadCta}`}>
                {uploading ? "Preparing your lesson…" : "Try your own photo"}
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  disabled={uploading}
                  className="visually-hidden"
                  onChange={event => {
                    const file = event.target.files?.[0];
                    if (file) void upload(file);
                    event.target.value = "";
                  }}
                />
              </label>
            </div>
            <p className="small">Guest photos are processed to build the demo and aren’t saved to your account.</p>
            {uploadError ? <p role="alert" className={styles.uploadError}>{uploadError}</p> : null}
            <div className={styles.prompt}>
              <svg className={styles.noodle} viewBox="0 0 120 60" aria-hidden="true">
                <path d="M4 50c18 4 30-6 30-18s-14-16-18-6 8 20 28 18 44-18 66-34" />
                <path d="m100 6 12 4-8 10" />
              </svg>
              <p>
                <b>Pick a sample or upload your own</b> to start a guest lesson in
              </p>
              <LanguageToggle value={lang} onChange={setLang} compact />
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
                    onClick={event => pick(item.id, event.currentTarget.querySelector<HTMLElement>("[data-print]"))}
                    aria-label={`Learn from “${item.title}”, ${item.place}`}
                  >
                    <span
                      className={styles.printImage}
                      data-print={item.id}
                      style={{
                        aspectRatio: `${item.width} / ${item.height}`,
                        viewTransitionName: returnId === item.id ? "picked-photo" : undefined,
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
      )}
    </section>
  );
}

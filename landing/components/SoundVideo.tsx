"use client";

import { useEffect, useRef, useState } from "react";
import { Speaker, SpeakerOff } from "./icons";
import styles from "./Film.module.css";

export type VideoSource = { src: string; media?: string };

/**
 * A muted loop with a "Sound on" button, the format of the home-page film. Plays only while on screen,
 * and stays on its poster for reduced-motion users until they ask for sound.
 */
export function SoundVideo({ sources, poster, label, captions, className }: {
  sources: VideoSource[];
  poster: string;
  label: string;
  /** WebVTT file shown as captions when the sound is off. */
  captions?: string;
  className?: string;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const [muted, setMuted] = useState(true);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    let inView = false;
    const sync = () => {
      if (inView && (!query.matches || !video.muted)) void video.play().catch(() => {});
      else video.pause();
    };
    const observer = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      sync();
    }, { rootMargin: "200px 0px" });
    observer.observe(video);
    query.addEventListener("change", sync);
    return () => {
      observer.disconnect();
      query.removeEventListener("change", sync);
    };
  }, []);

  // Turning the sound on restarts the video so the voice and score start from the top.
  const toggleSound = () => {
    const video = ref.current;
    if (!video) return;
    const next = !muted;
    video.muted = next;
    if (!next) {
      video.currentTime = 0;
      void video.play().catch(() => {});
    }
    setMuted(next);
  };

  return (
    <div className={`${styles.frame} ${className ?? ""}`}>
      <video ref={ref} className={styles.video} poster={poster} muted loop playsInline preload="none" aria-label={label}>
        {sources.map(source => <source key={source.src} src={source.src} type="video/mp4" media={source.media} />)}
        {captions ? <track kind="captions" src={captions} srcLang="en" label="English" default /> : null}
      </video>
      <button type="button" className={styles.sound} onClick={toggleSound} aria-pressed={!muted}>
        {muted ? <SpeakerOff size={18} /> : <Speaker size={18} />}
        {muted ? "Sound on" : "Sound off"}
      </button>
    </div>
  );
}

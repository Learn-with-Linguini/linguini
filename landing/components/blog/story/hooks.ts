"use client";

import { type RefObject, useEffect, useRef, useState } from "react";

/** True once the element has scrolled into view (stays true). */
export function useInView<T extends Element>(ref: RefObject<T | null>, rootMargin = "0px 0px -15% 0px") {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      entries => {
        if (entries.some(entry => entry.isIntersecting)) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin, threshold: 0.2 },
    );
    observer.observe(node);
    const show = () => setInView(true);
    window.addEventListener("beforeprint", show);
    return () => {
      observer.disconnect();
      window.removeEventListener("beforeprint", show);
    };
  }, [ref, rootMargin]);
  return inView;
}

/** Rendered width of an element, for charts drawn at real pixel size. */
export function useWidth<T extends Element>(ref: RefObject<T | null>, fallback = 640) {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

/** Eases a displayed number toward `value` whenever it changes. */
export function useTween(value: number, duration = 700) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = performance.now();
    const origin = from.current;
    if (origin === value) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      from.current = value;
      const id = requestAnimationFrame(() => setShown(value));
      return () => cancelAnimationFrame(id);
    }
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      const next = origin + (value - origin) * eased;
      from.current = next;
      setShown(next);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);
  return shown;
}

/** True while the page is being printed or saved as PDF, so collapsed content can render in full. */
export function usePrinting() {
  const [printing, setPrinting] = useState(false);
  useEffect(() => {
    const on = () => setPrinting(true);
    const off = () => setPrinting(false);
    window.addEventListener("beforeprint", on);
    window.addEventListener("afterprint", off);
    return () => {
      window.removeEventListener("beforeprint", on);
      window.removeEventListener("afterprint", off);
    };
  }, []);
  return printing;
}

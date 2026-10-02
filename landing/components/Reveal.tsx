"use client";

import { useEffect, useRef, type ElementType, type ReactNode, type CSSProperties } from "react";

type RevealProps = {
  as?: ElementType;
  className?: string;
  delay?: number;
  children: ReactNode;
  style?: CSSProperties;
} & Record<string, unknown>;

/** Fades content up once it scrolls into view. Content stays visible without JavaScript. */
export function Reveal({ as: Tag = "div", className = "", delay = 0, children, style, ...rest }: RevealProps) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.12 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      className={`reveal ${className}`.trim()}
      style={{ ...style, "--reveal-delay": `${delay}ms` } as CSSProperties}
      {...rest}
    >
      {children}
    </Tag>
  );
}

"use client";

import { type ElementType, type ReactNode, useRef } from "react";
import { useInView } from "./hooks";

/** Sets `data-inview` once the element scrolls into view, so CSS can animate its children. */
export function InView({ as: Tag = "div", className, children, ...rest }: {
  as?: ElementType;
  className?: string;
  children: ReactNode;
} & Record<string, unknown>) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref);
  return (
    <Tag ref={ref} className={className} data-inview={inView || undefined} {...rest}>
      {children}
    </Tag>
  );
}

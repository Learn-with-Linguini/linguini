import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { Button } from "./ui";

type Props = {
  targetRef: RefObject<HTMLElement | null>;
  step: number;
  totalSteps: number;
  title: string;
  description: string;
  nextLabel: string;
  saving?: boolean;
  error?: string | null;
  onBack?: () => void;
  onNext: () => void;
  onSkip: () => void;
};

type Rect = { top: number; left: number; width: number; height: number };

const SPOTLIGHT_PAD = 7;
const SPOTLIGHT_RADIUS = 18;
const OVERLAY_FILL = "rgba(25, 37, 42, 0.72)";

function sameRect(a: Rect | null, b: Rect | null) {
  return a === b || (!!a && !!b && a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height);
}

export function WalkthroughCoachmark({
  targetRef,
  step,
  totalSteps,
  title,
  description,
  nextLabel,
  saving = false,
  error,
  onBack,
  onNext,
  onSkip,
}: Props) {
  const titleId = useId();
  const descriptionId = useId();
  const maskId = useId().replace(/:/g, "");
  const layerRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const [rect, setRect] = useState<Rect | null>(null);

  useEffect(() => {
    const previousFocus = document.activeElement;
    const bodyOverflow = document.body.style.overflow;
    const pageOverflow = document.documentElement.style.overflow;
    const bodyPadding = document.body.style.paddingRight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    const background = [...document.body.children]
      .filter(element => element !== layerRef.current)
      .map(element => ({ element, inert: element.getAttribute("inert") }));

    if (scrollbarWidth > 0) {
      document.body.style.paddingRight = `${parseFloat(getComputedStyle(document.body).paddingRight) + scrollbarWidth}px`;
    }
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    for (const { element } of background) element.setAttribute("inert", "");

    const trapFocus = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const buttons = [...dialog.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
      const first = buttons[0];
      const last = buttons.at(-1);
      if (!first || !last) {
        event.preventDefault();
        dialog.focus({ preventScroll: true });
      } else if (event.shiftKey && (document.activeElement === first || !buttons.includes(document.activeElement as HTMLButtonElement))) {
        event.preventDefault();
        last.focus({ preventScroll: true });
      } else if (!event.shiftKey && (document.activeElement === last || !buttons.includes(document.activeElement as HTMLButtonElement))) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    };
    document.addEventListener("keydown", trapFocus);
    return () => {
      document.removeEventListener("keydown", trapFocus);
      document.body.style.overflow = bodyOverflow;
      document.documentElement.style.overflow = pageOverflow;
      document.body.style.paddingRight = bodyPadding;
      for (const { element, inert } of background) {
        if (inert === null) element.removeAttribute("inert");
        else element.setAttribute("inert", inert);
      }
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      const target = targetRef.current;
      const bounds = target?.getBoundingClientRect();
      const next = bounds ? { top: bounds.top, left: bounds.left, width: bounds.width, height: bounds.height } : null;
      setRect(prev => (sameRect(prev, next) ? prev : next));
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(measure); };
    // Focus must not start a second scroll while the highlighted target is positioned.
    targetRef.current?.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
    dialogRef.current?.focus({ preventScroll: true });
    schedule();
    window.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);
    window.visualViewport?.addEventListener("resize", schedule);
    window.visualViewport?.addEventListener("scroll", schedule);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(schedule);
    if (targetRef.current) observer?.observe(targetRef.current);
    if (dialogRef.current) observer?.observe(dialogRef.current);
    observer?.observe(document.body);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener("scroll", schedule, true);
      window.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("scroll", schedule);
    };
  }, [targetRef, step]);

  if (typeof document === "undefined") return null;
  return createPortal(
    <div ref={layerRef} className="walkthrough-layer">
      <svg className="walkthrough-overlay" aria-hidden="true">
        <defs>
          <mask id={maskId}>
            <rect width="100%" height="100%" fill="#fff" />
            {rect ? (
              <rect
                x={rect.left - SPOTLIGHT_PAD}
                y={rect.top - SPOTLIGHT_PAD}
                width={rect.width + SPOTLIGHT_PAD * 2}
                height={rect.height + SPOTLIGHT_PAD * 2}
                rx={SPOTLIGHT_RADIUS}
                fill="#000"
              />
            ) : null}
          </mask>
        </defs>
        <rect width="100%" height="100%" fill={OVERLAY_FILL} mask={`url(#${maskId})`} />
      </svg>
      {rect ? (
        <div
          className="walkthrough-ring"
          aria-hidden="true"
          style={{
            top: rect.top - SPOTLIGHT_PAD + 5,
            left: rect.left - SPOTLIGHT_PAD,
            width: rect.width + SPOTLIGHT_PAD * 2,
            height: rect.height + SPOTLIGHT_PAD * 2,
          }}
        />
      ) : null}
      <section
        ref={dialogRef}
        className="walkthrough-coachmark"
        role="dialog"
        tabIndex={-1}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <span className="walkthrough-coachmark__step">Step {step} of {totalSteps}</span>
        <h2 id={titleId}>{title}</h2>
        <p id={descriptionId}>{description}</p>
        {error ? <p className="walkthrough-coachmark__error" role="alert">{error}</p> : null}
        <div className="walkthrough-coachmark__actions">
          <Button variant="quiet" disabled={saving} onClick={onSkip}>Skip guide</Button>
          {onBack ? <Button variant="secondary" disabled={saving} onClick={onBack}>Back</Button> : null}
          <Button disabled={saving} onClick={onNext}>{saving ? "Saving…" : nextLabel}</Button>
        </div>
      </section>
    </div>,
    document.body,
  );
}

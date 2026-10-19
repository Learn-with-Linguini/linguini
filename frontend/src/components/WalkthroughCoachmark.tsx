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
  const dialogRef = useRef<HTMLElement>(null);
  const [rect, setRect] = useState<Rect | null>(null);

  useEffect(() => {
    targetRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
  }, [targetRef, step]);

  useEffect(() => {
    let frame = 0;
    const track = () => {
      const target = targetRef.current;
      const next = target ? target.getBoundingClientRect() : null;
      setRect(prev => (sameRect(prev, next) ? prev : next));
      frame = requestAnimationFrame(track);
    };
    frame = requestAnimationFrame(track);
    return () => cancelAnimationFrame(frame);
  }, [targetRef]);

  if (typeof document === "undefined") return null;
  return createPortal(
    <>
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
    </>,
    document.body,
  );
}

import { useEffect, useId, useRef, type RefObject } from "react";
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
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const target = targetRef.current;
    if (!target) return;
    target.classList.add("walkthrough-target");
    target.scrollIntoView({ block: "center", behavior: "smooth" });
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => target.classList.remove("walkthrough-target");
  }, [targetRef, step]);

  if (typeof document === "undefined") return null;
  return createPortal(
    <>
      <div className="walkthrough-overlay" aria-hidden="true" />
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

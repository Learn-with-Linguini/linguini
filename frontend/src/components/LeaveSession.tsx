import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "./ui";
import { useBackAction } from "./BackAction";
import { abandonPractice } from "../lib/api";
import { friendlyError } from "../lib/queryKeys";

export function LeaveSession({ sessionId, warning }: { sessionId: string; warning: string }) {
  const navigate = useNavigate();
  const [asking, setAsking] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!asking) return;
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !leaving) setAsking(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [asking, leaving]);

  // The brand-bar chevron is the leave trigger; ignore repeats while open or in flight.
  useBackAction(() => {
    if (!leaving) setAsking(true);
  }, "Leave this session");

  // Stays disabled after a successful abandon so a queued click cannot reach the picker.
  const leave = async () => {
    if (leaving) return;
    setLeaving(true);
    setError(null);
    try {
      await abandonPractice(sessionId);
      navigate("/practice", { replace: true });
    } catch (reason) {
      setError(friendlyError(reason));
      setLeaving(false);
    }
  };

  return (
    <>
      {asking ? (
        <div
          className="help-modal__backdrop"
          onMouseDown={() => {
            if (!leaving) setAsking(false);
          }}
        >
          <section
            ref={dialogRef}
            className="help-modal leave-session__dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <h2 id={titleId}>Leave this session?</h2>
            <p>{warning}</p>
            {error ? (
              <p className="leave-session__error" role="alert">
                {error}
              </p>
            ) : null}
            <div className="leave-session__actions">
              <Button variant="secondary" block disabled={leaving} onClick={() => void leave()}>
                {leaving ? "Leaving..." : "Leave and start over"}
              </Button>
              <Button variant="quiet" block disabled={leaving} onClick={() => setAsking(false)}>
                Keep practising
              </Button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}

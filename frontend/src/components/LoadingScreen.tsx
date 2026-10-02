import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import "./LoadingScreen.css";

let activeOverlays = 0;
let restoreBackground: (() => void) | undefined;

/** Mount while a page is loading; unmounting restores background interaction. */
export function LoadingScreen({ label = "Loading…" }: { label?: string }) {
  const status = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (activeOverlays === 0) {
      const root = document.getElementById("root");
      const wasInert = root?.inert ?? false;
      const overflow = document.body.style.overflow;
      const focused = document.activeElement;
      if (root) root.inert = true;
      document.body.style.overflow = "hidden";
      restoreBackground = () => {
        if (root) root.inert = wasInert;
        document.body.style.overflow = overflow;
        if (focused instanceof HTMLElement && focused.isConnected) {
          focused.focus({ preventScroll: true });
        }
      };
    }
    activeOverlays += 1;
    status.current?.focus({ preventScroll: true });
    return () => {
      activeOverlays -= 1;
      if (activeOverlays === 0) {
        restoreBackground?.();
        restoreBackground = undefined;
      }
    };
  }, []);

  // A portal keeps the status accessible while the app root is inert.
  return createPortal(
    <div className="loading-screen">
      <div className="loading-screen__status" role="status" aria-live="polite" aria-atomic="true" tabIndex={-1} ref={status}>
        <div className="loading-fork" aria-hidden="true">
          <img src="/loading/fork-spaghetti.png" alt="" />
        </div>
        <span className="loading-screen__label">{label}</span>
      </div>
    </div>,
    document.body,
  );
}

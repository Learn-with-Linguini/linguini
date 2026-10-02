import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui";
import { ArrowRightIcon, MicIcon } from "../components/icons";
import { useScene } from "../state/useScene";
import { useAppState } from "../state/useAppState";
import { friendlyError } from "../lib/queryKeys";

type MicState = "idle" | "listening" | "working" | "unavailable";

export function MicTest() {
  const navigate = useNavigate();
  const scene = useScene();
  const { setMicReady, learner } = useAppState();
  const [state, setState] = useState<MicState>(learner.micOn ? "idle" : "unavailable");
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const pending = useRef(false);

  useEffect(() => {
    setMicReady(false);
    return () => { generation.current += 1; };
  }, [setMicReady]);

  const listen = async () => {
    if (!learner.micOn || pending.current) return;
    pending.current = true;
    const version = ++generation.current;
    setState("listening");
    setError(null);
    setMicReady(false);
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone access is unavailable in this browser.");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const available = stream.getAudioTracks().some(track => track.readyState === "live");
      stream.getTracks().forEach(track => track.stop());
      if (version !== generation.current) return;
      if (!available) throw new Error("No microphone was detected.");
      setState("working");
      setMicReady(true);
    } catch (reason) {
      if (version !== generation.current) return;
      setState("unavailable");
      setError(friendlyError(reason));
    } finally { pending.current = false; }
  };

  const skip = () => {
    generation.current += 1;
    setState("unavailable");
    setError(null);
    setMicReady(false);
  };

  return (
    <div className="stack mic-test-page">
      <h1>Test your mic</h1>
      <p className="muted">Check microphone access, or continue with typing.</p>

      <section className="mic-test-panel" aria-label="Microphone test">
        <div className="mic-prompt">
          <h2>{scene.items[0]?.example || "Testing my microphone."}</h2>
          <span className="small muted">{scene.items[0]?.exampleTranslation}</span>
        </div>

        <button
          type="button"
          className="mic-test-control"
          onClick={() => void listen()}
          disabled={!learner.micOn || state === "listening"}
          aria-label={state === "listening" ? "Listening" : "Test my microphone"}
        >
          <span className={`mic-orb${state === "listening" ? " mic-orb--live" : ""}`}>
            <MicIcon size={48} />
          </span>
          <strong>{state === "listening" ? "Listening…" : "Tap to test"}</strong>
        </button>

        {state === "working" ? (
          <p className="mic-status mic-status--success" role="status">
            Microphone access is ready.
          </p>
        ) : null}

        {state === "unavailable" ? (
          <p className="mic-status" role="status">
            Typing is ready instead.
          </p>
        ) : null}
        {error ? <p role="alert">{error} You can continue with typing.</p> : null}
      </section>

      <Button
        variant="quiet"
        className="mic-typing-action"
        block
        onClick={skip}
      >
        Use typing instead
      </Button>

      <Button
        block
        disabled={state === "idle" || state === "listening"}
        onClick={() => navigate(`/practice/sessions/${scene.sessionId}/learn`)}
      >
        Continue <ArrowRightIcon />
      </Button>
    </div>
  );
}

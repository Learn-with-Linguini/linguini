import { useEffect, useId, useRef, useState } from "react";
import { trackAction } from "../lib/analytics";
import { Button } from "./ui";
import styles from "./CameraCapture.module.css";

type CameraCaptureProps = {
  onCapture: (file: File) => void;
  onClose: () => void;
};

function cameraError(error: unknown): string {
  const name = error instanceof Error ? error.name : "UnknownError";
  if (name === "NotAllowedError" || name === "SecurityError") return "Camera access was blocked. Allow camera access in your browser's site permissions, then try again. You can also upload a photo.";
  if (name === "NotFoundError") return "No camera was found. Connect a camera and try again, or upload a photo.";
  if (name === "NotReadableError" || name === "AbortError") return "Your camera couldn't start. Close other apps using it and try again, or upload a photo.";
  return "We couldn't open your camera. Try again, or upload a photo instead.";
}

export function CameraCapture({ onCapture, onClose }: CameraCaptureProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const active = useRef(false);
  const capturing = useRef(false);
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();

  const stopCamera = () => {
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
  };

  useEffect(() => {
    let cancelled = false;
    const preview = video.current;
    active.current = true;
    dialog.current?.showModal();
    trackAction("photo_camera_opened");
    const start = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("Camera access requires HTTPS or localhost and a supported browser. You can still upload a photo.");
        trackAction("photo_camera_failed", { reason: "unavailable" });
        return;
      }
      try {
        const media = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: "environment" } } });
        // Permission can be granted after the user has already closed the dialog.
        if (cancelled) { media.getTracks().forEach(track => track.stop()); return; }
        stream.current = media;
        if (preview) {
          preview.srcObject = media;
          await preview.play();
        }
      } catch (cause) {
        if (cancelled) return;
        stopCamera();
        setReady(false);
        setError(cameraError(cause));
        trackAction("photo_camera_failed", { reason: cause instanceof Error ? cause.name : "UnknownError" });
      }
    };
    void start();
    return () => {
      cancelled = true;
      active.current = false;
      stopCamera();
      if (preview) preview.srcObject = null;
    };
  }, []);

  const close = () => {
    active.current = false;
    stopCamera();
    trackAction("photo_camera_cancelled");
    onClose();
  };

  const capture = () => {
    const preview = video.current;
    if (!preview || !ready || capturing.current || !preview.videoWidth || !preview.videoHeight) return;
    capturing.current = true;
    setSaving(true);
    try {
      const canvas = document.createElement("canvas");
      // Bound file size and memory use on high-resolution mobile cameras.
      const scale = Math.min(1, 1920 / Math.max(preview.videoWidth, preview.videoHeight));
      canvas.width = Math.round(preview.videoWidth * scale);
      canvas.height = Math.round(preview.videoHeight * scale);
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Image capture unavailable");
      context.drawImage(preview, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(blob => {
        if (!active.current) return;
        if (!blob) { captureFailed(); return; }
        active.current = false;
        stopCamera();
        trackAction("photo_camera_captured");
        onCapture(new File([blob], `camera-${Date.now()}.jpg`, { type: "image/jpeg" }));
      }, "image/jpeg", 0.9);
    } catch { captureFailed(); }
  };

  const captureFailed = () => {
    capturing.current = false;
    setSaving(false);
    setError("We couldn't capture that photo. Try taking it again, or cancel and upload a photo.");
    trackAction("photo_camera_failed", { reason: "capture_failed" });
  };

  return <dialog ref={dialog} className={styles.dialog} aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); close(); }}>
    <div className="stack">
      <h2 id={titleId}>Take a photo</h2>
      <video ref={video} className={styles.preview} autoPlay muted playsInline aria-label="Live camera preview"
        onLoadedData={() => setReady(true)} onPlaying={() => setReady(true)} />
      {!ready && !error ? <p role="status">Waiting for your camera… Allow access when your browser asks.</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      <div className={styles.actions}>
        <Button disabled={!ready || saving} onClick={capture}>{saving ? "Capturing…" : "Take photo"}</Button>
        <Button variant="quiet" onClick={close}>Cancel</Button>
      </div>
    </div>
  </dialog>;
}

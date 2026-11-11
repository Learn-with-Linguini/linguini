import { InlineLoader } from "./LoadingScreen";
import { useEffect, useRef, useState } from "react";
import { uploadImage } from "../lib/api";
import type { ImageUploadAttempt, UploadedImage } from "../lib/api";
import { Button } from "./ui";
import { CameraIcon, UploadIcon } from "./icons";
import { friendlyError } from "../lib/queryKeys";
import { useAuth } from "../state/Auth";
import { trackAction } from "../lib/analytics";
import { CameraCapture } from "./CameraCapture";

type ImageUploadProps = {
  /** Optional heading inside the capture box, e.g. "Add a photo to the room". */
  label?: string;
  onUploaded: (image: UploadedImage) => void;
  cameraEnabled?: boolean;
  disabled?: boolean;
  onBusyChange?: (busy: boolean) => void;
};

/** Phones and tablets have a touch screen as their main input, and a far better camera app of their own. */
const usesDeviceCamera = () => window.matchMedia?.("(pointer: coarse)").matches ?? false;

export function ImageUpload(props: ImageUploadProps) {
  const { session } = useAuth();
  return <ImageUploadForAccount key={session?.user.id ?? "demo"} {...props} />;
}

function ImageUploadForAccount({ onUploaded, cameraEnabled = true, disabled = false, onBusyChange, label }: ImageUploadProps) {
  const fileInput = useRef<HTMLInputElement>(null);
  const deviceCameraInput = useRef<HTMLInputElement>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const busyRef = useRef(false);
  const mounted = useRef(true);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState<ImageUploadAttempt | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; onBusyChange?.(false); };
  }, [onBusyChange]);
  const select = async (file: File | undefined, source: "camera" | "userUpload", previous?: ImageUploadAttempt) => {
    if (!file || busyRef.current) return;
    const attempt = previous ?? { file, source, isCurrent: () => mounted.current };
    busyRef.current = true;
    setBusy(true);
    onBusyChange?.(true);
    setError(null);
    setRetry(null);
    try {
      const image = await uploadImage(file, source, setPhase, attempt);
      if (mounted.current) onUploaded(image);
    }
    catch (e) {
      if (mounted.current) {
        setError(friendlyError(e));
        if (attempt.uploaded) setRetry(attempt);
      }
    }
    finally {
      busyRef.current = false;
      if (mounted.current) { setBusy(false); setPhase(""); onBusyChange?.(false); }
    }
  };
  const openCamera = () => {
    setError(null);
    if (usesDeviceCamera()) {
      trackAction("photo_camera_opened", { camera: "device" });
      deviceCameraInput.current?.click();
    } else setCameraOpen(true);
  };
  // Every photo picker shares one layout: a dashed capture box with Click (camera) and Upload.
  return <div className="dashed-capture">
    <span style={{ color: "var(--teal-dark)" }}><CameraIcon size={44} /></span>
    {label ? <strong>{label}</strong> : null}
    <div className="stack-2">
      <input ref={fileInput} type="file" hidden accept="image/jpeg,image/png,image/webp"
        onChange={(e) => { void select(e.target.files?.[0], "userUpload"); e.target.value = ""; }} />
      <input ref={deviceCameraInput} type="file" hidden accept="image/jpeg,image/png,image/webp" capture="environment"
        data-testid="device-camera"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) trackAction("photo_camera_captured", { camera: "device" });
          void select(file, "camera");
          e.target.value = "";
        }} />
      {cameraOpen && cameraEnabled && !disabled && !busy ? <CameraCapture
        onClose={() => setCameraOpen(false)}
        onCapture={file => { setCameraOpen(false); void select(file, "camera"); }} /> : null}
      <div className="row">
        <Button disabled={disabled || busy || !cameraEnabled} onClick={openCamera}><CameraIcon size={18} /> Click</Button>
        <Button variant="secondary" disabled={disabled || busy} onClick={() => fileInput.current?.click()}><UploadIcon size={18} /> Upload</Button>
      </div>
      {busy ? <InlineLoader label={phase || "Preparing upload"} /> : null}
      {error ? <p role="alert">{error}</p> : null}
      {retry ? <Button variant="secondary" disabled={disabled || busy} onClick={() => {
        trackAction("photo_upload_retried", { source: retry.source });
        void select(retry.file, retry.source, retry);
      }}>Retry upload</Button> : null}
    </div>
  </div>;
}

import { useRef, useState } from "react";
import { uploadImage } from "../lib/api";
import type { UploadedImage } from "../lib/api";
import { Button } from "./ui";
import { CameraIcon, UploadIcon } from "./icons";
import { friendlyError } from "../lib/queryKeys";

export function ImageUpload({ onUploaded, cameraEnabled = true, disabled = false, onBusyChange, compact = false, dropzoneLabel }: {
  compact?: boolean;
  dropzoneLabel?: string;
  onUploaded: (image: UploadedImage) => void;
  cameraEnabled?: boolean;
  disabled?: boolean;
  onBusyChange?: (busy: boolean) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const cameraInput = useRef<HTMLInputElement>(null);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState("");
  const [error, setError] = useState<string | null>(null);
  const select = async (file: File | undefined, source: "camera" | "userUpload") => {
    if (!file || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    onBusyChange?.(true);
    setError(null);
    try { onUploaded(await uploadImage(file, source, setPhase)); }
    catch (e) { setError(friendlyError(e)); }
    finally { busyRef.current = false; setBusy(false); setPhase(""); onBusyChange?.(false); }
  };
  return <div className="stack-2">
    <input ref={fileInput} type="file" hidden accept="image/jpeg,image/png,image/webp"
      onChange={(e) => { void select(e.target.files?.[0], "userUpload"); e.target.value = ""; }} />
    <input ref={cameraInput} type="file" hidden accept="image/jpeg,image/png,image/webp" capture="environment"
      onChange={(e) => { void select(e.target.files?.[0], "camera"); e.target.value = ""; }} />
    {dropzoneLabel ? (
      <button type="button" className="dashed-capture journal-upload-dropzone" disabled={disabled || busy}
        onClick={() => fileInput.current?.click()}>
        <span style={{ color: "var(--teal-dark)" }}><UploadIcon size={40} /></span>
        <strong>{dropzoneLabel}</strong>
        <span className="small muted">Choose from your device</span>
      </button>
    ) : <>
      <div className="row">
        <Button disabled={disabled || busy || !cameraEnabled} onClick={() => cameraInput.current?.click()}><CameraIcon size={18} /> {compact ? "Click" : "Open camera"}</Button>
        <Button variant="secondary" disabled={disabled || busy} onClick={() => fileInput.current?.click()}><UploadIcon size={18} /> Upload</Button>
      </div>
      {!compact ? <p className="small muted">JPEG, PNG or WebP, up to 10 MB</p> : null}
    </>}
    {busy ? <p role="status">{phase}</p> : null}
    {error ? <p role="alert">{error}</p> : null}
  </div>;
}

import { useEffect, useState } from "react";
import type { KeyboardEvent, MouseEvent } from "react";
import { getChatPhoto } from "../../lib/friendChats";
import type { ChatObject, ChatPoint } from "../../lib/friendChats";
import { Button } from "../ui";
import { InlineLoader } from "../LoadingScreen";

const clamp = (value: number) => Math.max(0, Math.min(1, value));
export function photoPoint(event: { clientX: number; clientY: number }, bounds: Pick<DOMRect, "left" | "top" | "width" | "height">): ChatPoint | null {
  return bounds.width && bounds.height ? { x: clamp((event.clientX - bounds.left) / bounds.width), y: clamp((event.clientY - bounds.top) / bounds.height) } : null;
}

export function ChatPhoto({ chatId, roundId, objects = [], selected, onObject, onPoint, disabled = false, crop, label = "Shared I-Spy photo" }: {
  chatId: string; roundId: string; objects?: ChatObject[]; selected?: ChatPoint | null;
  onObject?: (object: ChatObject) => void; onPoint?: (point: ChatPoint) => void; disabled?: boolean;
  crop?: ChatObject | null; label?: string;
}) {
  const [retry, setRetry] = useState(0);
  const [image, setImage] = useState<{ key: string; url: string | null; failed: boolean } | null>(null);
  const [cursor, setCursor] = useState<ChatPoint>({ x: .5, y: .5 });
  const key = `${chatId}:${roundId}:${retry}`;
  const cropWidth = Math.max(.02, crop?.width ?? .3);
  const cropHeight = Math.max(.02, crop?.height ?? .3);
  const current = image?.key === key ? image : null;
  useEffect(() => {
    const controller = new AbortController(); let url: string | null = null;
    void getChatPhoto(chatId, roundId, controller.signal).then(blob => {
      if (controller.signal.aborted) return;
      url = URL.createObjectURL(blob); setImage({ key, url, failed: false });
    }).catch(() => { if (!controller.signal.aborted) setImage({ key, url: null, failed: true }); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [chatId, roundId, key]);
  const choose = (event: MouseEvent<HTMLDivElement>) => {
    if (!onPoint || disabled || !current?.url) return;
    const point = photoPoint(event, event.currentTarget.getBoundingClientRect());
    if (point) { setCursor(point); onPoint(point); }
  };
  const keyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!onPoint || disabled || !current?.url) return;
    const direction = { ArrowLeft: [-.02, 0], ArrowRight: [.02, 0], ArrowUp: [0, -.02], ArrowDown: [0, .02] }[event.key];
    if (direction) {
      event.preventDefault();
      const next = { x: clamp((selected ?? cursor).x + direction[0]), y: clamp((selected ?? cursor).y + direction[1]) };
      setCursor(next); onPoint(next);
    } else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onPoint(selected ?? cursor); }
  };
  if (current?.failed) return <div className="friend-photo__placeholder"><p role="alert">We couldn’t load this photo.</p>
    <Button variant="secondary" onClick={() => setRetry(value => value + 1)}>Reload photo</Button></div>;
  if (!current?.url) return <div className="friend-photo__placeholder"><InlineLoader compact label="Opening photo…" /></div>;
  return <div className={`friend-photo${crop ? " friend-photo--crop" : ""}`}>
    <div className={`friend-photo__image${onPoint ? " friend-photo__image--selectable" : ""}`} role={onPoint ? "button" : undefined}
      tabIndex={onPoint && !disabled ? 0 : undefined} aria-label={onPoint ? `${label}. Tap a location, or use arrow keys to move your selection and Enter to select.` : undefined}
      aria-disabled={onPoint ? disabled : undefined} onClick={choose} onKeyDown={keyboard}>
      <img src={current.url} alt={label} draggable={false} onError={() => setImage({ key, url: null, failed: true })}
        style={crop ? { width: `${100 / cropWidth}%`, height: `${100 / cropHeight}%`, maxWidth: "none",
          left: `${50 - crop.x * 100 / cropWidth}%`, top: `${50 - crop.y * 100 / cropHeight}%` } : undefined} />
      {!crop ? objects.map(object => onObject && !onPoint ? <button type="button" key={object.key} className="friend-photo__object"
        style={{ left: `${object.x * 100}%`, top: `${object.y * 100}%` }} disabled={disabled}
        aria-label={`Choose ${object.translation || object.label}`} onClick={() => onObject(object)}><span aria-hidden="true" /></button> :
        <span key={object.key} className="friend-photo__object" aria-hidden="true" style={{ left: `${object.x * 100}%`, top: `${object.y * 100}%` }} />) : null}
      {!crop && selected ? <span className="friend-photo__selection" aria-hidden="true" style={{ left: `${selected.x * 100}%`, top: `${selected.y * 100}%` }} /> : null}
    </div>
    {onPoint ? <p className="small muted">Tap the photo to choose. With a keyboard, focus the photo and use arrow keys to move.</p> : null}
  </div>;
}

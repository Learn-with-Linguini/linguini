"use client";

import { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import styles from "./ShareBar.module.css";

type ShareBarProps = {
  /** Absolute URL to share. */
  url: string;
  /** Short message that accompanies the link on networks that support it. */
  text: string;
  /** Visible label for the group. Defaults to a visually hidden "Share". */
  label?: string;
};

type Network = {
  id: string;
  name: string;
  href: (url: string, text: string) => string;
  Glyph: () => React.JSX.Element;
};

const enc = encodeURIComponent;

/* Authored 24px glyphs: 1.8 stroke, round joins, currentColor, filled only where the mark needs mass. */
const svgProps = {
  width: 22,
  height: 22,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
  focusable: false,
} as const;

function XGlyph() {
  return (
    <svg {...svgProps}>
      <path d="M4.5 4.5h4l11 15h-4z" />
      <path d="M19 4.5l-5.6 6.2M10.6 13.4 5 19.5" />
    </svg>
  );
}

function WhatsAppGlyph() {
  return (
    <svg {...svgProps}>
      <path d="M12 3.6a8.4 8.4 0 0 0-7.2 12.7L3.6 20.4l4.2-1.1A8.4 8.4 0 1 0 12 3.6z" />
      <path
        d="M9.2 8.1c.3-.3.8-.3 1 .1l.8 1.5c.2.3.1.7-.2 1l-.5.4c.5 1.2 1.4 2.1 2.6 2.6l.4-.5c.3-.3.7-.4 1-.2l1.5.8c.4.2.4.7.1 1-.5.6-1.3.9-2.1.7-2.5-.6-4.4-2.5-5-5-.2-.8.1-1.6.6-2.1z"
        fill="currentColor"
        stroke="none"
      />
    </svg>
  );
}

function TelegramGlyph() {
  return (
    <svg {...svgProps}>
      <path d="M20.6 4.2 3.4 10.9c-.6.2-.6 1.1 0 1.3l4.3 1.5 1.7 5.4c.2.5.8.6 1.1.2l2.4-2.6 4.3 3.2c.5.4 1.2.1 1.3-.5L21.8 5.4c.2-.8-.5-1.5-1.2-1.2z" />
      <path d="M7.7 13.7 17.2 7.6l-6.6 6.5-.6 4.9" />
    </svg>
  );
}

function LinkedInGlyph() {
  return (
    <svg {...svgProps}>
      <rect x="3.4" y="3.4" width="17.2" height="17.2" rx="3.6" />
      <circle cx="8.1" cy="8.1" r="1.25" fill="currentColor" stroke="none" />
      <path d="M8.1 11v5.9M11.9 16.9V11M11.9 13.8c0-1.8 1-2.8 2.4-2.8s2.2 1 2.2 2.8v3.1" />
    </svg>
  );
}

function FacebookGlyph() {
  return (
    <svg {...svgProps}>
      <circle cx="12" cy="12" r="8.6" />
      <path d="M15 7.8h-1.4c-1.4 0-2.2.8-2.2 2.2v10.6M9.2 13h5.2" />
    </svg>
  );
}

function ShareGlyph() {
  return (
    <svg {...svgProps}>
      <path d="M12 14.5V3.8M8.2 7.4 12 3.6l3.8 3.8" />
      <path d="M8 10.5H6.6c-.9 0-1.6.7-1.6 1.6v6.5c0 .9.7 1.6 1.6 1.6h10.8c.9 0 1.6-.7 1.6-1.6v-6.5c0-.9-.7-1.6-1.6-1.6H16" />
    </svg>
  );
}

function LinkGlyph() {
  return (
    <svg {...svgProps}>
      <path d="M10.2 13.8a3.6 3.6 0 0 0 5.1 0l3.1-3.1a3.6 3.6 0 0 0-5.1-5.1l-1.2 1.2" />
      <path d="M13.8 10.2a3.6 3.6 0 0 0-5.1 0l-3.1 3.1a3.6 3.6 0 0 0 5.1 5.1l1.2-1.2" />
    </svg>
  );
}

function CheckGlyph() {
  return (
    <svg {...svgProps} strokeWidth={2.2}>
      <path d="M5 12.5l4.4 4.4L19 7.3" />
    </svg>
  );
}

const networks: Network[] = [
  {
    id: "x",
    name: "X",
    href: (url, text) => `https://x.com/intent/post?text=${enc(text)}&url=${enc(url)}`,
    Glyph: XGlyph,
  },
  {
    id: "whatsapp",
    name: "WhatsApp",
    href: (url, text) => `https://wa.me/?text=${enc(`${text} ${url}`)}`,
    Glyph: WhatsAppGlyph,
  },
  {
    id: "telegram",
    name: "Telegram",
    href: (url, text) => `https://t.me/share/url?url=${enc(url)}&text=${enc(text)}`,
    Glyph: TelegramGlyph,
  },
  {
    id: "linkedin",
    name: "LinkedIn",
    href: (url) => `https://www.linkedin.com/sharing/share-offsite/?url=${enc(url)}`,
    Glyph: LinkedInGlyph,
  },
  {
    id: "facebook",
    name: "Facebook",
    href: (url) => `https://www.facebook.com/sharer/sharer.php?u=${enc(url)}`,
    Glyph: FacebookGlyph,
  },
];

const noopSubscribe = () => () => {};
const detectNativeShare = () => typeof navigator !== "undefined" && typeof navigator.share === "function";
// The server (and the hydration pass) never renders the native button, so markup always matches.
const serverSnapshot = () => false;

async function copyText(value: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Fall through to the legacy path (e.g. insecure context or denied permission).
  }
  try {
    const field = document.createElement("textarea");
    field.value = value;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    const ok = document.execCommand("copy");
    field.remove();
    return ok;
  } catch {
    return false;
  }
}

export function ShareBar({ url, text, label }: ShareBarProps) {
  const labelId = useId();
  const canNativeShare = useSyncExternalStore(noopSubscribe, detectNativeShare, serverSnapshot);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    },
    [],
  );

  const onCopy = useCallback(async () => {
    const ok = await copyText(url);
    setCopyState(ok ? "copied" : "failed");
    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => setCopyState("idle"), 2400);
  }, [url]);

  const onNativeShare = useCallback(async () => {
    try {
      await navigator.share({ title: "Linguini", text, url });
    } catch {
      // Dismissing the sheet rejects with AbortError; nothing to do.
    }
  }, [text, url]);

  const copyLabel = copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy link";

  return (
    <div className={styles.bar}>
      <span id={labelId} className={label ? styles.label : "visually-hidden"}>
        {label ?? "Share"}
      </span>
      <ul className={styles.list} aria-labelledby={labelId}>
        {canNativeShare ? (
          <li>
            <button type="button" className={`${styles.button} ${styles.pill}`} onClick={onNativeShare}>
              <ShareGlyph />
              <span>Share…</span>
            </button>
          </li>
        ) : null}
        {networks.map(({ id, name, href, Glyph }) => (
          <li key={id}>
            <a
              className={styles.button}
              href={href(url, text)}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`Share on ${name} (opens in a new tab)`}
              title={`Share on ${name}`}
            >
              <Glyph />
            </a>
          </li>
        ))}
        <li>
          <button
            type="button"
            className={`${styles.button} ${styles.pill}`}
            data-state={copyState}
            onClick={onCopy}
          >
            {copyState === "copied" ? <CheckGlyph /> : <LinkGlyph />}
            <span>{copyLabel}</span>
          </button>
        </li>
      </ul>
      <output className="visually-hidden" aria-live="polite">
        {copyState === "copied" ? "Link copied to clipboard" : copyState === "failed" ? "Could not copy the link" : ""}
      </output>
    </div>
  );
}
export default ShareBar;

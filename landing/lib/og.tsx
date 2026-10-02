/* eslint-disable @next/next/no-img-element -- Satori renders plain <img>, not next/image. */
/**
 * Shared helpers for the Satori-rendered social images (`next/og`).
 * Node.js runtime only: assets are read from disk relative to the project root.
 *
 * Satori rules worth remembering when editing these pieces:
 * - flexbox only; every element with more than one child needs `display: "flex"`.
 * - images must be PNG or JPEG (no WebP) and are embedded as data URIs.
 */
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { CSSProperties, ReactNode } from "react";
import { getPhoto, photos, type Photo } from "@/lib/photos";

export const OG_SIZE = { width: 1200, height: 630 } as const;

export const ogColors = {
  butter: "#fbf8ef",
  cream: "#fff2d6",
  paper: "#fffdf8",
  tomato: "#ef5b32",
  tomatoPressed: "#c84725",
  tomatoInk: "#b8401f",
  pasta: "#f9ae22",
  pastaSoft: "#fde6b4",
  teal: "#2e9c99",
  tealDark: "#21716f",
  ink: "#263238",
  muted: "#5d6c70",
  line: "#e4dccb",
} as const;

export const ogFont = {
  display: "Baloo 2",
  ui: "Nunito Sans",
} as const;

type OgFont = {
  name: string;
  data: ArrayBuffer;
  weight: 700 | 800;
  style: "normal";
};

const assetCache = new Map<string, Promise<unknown>>();

function cached<T>(key: string, load: () => Promise<T>): Promise<T> {
  let hit = assetCache.get(key) as Promise<T> | undefined;
  if (!hit) {
    hit = load();
    // Don't keep a rejected promise around; the next request retries.
    hit.catch(() => assetCache.delete(key));
    assetCache.set(key, hit);
  }
  return hit;
}

function fromRoot(relative: string): string {
  // Callers only read assets/, public/brand, public/pasta and public/photos; those are traced
  // for /og and /opengraph-image via `outputFileTracingIncludes` in next.config.ts.
  return path.join(/*turbopackIgnore: true*/ process.cwd(), relative);
}

async function readArrayBuffer(relative: string): Promise<ArrayBuffer> {
  const buf = await readFile(fromRoot(relative));
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
}

/** Baloo 2 ExtraBold for headings, Nunito Sans Bold for UI text. */
export function loadOgFonts(): Promise<OgFont[]> {
  return cached("fonts", async () => {
    const [baloo, nunito] = await Promise.all([
      readArrayBuffer("assets/fonts/Baloo2-ExtraBold.ttf"),
      readArrayBuffer("assets/fonts/NunitoSans-Bold.ttf"),
    ]);
    return [
      { name: ogFont.display, data: baloo, weight: 800, style: "normal" },
      { name: ogFont.ui, data: nunito, weight: 700, style: "normal" },
    ];
  });
}

const MIME: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
};

/** Read a PNG/JPEG (path relative to the project root, e.g. `public/brand/x.png`) as a data URI. */
export function loadImage(relative: string): Promise<string> {
  const ext = path.extname(relative).toLowerCase();
  const mime = MIME[ext];
  if (!mime) {
    return Promise.reject(new Error(`OG images support PNG/JPEG only, got "${relative}"`));
  }
  return cached(`img:${relative}`, async () => {
    const buf = await readFile(fromRoot(relative));
    return `data:${mime};base64,${buf.toString("base64")}`;
  });
}

export type PastaShape = "farfalle" | "fusilli" | "macaroni" | "penne";

const PASTA_SIZE: Record<PastaShape, { w: number; h: number }> = {
  farfalle: { w: 360, h: 281 },
  fusilli: { w: 276, h: 360 },
  macaroni: { w: 360, h: 333 },
  penne: { w: 360, h: 341 },
};

export function loadPasta(shape: PastaShape): Promise<string> {
  return loadImage(`public/pasta/${shape}.png`);
}

export function loadWordmark(): Promise<string> {
  return loadImage("public/brand/linguini-wordmark.png");
}

export function loadMascot(): Promise<string> {
  return loadImage("public/brand/linguini-logo.png");
}

/** Cache headers for images whose bytes are a pure function of the URL. */
export const IMMUTABLE_IMAGE_HEADERS = {
  "Cache-Control": "public, immutable, no-transform, max-age=31536000",
} as const;

/* ------------------------------------------------------------------ */
/* Layout pieces                                                       */
/* ------------------------------------------------------------------ */

/**
 * The orange wordmark, cropped to its ink (the source PNG is 450×150 with
 * transparent padding; the lettering sits at x 58, y 24, 344×110).
 */
export function Wordmark({ src, width }: { src: string; width: number }) {
  const scale = width / 344;
  return (
    <div
      style={{
        display: "flex",
        position: "relative",
        width,
        height: Math.round(110 * scale),
        overflow: "hidden",
      }}
    >
      <img
        src={src}
        alt=""
        width={Math.round(450 * scale)}
        height={Math.round(150 * scale)}
        style={{
          position: "absolute",
          left: Math.round(-58 * scale),
          top: Math.round(-24 * scale),
          width: Math.round(450 * scale),
          height: Math.round(150 * scale),
        }}
      />
    </div>
  );
}

type PrintProps = {
  src: string;
  width: number;
  height: number;
  /** Degrees. */
  rotate?: number;
  /** White border thickness; the bottom edge gets a little extra like an instant print. */
  border?: number;
  style?: CSSProperties;
  /** Overlays positioned absolutely relative to the print (e.g. a word tag); they may overhang the edge. */
  children?: ReactNode;
};

/** A photo printed on paper: white border, soft shadow, slight tilt. */
export function Print({ src, width, height, rotate = 0, border = 14, style, children }: PrintProps) {
  const photoW = width - border * 2;
  const photoH = height - border * 2 - Math.round(border * 1.4);
  return (
    <div
      style={{
        display: "flex",
        position: "absolute",
        width,
        height,
        padding: border,
        paddingBottom: border + Math.round(border * 1.4),
        background: ogColors.paper,
        borderRadius: 6,
        boxShadow: "0 22px 44px -14px rgba(62, 45, 18, 0.42), 0 4px 12px rgba(62, 45, 18, 0.14)",
        transform: `rotate(${rotate}deg)`,
        ...style,
      }}
    >
      <div
        style={{
          display: "flex",
          position: "relative",
          width: photoW,
          height: photoH,
          overflow: "hidden",
          borderRadius: 3,
          background: ogColors.cream,
        }}
      >
        <img
          src={src}
          alt=""
          width={photoW}
          height={photoH}
          style={{ width: photoW, height: photoH, objectFit: "cover" }}
        />
      </div>
      {children}
    </div>
  );
}

/** Photo area inside a `Print` of the given outer size (matches its padding). */
export function printPhotoArea(width: number, height: number, border = 14) {
  return {
    x: border,
    y: border,
    w: width - border * 2,
    h: height - border * 2 - Math.round(border * 1.4),
  };
}

/**
 * Where a point given as percentages of the source image (0–100, as in
 * credits.json) lands inside a box the image fills with `object-fit: cover`.
 */
export function coverPoint(
  source: { width: number; height: number },
  box: { w: number; h: number },
  point: { x: number; y: number },
) {
  const scale = Math.max(box.w / source.width, box.h / source.height);
  const offsetX = (box.w - source.width * scale) / 2;
  const offsetY = (box.h - source.height * scale) / 2;
  return {
    x: (point.x / 100) * source.width * scale + offsetX,
    y: (point.y / 100) * source.height * scale + offsetY,
  };
}

/** A strip of translucent tape, as if the print were stuck into a journal. */
export function Tape({ width = 120, rotate = -4, style }: { width?: number; rotate?: number; style?: CSSProperties }) {
  return (
    <div
      style={{
        display: "flex",
        position: "absolute",
        width,
        height: 34,
        background: "rgba(249, 174, 34, 0.55)",
        borderLeft: "2px dashed rgba(255, 253, 248, 0.6)",
        borderRight: "2px dashed rgba(255, 253, 248, 0.6)",
        transform: `rotate(${rotate}deg)`,
        ...style,
      }}
    />
  );
}

type WordTagProps = {
  /** Word in the target language, with its article, e.g. "la mesa". */
  target: string;
  /** English meaning, e.g. "the table". */
  meaning?: string;
  style?: CSSProperties;
  size?: number;
};

/** The in-app label that pins a learned word to an object in the photo. */
export function WordTag({ target, meaning, style, size = 26 }: WordTagProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: Math.round(size * 0.4),
        padding: `${Math.round(size * 0.34)}px ${Math.round(size * 0.66)}px ${Math.round(size * 0.34)}px ${Math.round(size * 0.5)}px`,
        background: ogColors.paper,
        borderRadius: 999,
        border: `2px solid ${ogColors.ink}`,
        boxShadow: `0 4px 0 ${ogColors.ink}`,
        ...style,
      }}
    >
      <div
        style={{
          display: "flex",
          width: Math.round(size * 0.46),
          height: Math.round(size * 0.46),
          borderRadius: 999,
          background: ogColors.tomato,
        }}
      />
      <div
        style={{
          display: "flex",
          fontFamily: ogFont.display,
          fontWeight: 800,
          fontSize: size,
          lineHeight: 1,
          color: ogColors.ink,
          paddingTop: Math.round(size * 0.12),
        }}
      >
        {target}
      </div>
      {meaning ? (
        <div
          style={{
            display: "flex",
            fontFamily: ogFont.ui,
            fontWeight: 700,
            fontSize: Math.round(size * 0.78),
            lineHeight: 1,
            color: ogColors.muted,
          }}
        >
          {`· ${meaning}`}
        </div>
      ) : null}
    </div>
  );
}

type PastaProps = {
  src: string;
  shape: PastaShape;
  /** Rendered width in px; height follows the source aspect ratio. */
  width: number;
  rotate?: number;
  style?: CSSProperties;
};

export function Pasta({ src, shape, width, rotate = 0, style }: PastaProps) {
  const { w, h } = PASTA_SIZE[shape];
  const height = Math.round((width * h) / w);
  return (
    <img
      src={src}
      alt=""
      width={width}
      height={height}
      style={{ position: "absolute", width, height, transform: `rotate(${rotate}deg)`, ...style }}
    />
  );
}

/* ------------------------------------------------------------------ */
/* Journal share card: query parsing shared by /og and /share          */
/* ------------------------------------------------------------------ */

export type JournalLang = "es" | "fr";

export const LANGUAGE_NAME: Record<JournalLang, string> = {
  es: "Spanish",
  fr: "French",
};

export const JOURNAL_LIMITS = {
  words: 5,
  wordLength: 28,
  titleLength: 60,
} as const;

/** Photo used when `photo` is missing or unknown. */
export const DEFAULT_JOURNAL_PHOTO: Photo = getPhoto("cafe-interior") ?? photos[0]!;

export type JournalCard = {
  photo: Photo;
  lang: JournalLang;
  words: string[];
  title?: string;
};

type RawParam = string | string[] | null | undefined;

function first(value: RawParam): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

// Control/format characters and bidi overrides, plus emoji (Satori would fetch them remotely).
const UNSAFE_CHARS = /[\p{Cc}\p{Cf}\p{Co}\p{Cs}\p{Extended_Pictographic}️]/gu;

/**
 * Normalise user text: strip control/format chars and emoji, collapse spaces, and clamp to
 * `max` code points. Over-long text is cut at a word boundary where possible and ends in "…".
 */
export function cleanText(value: string, max: number): string {
  const chars = Array.from(value.normalize("NFC").replace(UNSAFE_CHARS, "").replace(/\s+/g, " ").trim());
  if (chars.length <= max) return chars.join("");
  const cut = chars.slice(0, max - 1).join("");
  const lastSpace = cut.lastIndexOf(" ");
  const head = lastSpace >= Math.floor(max * 0.6) ? cut.slice(0, lastSpace) : cut;
  return `${head.replace(/[\s.,;:·–—-]+$/u, "")}…`;
}

/** Parse and sanitise `/og` / `/share` query params. Never throws. */
export function parseJournalCard(params: {
  photo?: RawParam;
  lang?: RawParam;
  words?: RawParam;
  title?: RawParam;
}): JournalCard {
  const photo = getPhoto(first(params.photo).trim().slice(0, 80)) ?? DEFAULT_JOURNAL_PHOTO;
  const lang: JournalLang = first(params.lang).trim().toLowerCase() === "fr" ? "fr" : "es";

  const seen = new Set<string>();
  const words: string[] = [];
  for (const part of first(params.words).slice(0, 600).split(",")) {
    const word = cleanText(part, JOURNAL_LIMITS.wordLength);
    const key = word.toLocaleLowerCase();
    if (!word || seen.has(key)) continue;
    seen.add(key);
    words.push(word);
    if (words.length === JOURNAL_LIMITS.words) break;
  }

  const title = cleanText(first(params.title).slice(0, 400), JOURNAL_LIMITS.titleLength) || undefined;
  return { photo, lang, words, title };
}

/** Canonical query string for a card (stable key order, so equal cards share one cache entry). */
export function journalQuery(card: JournalCard): string {
  const query = new URLSearchParams();
  query.set("photo", card.photo.stem);
  query.set("lang", card.lang);
  if (card.words.length > 0) query.set("words", card.words.join(","));
  if (card.title) query.set("title", card.title);
  return query.toString();
}

/** Headline shown on the card and used as the share page title. */
export function journalTitle(card: JournalCard): string {
  if (card.title) return card.title;
  const n = card.words.length;
  if (n === 0) return `A day in ${LANGUAGE_NAME[card.lang]}`;
  return n === 1 ? "The word I learned today" : `${n} words I learned today`;
}

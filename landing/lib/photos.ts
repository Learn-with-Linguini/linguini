import credits from "@/public/photos/credits.json";

/** A labelled object in a photo; `x`/`y` are percentages (0–100) of the frame width/height. */
export type PhotoObject = {
  en: string;
  x: number;
  y: number;
};

type PhotoCredit = {
  file: string;
  width: number;
  height: number;
  alt: string;
  subject: string;
  sourceRepo: string;
  sourcePath: string;
  commitDate: string;
  author: string;
  origin: string;
  license: string;
  objects: PhotoObject[];
};

export type Photo = PhotoCredit & {
  /** File name without extension; the stable id used in URLs (`/og?photo=<stem>`). */
  stem: string;
  /** Public URL path, e.g. `/photos/cafe.jpg`. */
  src: string;
};

function stemOf(file: string): string {
  return file.replace(/\.[^.]+$/, "");
}

export const photos: readonly Photo[] = (credits as PhotoCredit[]).map((credit) => ({
  ...credit,
  stem: stemOf(credit.file),
  src: `/photos/${credit.file}`,
}));

const byStem = new Map(photos.map((photo) => [photo.stem, photo]));

export function getPhoto(stem: string): Photo | undefined {
  return byStem.get(stem);
}

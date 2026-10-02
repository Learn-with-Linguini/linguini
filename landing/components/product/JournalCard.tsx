import Image from "next/image";
import type { Lang } from "@/data/types";
import { stripArticle } from "@/lib/words";
import styles from "./product.module.css";

export type JournalCardProps = {
  photos: { src: string; alt: string }[];
  title: string;
  body: string;
  date: string;
  lang?: Lang;
  /** Words to highlight inside the body. */
  highlight?: string[];
  className?: string;
  headingLevel?: "h3" | "h4" | "p";
};

function highlightWords(body: string, words: string[]) {
  if (!words.length) return body;
  const escaped = words
    .map(stripArticle)
    .filter(Boolean)
    .map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(?<!\\p{L})((?:${escaped.join("|")})(?:e?s)?)(?!\\p{L})`, "giu");
  return body.split(pattern).map((part, index) =>
    index % 2 === 1 ? <mark key={index} className={styles.hl}>{part}</mark> : part,
  );
}

export function JournalCard({ photos, title, body, date, lang, highlight = [], className = "", headingLevel = "h3" }: JournalCardProps) {
  const Heading = headingLevel;
  const [main, ...rest] = photos;
  const side = rest.slice(0, 2);
  const extra = photos.length - 3;
  return (
    <article className={`${styles.journalCard} ${className}`}>
      <div
        className={`${styles.journalPhotos} ${side.length === 0 ? styles.journalPhotosSingle : side.length === 1 ? styles.journalPhotosPair : ""}`}
      >
        <div className={styles.journalMain}>
          <Image src={main.src} alt={main.alt} fill sizes="(max-width: 700px) 70vw, 280px" className={styles.photoImg} />
        </div>
        {side.map((photo, index) => (
          <div key={photo.src} className={styles.journalSide}>
            <Image src={photo.src} alt={photo.alt} fill sizes="140px" className={styles.photoImg} />
            {index === 1 && extra > 0 ? <span className={styles.journalMore}>+{extra}</span> : null}
          </div>
        ))}
      </div>
      <div className={styles.journalText}>
        <Heading className={styles.journalTitle}>{title}</Heading>
        <p className={styles.journalBody} lang={lang}>{highlightWords(body, highlight)}</p>
      </div>
      <p className={styles.journalDate}>{date}</p>
    </article>
  );
}

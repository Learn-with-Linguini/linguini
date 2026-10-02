import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { photos } from "@/lib/photos";
import { pageMetadata } from "@/lib/seo";
import styles from "./credits.module.css";

export const metadata: Metadata = pageMetadata({
  title: "Photo credits",
  description: "Where every photo on the Linguini site comes from: photographer, source repository, commit date and licence.",
  path: "/credits",
});

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

function formatDate(value: string): string {
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? value : dateFormat.format(date);
}

function repoUrl(repo: string): string {
  return /^https?:\/\//.test(repo) ? repo : `https://github.com/${repo}`;
}

export default function CreditsPage() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.brand} aria-label="Linguini home">
          <Image src="/brand/linguini-wordmark.png" alt="" width={450} height={150} priority className={styles.wordmark} />
        </Link>
      </header>

      <div className={styles.intro}>
        <h1 className={styles.title}>Photo credits</h1>
        <p className={styles.lede}>
          The scenes on this site are real photos. Here is where each one comes from, who took it and the licence as far as
          we could trace it.
        </p>
      </div>

      <ol className={styles.list}>
        {photos.map((photo) => (
          <li key={photo.stem} id={photo.stem} className={styles.item}>
            <div className={styles.thumb}>
              <Image
                src={photo.src}
                alt={photo.alt}
                fill
                sizes="(min-width: 720px) 240px, 100vw"
                className={styles.thumbImg}
              />
            </div>
            <div className={styles.body}>
              <h2 className={styles.subject}>{photo.subject}</h2>
              <dl className={styles.facts}>
                <div>
                  <dt>Photographer</dt>
                  <dd>{photo.author === "unknown" ? "Not credited" : photo.author}</dd>
                </div>
                <div>
                  <dt>Origin</dt>
                  <dd>{photo.origin}</dd>
                </div>
                <div>
                  <dt>Licence</dt>
                  <dd>{photo.license}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>
                    <a href={repoUrl(photo.sourceRepo)} target="_blank" rel="noopener noreferrer">
                      {photo.sourceRepo}
                    </a>
                    <code className={styles.path}>{photo.sourcePath}</code>
                  </dd>
                </div>
                <div>
                  <dt>Committed</dt>
                  <dd>
                    <time dateTime={photo.commitDate}>{formatDate(photo.commitDate)}</time>
                  </dd>
                </div>
              </dl>
            </div>
          </li>
        ))}
      </ol>

      <p className={styles.back}>
        <Link href="/" className="btn-quiet">
          <span aria-hidden="true">←</span> Back to Linguini
        </Link>
      </p>
    </main>
  );
}

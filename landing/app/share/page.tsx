import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ShareBar } from "@/components/ShareBar";
import { LANGUAGE_NAME, OG_SIZE, journalQuery, journalTitle, parseJournalCard, type JournalCard } from "@/lib/og";
import { appLinks, site } from "@/lib/site";
import styles from "./share.module.css";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

async function readCard(searchParams: SearchParams): Promise<JournalCard> {
  const params = await searchParams;
  return parseJournalCard({
    photo: params.photo,
    lang: params.lang,
    words: params.words,
    title: params.title,
  });
}

function describe(card: JournalCard): string {
  const language = LANGUAGE_NAME[card.lang];
  if (card.words.length === 0) {
    return `A page from my Linguini journal in ${language}. Snap a photo of your day and learn the words inside it.`;
  }
  return `I learned ${card.words.join(", ")} in ${language} from one photo. Linguini turns the photos you take into bite-size lessons.`;
}

export async function generateMetadata({ searchParams }: { searchParams: SearchParams }): Promise<Metadata> {
  const card = await readCard(searchParams);
  const query = journalQuery(card);
  const title = `${journalTitle(card)} · My Linguini journal`;
  const description = describe(card);
  const image = {
    url: `/og?${query}`,
    width: OG_SIZE.width,
    height: OG_SIZE.height,
    alt: `${journalTitle(card)} — a page from a Linguini journal in ${LANGUAGE_NAME[card.lang]}`,
    type: "image/png",
  };

  return {
    title: { absolute: title },
    description,
    alternates: { canonical: "/" },
    robots: { index: false, follow: true },
    openGraph: {
      type: "website",
      siteName: site.name,
      locale: site.locale,
      url: `/share?${query}`,
      title,
      description,
      images: [image],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [image],
    },
  };
}

export default async function SharePage({ searchParams }: { searchParams: SearchParams }) {
  const card = await readCard(searchParams);
  const { photo } = card;
  const language = LANGUAGE_NAME[card.lang];
  const shareUrl = `${site.url}/share?${journalQuery(card)}`;
  const shareText =
    card.words.length > 0
      ? `I learned ${card.words.length} ${language} ${card.words.length === 1 ? "word" : "words"} from one photo on Linguini.`
      : `A page from my Linguini journal in ${language}.`;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.brand} aria-label="Linguini home">
          <Image src="/brand/linguini-wordmark.png" alt="" width={450} height={150} priority className={styles.wordmark} />
        </Link>
      </header>

      <article className={styles.card} aria-labelledby="share-title">
        <figure className={styles.print}>
          <span className={styles.tape} aria-hidden="true" />
          <div className={styles.photo}>
            <Image
              src={photo.src}
              alt={photo.alt}
              fill
              priority
              sizes="(min-width: 880px) 400px, 88vw"
              className={styles.photoImg}
            />
          </div>
          <figcaption className={styles.caption}>{photo.subject}</figcaption>
        </figure>

        <div className={styles.entry}>
          <p className={styles.eyebrow}>
            <Image src="/brand/linguini-logo.png" alt="" width={32} height={32} />
            My Linguini journal · {language}
          </p>
          <h1 id="share-title" className={styles.title}>
            {journalTitle(card)}
          </h1>

          {card.words.length > 0 ? (
            <ul className={styles.words} aria-label={`Words learned in ${language}`}>
              {card.words.map((word) => (
                <li key={word} className={styles.word} lang={card.lang}>
                  {word}
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.lede}>Snap a photo. Linguini finds the words inside it and teaches them in {language}.</p>
          )}

          <div className={styles.actions}>
            <Link href="/#try" className="btn">
              Try it with your own photo
            </Link>
            <a href={appLinks.signUp} className="btn btn--teal">
              Start free
            </a>
          </div>

          <div className={styles.share}>
            <ShareBar url={shareUrl} text={shareText} label="Share this page" />
          </div>

          <p className={styles.credit}>
            Photo: {photo.author === "unknown" ? "photographer not credited" : photo.author}.{" "}
            <Link href="/credits">Photo credits</Link>
          </p>
        </div>
      </article>
    </main>
  );
}

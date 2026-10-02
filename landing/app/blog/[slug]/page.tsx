import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { postBodies } from "@/components/blog/postBodies";
import { ArrowLeft, ArrowRight, Book, Download, Sparkle } from "@/components/icons";
import { serializeJsonLd } from "@/components/JsonLd";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { formatPostDate, getPost, posts } from "@/data/posts";
import { pageMetadata } from "@/lib/seo";
import { appLinks, site } from "@/lib/site";
import styles from "./post.module.css";

type Props = { params: Promise<{ slug: string }> };

export const dynamicParams = false;

export function generateStaticParams() {
  return posts.map(post => ({ slug: post.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const post = getPost((await params).slug);
  if (!post) return {};
  return pageMetadata({
    title: post.title,
    description: post.summary,
    path: `/blog/${post.slug}`,
    article: { publishedTime: post.date, section: post.category },
    ownImage: true,
  });
}

export default async function PostPage({ params }: Props) {
  const { slug } = await params;
  const post = getPost(slug);
  const Body = postBodies[slug];
  if (!post || !Body) notFound();

  const url = `${site.url}/blog/${post.slug}`;
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    "@id": `${url}#article`,
    headline: post.title,
    description: post.summary,
    datePublished: post.date,
    dateModified: post.date,
    articleSection: post.category,
    inLanguage: "en",
    timeRequired: `PT${post.readMinutes}M`,
    url,
    mainEntityOfPage: url,
    image: `${url}/opengraph-image`,
    author: { "@id": `${site.url}/#organization` },
    publisher: { "@id": `${site.url}/#organization` },
    isPartOf: { "@id": `${site.url}/#website` },
  };

  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <div className="no-print"><SiteHeader /></div>
      <main id="main" className={styles.main}>
        <article className={`container ${styles.article}`}>
          <p className={`print-only ${styles.printBrand}`}>
            <Image src="/brand/linguini-wordmark.png" alt="Linguini" width={450} height={150} className={styles.printWordmark} />
            <span>{`${site.url.replace(/^https?:\/\//, "")}/blog/${post.slug}`}</span>
          </p>

          <div className={styles.topbar}>
            <Link href="/blog" className={`btn-quiet ${styles.back}`}>
              <ArrowLeft size={18} /> Back to blog
            </Link>
            <time dateTime={post.date} className={styles.date}>{formatPostDate(post.date)}</time>
          </div>

          <header className={styles.head}>
            <p className={styles.meta}>{post.category} · {post.readMinutes} min read</p>
            <h1 className={styles.title}>{post.title}</h1>
            <p className={styles.summary}>{post.summary}</p>
            <div className={styles.actions}>
              <Link href="/#try" className="btn btn-gloss">
                Try a lesson <ArrowRight size={18} />
              </Link>
              {post.pdf ? (
                <a href={post.pdf} download className="btn btn--paper">
                  Download PDF <Download size={18} />
                </a>
              ) : null}
            </div>
          </header>

          <div className={styles.column}>
            <Body />
          </div>

          <footer className={styles.end}>
            <div className={styles.links}>
              <Link href="/#pricing" className={styles.linkCard}>
                <span className={styles.linkIcon}><Sparkle size={20} /></span>
                <span><small>Pricing</small>See the plans</span>
              </Link>
              <Link href="/blog" className={styles.linkCard}>
                <span className={styles.linkIcon}><Book size={20} /></span>
                <span><small>Blog</small>Read more posts</span>
              </Link>
            </div>
            <div className={styles.cta}>
              <h2 className={styles.ctaTitle}>Turn today into your first page</h2>
              <p>One photo lesson and one journal page a day are free. Pick Spanish or French and start in under a minute.</p>
              <a href={appLinks.signUp} className="btn btn-gloss">
                Start learning free <ArrowRight size={18} />
              </a>
            </div>
          </footer>
        </article>
      </main>
      <div className="no-print"><SiteFooter /></div>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(jsonLd) }} />
    </>
  );
}

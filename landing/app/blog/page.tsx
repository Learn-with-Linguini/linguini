import type { Metadata } from "next";
import Link from "next/link";
import { PostCover } from "@/components/blog/PostCover";
import { ArrowRight } from "@/components/icons";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { formatPostDate, posts } from "@/data/posts";
import { pageMetadata } from "@/lib/seo";
import styles from "./blog.module.css";

export const metadata: Metadata = pageMetadata({
  title: "Blog",
  description: "Notes from the Linguini team on learning from photos, how lessons are built, and how we price the app.",
  path: "/blog",
});

export default function BlogPage() {
  const [featured, ...rest] = posts;
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <SiteHeader />
      <main id="main" className={`container ${styles.main}`}>
        <h1 className="visually-hidden">Linguini blog</h1>

        <section className={styles.featured} aria-labelledby="featured-title">
          <div className={styles.featuredText}>
            <time dateTime={featured.date} className={styles.date}>{formatPostDate(featured.date)}</time>
            <h2 id="featured-title" className={styles.featuredTitle}>{featured.title}</h2>
            <p className={styles.summary}>{featured.summary}</p>
            <Link href={`/blog/${featured.slug}`} className="btn btn-gloss">
              Read more <ArrowRight size={18} />
            </Link>
          </div>
          <Link href={`/blog/${featured.slug}`} className={styles.featuredMedia} aria-label={featured.title} tabIndex={-1}>
            <PostCover post={featured} sizes="(min-width: 900px) 640px, 100vw" priority />
          </Link>
        </section>

        <ul className={styles.cards}>
          {rest.slice(0, 2).map(post => (
            <li key={post.slug}>
              <Link href={`/blog/${post.slug}`} className={styles.card}>
                <PostCover post={post} sizes="(min-width: 720px) 560px, 100vw" />
                <p className={styles.meta}>
                  {post.category} <span aria-hidden="true">·</span> <time dateTime={post.date}>{formatPostDate(post.date)}</time>
                </p>
                <h3 className={styles.cardTitle}>
                  {post.title} <span aria-hidden="true" className={styles.chevron}>›</span>
                </h3>
              </Link>
            </li>
          ))}
        </ul>

        <section aria-labelledby="all-posts">
          <h2 id="all-posts" className={styles.allTitle}>All posts</h2>
          <ul className={styles.list}>
            {posts.map(post => (
              <li key={post.slug}>
                <Link href={`/blog/${post.slug}`} className={styles.row}>
                  <span className={styles.rowText}>
                    <span className={styles.rowTitle}>{post.title}</span>
                    <span className={styles.rowSummary}>{post.summary}</span>
                  </span>
                  <time dateTime={post.date} className={styles.date}>{formatPostDate(post.date)}</time>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}

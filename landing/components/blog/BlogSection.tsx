import Link from "next/link";
import { formatPostDate, posts } from "@/data/posts";
import { ArrowRight } from "../icons";
import { PostCover } from "./PostCover";
import styles from "./BlogSection.module.css";

/** The three newest posts, shown between the final call to action and the footer. */
export function BlogSection() {
  return (
    <section className={`section ${styles.section}`} aria-labelledby="blog-title">
      <div className="container">
        <div className={styles.head}>
          <h2 id="blog-title" className={styles.title}>From the Linguini kitchen</h2>
          <Link href="/blog" className="btn-quiet">
            All posts <ArrowRight size={18} />
          </Link>
        </div>
        <ul className={styles.grid}>
          {posts.slice(0, 3).map(post => (
            <li key={post.slug}>
              <Link href={`/blog/${post.slug}`} className={styles.card}>
                <PostCover post={post} />
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
      </div>
    </section>
  );
}

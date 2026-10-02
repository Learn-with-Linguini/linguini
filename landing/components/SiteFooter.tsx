import Image from "next/image";
import Link from "next/link";
import { appLinks, site } from "@/lib/site";
import styles from "./SiteFooter.module.css";

export function SiteFooter() {
  return (
    <footer className={styles.footer}>
      <div className={`container ${styles.grid}`}>
        <div className={styles.brand}>
          <Image src="/brand/linguini-wordmark.png" alt="Linguini" width={450} height={150} className={styles.wordmark} />
          <p>Language lessons from the photos you take. Served fresh daily in Spanish and French.</p>
        </div>
        <nav aria-label="Product" className={styles.col}>
          <h2 className={styles.heading}>Product</h2>
          <Link href="/#try">Try a session</Link>
          <Link href="/#features">Features</Link>
          <Link href="/#journal">Journal</Link>
          <Link href="/#pricing">Pricing</Link>
          <Link href="/learn/spanish">Learn Spanish</Link>
          <Link href="/learn/french">Learn French</Link>
        </nav>
        <nav aria-label="Account" className={styles.col}>
          <h2 className={styles.heading}>Account</h2>
          <a href={appLinks.signUp}>Create an account</a>
          <a href={appLinks.signIn}>Log in</a>
        </nav>
        <nav aria-label="About" className={styles.col}>
          <h2 className={styles.heading}>About</h2>
          <Link href="/#faq">FAQ</Link>
          <Link href="/blog">Blog</Link>
          <Link href="/blog/linguini-vs-duolingo">Compare apps</Link>
          <Link href="/credits">Photo credits</Link>
          <a href={site.repoUrl}>GitHub</a>
        </nav>
      </div>
      <div className={`container ${styles.base}`}>
        <p>© {new Date().getFullYear()} Linguini. Every photo on this page is a real photograph, credited on the credits page.</p>
      </div>
    </footer>
  );
}

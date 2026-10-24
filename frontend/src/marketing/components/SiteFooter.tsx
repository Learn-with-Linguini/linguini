import Image from "./Image";
import Link from "./Link";
import { appLinks } from "../lib/site";
import { SOCIAL_LINKS } from "../../config/social";
import { trackAction } from "../../lib/analytics";
import styles from "./SiteFooter.module.css";

export function SiteFooter() {
  return (
    <footer className={styles.footer}>
      <div className={`container ${styles.grid}`}>
        <div className={styles.brand}>
          <Image src="/brand/linguini-wordmark.png" alt="Linguini" width={450} height={150} className={styles.wordmark} />
          <p>Language lessons from the photos you take, in Spanish, French, German and beginner Korean.</p>
        </div>
        <nav aria-label="Product" className={styles.col}>
          <h2 className={styles.heading}>Product</h2>
          <Link href="/demo">Try a session</Link>
          <Link href="/#features">Features</Link>
          <Link href="/#journal">Journal</Link>
          <Link href="/#pricing">Pricing</Link>
          <Link href="/learn/spanish">Learn Spanish</Link>
          <Link href="/learn/french">Learn French</Link>
          <Link href="/learn/german">Learn German</Link>
          <Link href="/learn/korean">Learn Korean</Link>
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
          <Link href="/privacy">Privacy policy</Link>
          <Link href="/terms">Terms of service</Link>
          <a href={appLinks.contact}>Contact us</a>
        </nav>
        <nav aria-label="Follow us" className={styles.col}>
          <h2 className={styles.heading}>Follow us</h2>
          <a href={SOCIAL_LINKS.instagram.url} target="_blank" rel="noopener noreferrer" onClick={() => trackAction("social_link_clicked", { platform: "instagram" })}>Instagram</a>
          <a href={SOCIAL_LINKS.tiktok.url} target="_blank" rel="noopener noreferrer" onClick={() => trackAction("social_link_clicked", { platform: "tiktok" })}>TikTok</a>
          <a href={SOCIAL_LINKS.x.url} target="_blank" rel="noopener noreferrer" onClick={() => trackAction("social_link_clicked", { platform: "x" })}>X (Twitter)</a>
          <a href={SOCIAL_LINKS.linkedin.url} target="_blank" rel="noopener noreferrer" onClick={() => trackAction("social_link_clicked", { platform: "linkedin" })}>LinkedIn</a>
        </nav>
      </div>
      <div className={`container ${styles.base}`}>
        <p>© {new Date().getFullYear()} Linguini. Every photo on this page is a real photograph, credited on the credits page.</p>
      </div>
    </footer>
  );
}

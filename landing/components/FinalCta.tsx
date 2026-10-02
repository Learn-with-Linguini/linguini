import Image from "next/image";
import { appLinks, site } from "@/lib/site";
import { ShareBar } from "./ShareBar";
import { ArrowRight } from "./icons";
import styles from "./FinalCta.module.css";

type FinalCtaProps = {
  title?: string;
  lede?: string;
  /** Page to share; defaults to the home page. */
  shareUrl?: string;
};

export function FinalCta({
  title = "Your next photo is a lesson.",
  lede = "Sign up in under a minute, pick Spanish or French, and turn today into your first page.",
  shareUrl = site.url,
}: FinalCtaProps) {
  return (
    <section className={styles.section} aria-labelledby="cta-title">
      <Image src="/pasta/fusilli.webp" alt="" width={276} height={360} className={`${styles.pasta} ${styles.fusilli}`} />
      <Image src="/pasta/penne.webp" alt="" width={360} height={341} className={`${styles.pasta} ${styles.penne}`} />
      <Image src="/pasta/macaroni.webp" alt="" width={360} height={333} className={`${styles.pasta} ${styles.macaroni}`} />
      <div className={`container ${styles.inner}`}>
        <h2 id="cta-title" className={styles.title}>{title}</h2>
        <p className={styles.lede}>{lede}</p>
        <a href={appLinks.signUp} className={`btn ${styles.cta}`}>
          Start learning free <ArrowRight size={20} />
        </a>
        <div className={styles.share}>
          <p className={styles.shareLabel}>Know someone learning a language? Pass Linguini on.</p>
          <ShareBar url={shareUrl} text="Linguini turns the photos you take into bite-size Spanish and French lessons." />
        </div>
      </div>
    </section>
  );
}

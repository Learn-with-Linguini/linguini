import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { pageMetadata } from "@/lib/seo";
import { site } from "@/lib/site";
import styles from "../legal.module.css";

export const metadata: Metadata = pageMetadata({
  title: "Terms of service",
  description: "The terms that apply when you access or use the Linguini beta.",
  path: "/terms",
});

const effectiveDate = "10 October 2026";

function Contact() {
  if (site.supportEmail) {
    return <a href={`mailto:${site.supportEmail}`}>{site.supportEmail}</a>;
  }
  return <>the official support channel displayed in the Linguini service</>;
}

export default function TermsPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.brand} aria-label="Linguini home">
          <Image src="/brand/linguini-wordmark.png" alt="" width={450} height={150} priority className={styles.wordmark} />
        </Link>
      </header>

      <main className={styles.main}>
        <div className={styles.intro}>
          <p className={styles.eyebrow}>The beta ground rules</p>
          <h1 className={styles.title}>Terms of service</h1>
          <p className={styles.lede}>
            These terms govern your access to and use of Linguini. Please read them before creating an account or
            uploading a photograph.
          </p>
          <p className={styles.updated}>Effective and last updated: {effectiveDate}</p>
        </div>

        <div className={styles.content}>
          <section className={styles.section}>
            <h2>1. Accepting these terms</h2>
            <p>
              By accessing or using the Linguini website, web application or related services (the “Service”), you agree
              to these terms and our <Link href="/privacy">privacy policy</Link>. If you do not agree, do not use the
              Service. Linguini is currently operated by the Linguini project team as a beta educational project.
            </p>
          </section>

          <section className={styles.section}>
            <h2>2. Eligibility</h2>
            <p>
              You must be at least 13 years old to use the Service. If local law requires you to be older to agree to
              online terms or data processing, you must meet that age or have permission from a parent or guardian. You
              may not use the Service if doing so would violate applicable law.
            </p>
          </section>

          <section className={styles.section}>
            <h2>3. Accounts</h2>
            <p>
              Provide accurate information, keep your login credentials secure and notify us if you suspect unauthorized
              use. You are responsible for activity performed through your account. Do not share an account or create
              accounts through automated means without our permission.
            </p>
          </section>

          <section className={styles.section}>
            <h2>4. A beta service</h2>
            <p>
              Linguini is under active development. Features may be incomplete, inaccurate, unavailable or changed without
              notice. We may introduce usage limits, change supported languages, reset test data or suspend parts of the
              Service to protect users, control costs or improve reliability. We will try to give reasonable notice when
              a planned change materially affects beta users.
            </p>
          </section>

          <section className={styles.section}>
            <h2>5. Your photos and other content</h2>
            <p>
              You retain ownership of photos, journal entries, text and other content you submit (“User Content”). You
              give the Linguini project team a limited, non-exclusive licence to host, copy, process, adapt and transmit
              User Content only as needed to operate, secure, troubleshoot and improve the Service.
            </p>
            <p>You represent that you have the rights and permissions needed to upload your User Content. In particular:</p>
            <ul>
              <li>Do not upload confidential, illegal, exploitative or intimate material.</li>
              <li>Do not upload photographs of another person without appropriate permission.</li>
              <li>Do not upload material that infringes copyright, privacy or other rights.</li>
              <li>Do not use Linguini to identify, track or make sensitive inferences about a person.</li>
            </ul>
            <p>
              We may remove content that creates legal, safety, privacy or operational risk. Our handling of User Content
              is described further in the <Link href="/privacy">privacy policy</Link>.
            </p>
          </section>

          <section className={styles.section}>
            <h2>6. AI-generated learning content</h2>
            <p>
              Linguini uses automated systems to identify scene objects, translate terms, create exercises and evaluate
              some responses. These systems can misunderstand an image, produce an incorrect translation or give
              unsuitable feedback. Review generated content before relying on it and use the object-review tools to make
              corrections.
            </p>
            <p>
              Linguini is a supplementary educational tool. We do not guarantee language proficiency, examination results,
              translation accuracy or fitness for professional, medical, legal, safety-critical or emergency use.
            </p>
          </section>

          <section className={styles.section}>
            <h2>7. Acceptable use</h2>
            <p>You must not:</p>
            <ul>
              <li>Break the law, violate another person’s rights or encourage harmful conduct.</li>
              <li>Probe, scan or test the Service for vulnerabilities without written permission.</li>
              <li>Bypass authentication, usage limits, moderation or access controls.</li>
              <li>Upload malware or interfere with the Service, its infrastructure or other users.</li>
              <li>Scrape, reverse engineer or automatically extract Service content except where law expressly permits it.</li>
              <li>Use the Service to generate spam, abusive material or content intended to deceive or impersonate others.</li>
              <li>Resell or commercially exploit the beta without our written permission.</li>
            </ul>
          </section>

          <section className={styles.section}>
            <h2>8. Linguini materials</h2>
            <p>
              The Service, including its software, design, branding, curated lessons and original content, belongs to the
              Linguini project team or its licensors. Subject to these terms, we grant you a personal, limited,
              non-exclusive, non-transferable and revocable right to use the Service for learning and beta evaluation.
            </p>
          </section>

          <section className={styles.section}>
            <h2>9. Third-party services</h2>
            <p>
              The Service relies on third parties for authentication, hosting, storage, analytics, moderation and AI
              processing. Their systems may be unavailable or governed by their own terms. We are not responsible for
              third-party websites that you choose to visit from the Service.
            </p>
          </section>

          <section className={styles.section}>
            <h2>10. Suspension and termination</h2>
            <p>
              You may stop using the Service at any time. You may ask us to delete your account through <Contact />. We may
              restrict or suspend access when reasonably necessary to protect the Service or others, investigate abuse,
              comply with law or address a breach of these terms. Where practical, we will explain the reason and provide
              a way to contact us.
            </p>
          </section>

          <section className={styles.section}>
            <h2>11. Disclaimers</h2>
            <p>
              To the fullest extent permitted by law, the beta is provided “as is” and “as available”. We do not promise
              uninterrupted availability, permanent storage, error-free operation or that generated content will be
              complete or accurate. Nothing in these terms excludes a right or guarantee that cannot lawfully be excluded.
            </p>
          </section>

          <section className={styles.section}>
            <h2>12. Limitation of liability</h2>
            <p>
              To the fullest extent permitted by law, the Linguini project team will not be liable for indirect,
              incidental, special or consequential loss, loss of data, lost opportunity or loss arising from reliance on
              generated learning content. Our total liability relating to the free beta will not exceed S$50. These limits
              do not apply where liability cannot legally be limited or excluded.
            </p>
          </section>

          <section className={styles.section}>
            <h2>13. Changes</h2>
            <p>
              We may update these terms as the Service develops. We will change the date above and provide additional
              notice when a material change affects current users. Continuing to use the Service after revised terms take
              effect means you accept them.
            </p>
          </section>

          <section className={styles.section}>
            <h2>14. Governing law</h2>
            <p>
              These terms are governed by applicable law. Disputes relating to the Service will be handled by a court
              with appropriate jurisdiction, subject to any rights you have under mandatory local law.
            </p>
          </section>

          <section className={styles.section}>
            <h2>15. Contact</h2>
            <p>Questions about these terms may be sent to the Linguini project team through <Contact />.</p>
          </section>
        </div>

        <p className={styles.back}>
          <Link href="/" className="btn-quiet"><span aria-hidden="true">←</span> Back to Linguini</Link>
        </p>
      </main>
    </div>
  );
}

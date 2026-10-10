import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { pageMetadata } from "@/lib/seo";
import { site } from "@/lib/site";
import styles from "../legal.module.css";

export const metadata: Metadata = pageMetadata({
  title: "Privacy policy",
  description: "How Linguini collects, uses, shares and protects information during the beta.",
  path: "/privacy",
});

const effectiveDate = "10 October 2026";

function Contact() {
  if (site.supportEmail) {
    return <a href={`mailto:${site.supportEmail}`}>{site.supportEmail}</a>;
  }
  return <>the official support channel displayed in the Linguini service</>;
}

export default function PrivacyPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.brand} aria-label="Linguini home">
          <Image src="/brand/linguini-wordmark.png" alt="" width={450} height={150} priority className={styles.wordmark} />
        </Link>
      </header>

      <main className={styles.main}>
        <div className={styles.intro}>
          <p className={styles.eyebrow}>Your data, explained plainly</p>
          <h1 className={styles.title}>Privacy policy</h1>
          <p className={styles.lede}>
            Linguini turns photos from your day into language-learning activities. This policy explains what information
            the Linguini project team collects, why we use it and the choices you have during the beta.
          </p>
          <p className={styles.updated}>Effective and last updated: {effectiveDate}</p>
        </div>

        <div className={styles.content}>
          <section className={styles.section}>
            <h2>1. Who we are and what this covers</h2>
            <p>
              Linguini is currently operated by the Linguini project team as a beta educational service.
              This policy applies to the Linguini website, web application and related support communications
              (together, the “Service”).
            </p>
          </section>

          <section className={styles.section}>
            <h2>2. Information we collect</h2>
            <h3>Account and profile information</h3>
            <p>
              We collect information needed to create and manage your account, such as your email address, display name,
              authentication identifier, timezone, selected languages, proficiency level, learning goals and app
              preferences.
            </p>
            <h3>Photos and learning content</h3>
            <p>
              When you upload or capture a photo, we store the image and related technical information so we can identify
              scene objects and build a lesson. We also store the objects you confirm, translations, tasks, answers,
              vocabulary progress, XP, session history and journal entries that you create.
            </p>
            <h3>Audio and device permissions</h3>
            <p>
              We record whether you enable camera or microphone features. If a speech feature asks you to submit audio in
              the future, we will process the audio and any resulting transcript to provide that feature. Simply granting
              microphone permission does not by itself upload a recording.
            </p>
            <h3>Usage and technical information</h3>
            <p>
              Our hosting, security and analytics tools may collect IP address, browser and device type, pages or screens
              visited, feature interactions, referring links, performance information, error logs and approximate location
              derived from an IP address. We use this information to operate, secure and improve the beta.
            </p>
            <h3>Support information</h3>
            <p>
              We collect the messages, contact details, and optional files you provide when you report a problem or
              give feedback.
            </p>
          </section>

          <section className={styles.section}>
            <h2>3. How we use information</h2>
            <ul>
              <li>Provide accounts, photo lessons, games, vocabulary progress and journals.</li>
              <li>Analyze uploaded scenes and generate translations, clues and learning activities.</li>
              <li>Save your progress and personalize the Service to your selected language and level.</li>
              <li>Protect the Service, moderate uploads, prevent abuse and enforce usage limits.</li>
              <li>Diagnose failures, measure performance and understand which features are useful.</li>
              <li>Respond to support requests and conduct beta research with your permission.</li>
              <li>Meet legal obligations and establish, exercise or defend legal claims.</li>
            </ul>
            <p>We do not sell your personal information or display your private photos to other learners.</p>
          </section>

          <section className={styles.section}>
            <h2>4. AI processing</h2>
            <p>
              Linguini uses automated systems to analyze photos, translate scene information, generate learning tasks and
              evaluate some responses. Depending on the feature and our current configuration, relevant images, scene
              descriptions or text may be sent to OpenRouter, OpenAI or model providers routed through those services.
              Generated results can be inaccurate. The object-review screen lets you correct an analysis before using it
              in a lesson.
            </p>
            <p className={styles.notice}>
              Do not upload photographs containing confidential documents, financial information, medical information,
              intimate content or people who have not agreed to the upload.
            </p>
          </section>

          <section className={styles.section}>
            <h2>5. When we share information</h2>
            <p>We disclose information only as needed to operate the Service, including to:</p>
            <ul>
              <li>Supabase for authentication, database hosting and private image storage.</li>
              <li>Vercel and our API hosting provider for website and application delivery.</li>
              <li>AI and moderation providers for the specific processing described above.</li>
              <li>Email and group-communication providers that deliver and retain support requests and attachments.</li>
              <li>Analytics, error-monitoring and security providers used to maintain the beta.</li>
              <li>Professional advisers, authorities or other parties when required by law or necessary to protect rights and safety.</li>
              <li>A successor team or organization if responsibility for Linguini is transferred, subject to appropriate safeguards.</li>
            </ul>
            <p>These providers may process information in countries other than the country where you live.</p>
          </section>

          <section className={styles.section}>
            <h2>6. Cookies and local storage</h2>
            <p>
              The Service uses browser storage and similar technologies to keep you signed in, remember settings, protect
              sessions and measure usage. You can restrict these through your browser, but essential account and session
              features may stop working.
            </p>
          </section>

          <section className={styles.section}>
            <h2>7. Retention</h2>
            <p>
              We keep account content while your account is active and for as long as reasonably necessary to provide the
              beta, respond to support requests, resolve disputes, prevent abuse and meet legal obligations. Support
              messages and attachments may remain in our team mailbox while they are needed to investigate and document a
              request. We may retain limited security logs and backup copies for a reasonable period after deletion. We
              will delete or anonymize information when it is no longer needed for those purposes.
            </p>
          </section>

          <section className={styles.section}>
            <h2>8. Security</h2>
            <p>
              We use measures intended to protect information, including authenticated access, private media storage,
              encrypted network connections and restricted service credentials. No online service is completely secure,
              so please use a strong, unique password and notify us if you suspect unauthorized access.
            </p>
          </section>

          <section className={styles.section}>
            <h2>9. Your choices and rights</h2>
            <p>You may ask us to:</p>
            <ul>
              <li>Explain what personal information we hold about you and how it has been used or disclosed.</li>
              <li>Correct inaccurate account information.</li>
              <li>Delete your account, photos, journal entries and other personal content, subject to lawful exceptions.</li>
              <li>Withdraw consent where processing relies on consent.</li>
              <li>Stop participating in optional research or communications.</li>
            </ul>
            <p>
              Send a request through <Contact />. We may need to verify your identity before acting on a request.
            </p>
          </section>

          <section className={styles.section}>
            <h2>10. Children</h2>
            <p>
              The beta is not directed to children under 13. If you are under the age at which you can consent to data
              processing where you live, use Linguini only with permission from a parent or guardian. Contact us if you
              believe a child provided personal information without appropriate permission.
            </p>
          </section>

          <section className={styles.section}>
            <h2>11. Changes to this policy</h2>
            <p>
              We may update this policy as the beta develops. We will change the date above and provide additional notice
              in the Service when a change materially affects how we handle your information.
            </p>
          </section>

          <section className={styles.section}>
            <h2>12. Contact</h2>
            <p>
              For privacy questions, concerns or data requests, contact the Linguini project team through <Contact />.
            </p>
          </section>
        </div>

        <p className={styles.back}>
          <Link href="/" className="btn-quiet"><span aria-hidden="true">←</span> Back to Linguini</Link>
        </p>
      </main>
    </div>
  );
}
